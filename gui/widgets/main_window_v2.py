# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from dataclasses import asdict

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableView,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.models import StrategyRunConfig
from gui.services import apply_dataframe, format_metric_dict, load_csv, open_path
from gui.workers.RunStrategyWorker import RunStrategyWorker
from gui.workers.UniverseWorker import UniverseWorker


class StrategyConfigPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("运行参数", parent)
        form = QFormLayout(self)

        self.edit_since = QLineEdit("2022-01-01")
        self.edit_universe = QLineEdit("data/universe_fund.csv")
        self.btn_browse = QPushButton("浏览")
        row_universe = QWidget()
        row_universe_layout = QHBoxLayout(row_universe)
        row_universe_layout.setContentsMargins(0, 0, 0, 0)
        row_universe_layout.addWidget(self.edit_universe)
        row_universe_layout.addWidget(self.btn_browse)

        self.spin_workers = QSpinBox(); self.spin_workers.setRange(1, 64); self.spin_workers.setValue(8)
        self.spin_topn = QSpinBox(); self.spin_topn.setRange(1, 50); self.spin_topn.setValue(5)
        self.spin_window = QSpinBox(); self.spin_window.setRange(30, 1260); self.spin_window.setValue(252)
        self.spin_universe_limit = QSpinBox(); self.spin_universe_limit.setRange(5, 1000); self.spin_universe_limit.setValue(100)
        self.spin_backfill = QSpinBox(); self.spin_backfill.setRange(0, 1260); self.spin_backfill.setValue(126)
        self.edit_weight_scheme = QLineEdit("weight_optimized")

        self.dsb_max_weight = QDoubleSpinBox(); self._init_dsb(self.dsb_max_weight, 0.45, 0.01, 1.0, 0.01, 2)
        self.dsb_min_weight = QDoubleSpinBox(); self._init_dsb(self.dsb_min_weight, 0.00, 0.00, 0.50, 0.01, 2)
        self.dsb_risk_aversion = QDoubleSpinBox(); self._init_dsb(self.dsb_risk_aversion, 4.0, 0.1, 100.0, 0.1, 2)
        self.dsb_score_tilt = QDoubleSpinBox(); self._init_dsb(self.dsb_score_tilt, 0.03, 0.0, 1.0, 0.01, 3)
        self.dsb_turnover = QDoubleSpinBox(); self._init_dsb(self.dsb_turnover, 0.15, 0.0, 10.0, 0.01, 3)
        self.dsb_l2 = QDoubleSpinBox(); self._init_dsb(self.dsb_l2, 0.01, 0.0, 10.0, 0.01, 3)
        self.dsb_target_vol = QDoubleSpinBox(); self._init_dsb(self.dsb_target_vol, 0.00, 0.0, 2.0, 0.01, 3)
        self.spin_cov_lookback = QSpinBox(); self.spin_cov_lookback.setRange(20, 1260); self.spin_cov_lookback.setValue(126)

        form.addRow("起始日期", self.edit_since)
        form.addRow("基金池 CSV", row_universe)
        form.addRow("并行 workers", self.spin_workers)
        form.addRow("Top-N", self.spin_topn)
        form.addRow("因子窗口", self.spin_window)
        form.addRow("基金池上限", self.spin_universe_limit)
        form.addRow("历史回填天数", self.spin_backfill)
        form.addRow("默认权重列", self.edit_weight_scheme)
        form.addRow(QLabel("—— 约束优化参数 ——"))
        form.addRow("单基金最大权重", self.dsb_max_weight)
        form.addRow("单基金最小权重", self.dsb_min_weight)
        form.addRow("风险厌恶系数", self.dsb_risk_aversion)
        form.addRow("得分倾斜强度", self.dsb_score_tilt)
        form.addRow("锚点/换手惩罚", self.dsb_turnover)
        form.addRow("L2 正则", self.dsb_l2)
        form.addRow("目标年化波动(0=关闭)", self.dsb_target_vol)
        form.addRow("协方差回看窗", self.spin_cov_lookback)

    @staticmethod
    def _init_dsb(widget: QDoubleSpinBox, val, mi, ma, step, dec):
        widget.setRange(mi, ma)
        widget.setSingleStep(step)
        widget.setDecimals(dec)
        widget.setValue(val)

    def to_config(self) -> StrategyRunConfig:
        return StrategyRunConfig(
            since=self.edit_since.text().strip(),
            universe_csv=self.edit_universe.text().strip(),
            workers=int(self.spin_workers.value()),
            top_n=int(self.spin_topn.value()),
            window_days=int(self.spin_window.value()),
            universe_limit=int(self.spin_universe_limit.value()),
            weight_scheme=self.edit_weight_scheme.text().strip() or "weight_optimized",
            backfill_days=int(self.spin_backfill.value()),
            max_weight=float(self.dsb_max_weight.value()),
            min_weight=float(self.dsb_min_weight.value()),
            risk_aversion=float(self.dsb_risk_aversion.value()),
            score_tilt=float(self.dsb_score_tilt.value()),
            turnover_penalty=float(self.dsb_turnover.value()),
            l2_penalty=float(self.dsb_l2.value()),
            target_vol=float(self.dsb_target_vol.value()),
            cov_lookback=int(self.spin_cov_lookback.value()),
        )


class UniverseConfigPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("基金池生成", parent)
        form = QFormLayout(self)
        self.spin_pool_size = QSpinBox(); self.spin_pool_size.setRange(5, 2000); self.spin_pool_size.setValue(100)
        self.spin_lookback = QSpinBox(); self.spin_lookback.setRange(60, 1260); self.spin_lookback.setValue(252)
        form.addRow("基金池规模 K", self.spin_pool_size)
        form.addRow("回看天数 N", self.spin_lookback)

    def to_params(self) -> dict:
        return {
            "pool_size": int(self.spin_pool_size.value()),
            "lookback_days": int(self.spin_lookback.value()),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fund Pool Model · Research Workbench")
        self.resize(1440, 900)

        self.worker: RunStrategyWorker | None = None
        self.univ_worker: UniverseWorker | None = None
        self._last_artifacts = {}
        self._last_art_dir = ""

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        self.btn_start = QPushButton("运行主流程")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_open_output = QPushButton("打开 output")
        self.btn_open_artifacts = QPushButton("打开本次 artifacts")
        self.btn_open_artifacts.setEnabled(False)
        toolbar.addWidget(self.btn_start)
        toolbar.addWidget(self.btn_stop)
        toolbar.addWidget(self.btn_open_output)
        toolbar.addWidget(self.btn_open_artifacts)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)

        self.lbl_summary = QLabel("结果摘要：-")
        self.lbl_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.lbl_summary)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, stretch=1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.strategy_panel = StrategyConfigPanel()
        self.universe_panel = UniverseConfigPanel()
        self.btn_generate_universe = QPushButton("生成基金池 CSV")
        left_layout.addWidget(self.strategy_panel)
        left_layout.addWidget(self.universe_panel)
        left_layout.addWidget(self.btn_generate_universe)
        left_layout.addStretch(1)
        splitter.addWidget(left)

        right = QTabWidget()
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        self.log = QTextEdit(); self.log.setReadOnly(True)
        right.addTab(self.log, "日志")

        chart_tab = QWidget()
        chart_layout = QVBoxLayout(chart_tab)
        self.figure = Figure(figsize=(8, 4.2))
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        right.addTab(chart_tab, "回测图表")

        tables_tab = QTabWidget()
        self.tbl_scores = QTableView()
        self.tbl_weights = QTableView()
        self.tbl_trades = QTableView()
        self.tbl_universe = QTableView()
        tables_tab.addTab(self.tbl_scores, "评分")
        tables_tab.addTab(self.tbl_weights, "权重")
        tables_tab.addTab(self.tbl_trades, "交易")
        tables_tab.addTab(self.tbl_universe, "基金池预览")
        right.addTab(tables_tab, "表格")

        self.report_view = QTextBrowser()
        right.addTab(self.report_view, "研究报告")

        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_open_output.clicked.connect(lambda: open_path(os.path.join(os.getcwd(), "output")))
        self.btn_open_artifacts.clicked.connect(self.open_artifacts)
        self.strategy_panel.btn_browse.clicked.connect(self.on_browse_universe_csv)
        self.btn_generate_universe.clicked.connect(self.on_generate_universe)

        self.append_log("建议先生成或确认基金池 CSV，再运行主流程。")

    def append_log(self, message: str):
        self.log.append(message)

    def on_browse_universe_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择基金池 CSV", "data", "CSV Files (*.csv)")
        if path:
            self.strategy_panel.edit_universe.setText(path)

    def on_generate_universe(self):
        if self.univ_worker and self.univ_worker.isRunning():
            return
        output_csv = self.strategy_panel.edit_universe.text().strip() or "data/universe_fund.csv"
        params = self.universe_panel.to_params()
        self.univ_worker = UniverseWorker(params, output_csv=output_csv)
        self.univ_worker.stage.connect(lambda n, p: self.progress.setValue(int(p)))
        self.univ_worker.log.connect(lambda s: self.append_log(f"[UNIV] {s}"))
        self.univ_worker.preview.connect(self.render_universe_preview)
        self.univ_worker.saved.connect(self.on_universe_saved)
        self.univ_worker.failed.connect(lambda e: QMessageBox.critical(self, "基金池失败", e))
        self.univ_worker.start()

    def render_universe_preview(self, rows):
        df = pd.DataFrame(rows or [])
        apply_dataframe(self.tbl_universe, df)

    def on_universe_saved(self, path: str):
        self.append_log(f"[UNIV] 基金池已保存：{path}")
        QMessageBox.information(self, "基金池完成", f"已写入：{path}")

    def on_start(self):
        if self.worker and self.worker.isRunning():
            return
        cfg = self.strategy_panel.to_config()
        if cfg.min_weight > cfg.max_weight:
            QMessageBox.warning(self, "参数错误", "最小权重不能大于最大权重。")
            return
        if cfg.max_weight * cfg.top_n < 1.0 - 1e-12:
            QMessageBox.warning(self, "参数错误", "当前 Top-N 与最大权重组合不可行。")
            return

        self.worker = RunStrategyWorker(asdict(cfg))
        self.worker.progress.connect(self.progress.setValue)
        self.worker.log.connect(self.append_log)
        self.worker.stage.connect(lambda name, pct: self.append_log(f"[STAGE] {name} -> {pct}%"))
        self.worker.artifacts.connect(self.on_artifacts)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.append_log("启动任务...")
        self.worker.start()

    def on_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.append_log("已发送停止信号。")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def on_artifacts(self, payload: dict):
        self._last_artifacts = payload or {}
        self._last_art_dir = os.path.join(os.getcwd(), "gui", "artifacts", payload.get("run_id", ""))
        self.btn_open_artifacts.setEnabled(bool(payload.get("run_id")))

        scores_df = load_csv(payload.get("scores_csv"))
        weights_df = load_csv(payload.get("weights_csv"))
        trades_df = load_csv(payload.get("trades_csv"))
        apply_dataframe(self.tbl_scores, scores_df)
        apply_dataframe(self.tbl_weights, weights_df)
        apply_dataframe(self.tbl_trades, trades_df)
        self.render_equity_chart(payload.get("equity_curve_csv"))
        self.render_report(payload.get("report_html"))

    def render_equity_chart(self, eq_csv: str | None):
        self.ax.clear()
        df = load_csv(eq_csv)
        if df.empty:
            self.ax.text(0.5, 0.5, "没有可绘制的收益曲线", ha="center", va="center", transform=self.ax.transAxes)
            self.canvas.draw_idle()
            return
        x = pd.to_datetime(df["date"], errors="coerce") if "date" in df.columns else pd.to_datetime(df.iloc[:, 0], errors="coerce")
        y = pd.to_numeric(df["equity"], errors="coerce") if "equity" in df.columns else pd.to_numeric(df.iloc[:, 1], errors="coerce")
        self.ax.plot(x, y, label="Strategy")
        if "benchmark" in df.columns:
            bm = pd.to_numeric(df["benchmark"], errors="coerce")
            self.ax.plot(x, bm, label="Benchmark")
            self.ax.legend()
        self.ax.set_title("Equity Curve")
        self.ax.grid(True, alpha=0.3)
        self.figure.autofmt_xdate()
        self.canvas.draw_idle()

    def render_report(self, report_html: str | None):
        if not report_html or not os.path.exists(report_html):
            self.report_view.setPlainText("暂无研究报告。")
            return
        try:
            self.report_view.setHtml(open(report_html, "r", encoding="utf-8").read())
        except Exception:
            self.report_view.setPlainText(report_html)

    def on_done(self, metrics: dict):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_summary.setText(format_metric_dict(metrics))
        self.append_log(self.lbl_summary.text())

    def on_failed(self, message: str):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.append_log(f"[ERROR] {message}")
        QMessageBox.critical(self, "运行失败", str(message))

    def open_artifacts(self):
        if not self._last_art_dir or not os.path.isdir(self._last_art_dir):
            QMessageBox.information(self, "提示", "当前没有可打开的 artifacts 目录。")
            return
        open_path(self._last_art_dir)
