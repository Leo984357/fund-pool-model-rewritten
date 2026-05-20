# -*- coding: utf-8 -*-
from __future__ import annotations
import os, re, glob, math, pathlib, datetime as dt
import pandas as pd

from PySide6.QtWidgets import QTableView, QSpinBox, QComboBox, QWidget, QTabWidget
from PySide6.QtGui import QStandardItemModel, QStandardItem
# ---- 读取 OUTPUT_DIR ----
def _output_dir() -> pathlib.Path:
    # 1) 优先 src/config.py 的 OUTPUT_DIR
    try:
        from src.config import OUTPUT_DIR as _CFG_OUT
        if _CFG_OUT:
            return pathlib.Path(_CFG_OUT)
    except Exception:
        pass
    # 2) 环境变量
    env_out = os.getenv("OUTPUT_DIR") or os.getenv("FUND_OUTPUT_DIR")
    if env_out:
        return pathlib.Path(env_out)
    # 3) 默认 ./output
    return pathlib.Path(__file__).resolve().parents[1] / "output"

# ---- 找最新/前一日 CSV ----
def _latest_csv(pattern: str) -> pathlib.Path | None:
    out = _output_dir()
    files = sorted(out.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def _latest_two_portfolios() -> tuple[pd.DataFrame | None, pd.DataFrame | None, str]:
    """返回 (今日组合, 昨日组合, 权重列名)"""
    scheme = os.getenv("FUND_WEIGHT_SCHEME", "weight_mixed")
    if scheme not in ("weight_equal", "weight_risk_parity", "weight_mixed"):
        scheme = "weight_mixed"

    f_today = _latest_csv("portfolio_fund_*.csv")
    if not f_today:
        return None, None, scheme
    df_today = pd.read_csv(f_today)

    # 找“上一个”文件（按文件名里的日期/或修改时间）
    out = _output_dir()
    all_pf = sorted(out.glob("portfolio_fund_*.csv"))
    prev = None
    if len(all_pf) >= 2:
        # 第二新的即为昨日文件
        prev = all_pf[-2] if all_pf[-1] == f_today else all_pf[-1]
        # 更稳：按 mtime 排序
        all_pf_m = sorted(all_pf, key=lambda p: p.stat().st_mtime, reverse=True)
        prev = all_pf_m[1] if len(all_pf_m) > 1 else None

    df_prev = pd.read_csv(prev) if prev else None
    return df_today, df_prev, scheme

# ---- 清洗/排序：TopN 权重 + score/rank 数值化 ----
def _normalize_portfolio(df: pd.DataFrame, scheme: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "fund_code", "weight", "score", "rank"])

    df = df.copy()
    # 兼容不同导出列名
    for col in ("fund_code", "code"):
        if col in df.columns:
            df.rename(columns={col: "fund_code"}, inplace=True)
            break

    # 数值化
    for col in ("score", "rank", "weight_equal", "weight_risk_parity", "weight_mixed"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if scheme not in df.columns:
        scheme = "weight_mixed"

    keep = [c for c in ["date", "fund_code", scheme, "score", "rank"] if c in df.columns]
    df = df[keep].rename(columns={scheme: "weight"})

    # 排序：rank↑；若 rank 缺失，则 score↓
    if "rank" in df.columns and df["rank"].notna().any():
        df.sort_values(["rank", "score"], ascending=[True, False], inplace=True)
    elif "score" in df.columns:
        df.sort_values("score", ascending=False, inplace=True)
    return df.reset_index(drop=True)

# ---- 由两期组合算“交易清单” ----
def _build_trades(today: pd.DataFrame, prev: pd.DataFrame | None, scheme_col: str) -> pd.DataFrame:
    if today is None or today.empty:
        return pd.DataFrame(columns=["date", "fund_code", "action", "delta"])
    t = today.copy()
    for c in ("fund_code", scheme_col):
        if c not in t.columns:
            return pd.DataFrame(columns=["date", "fund_code", "action", "delta"])

    t = t[["date", "fund_code", scheme_col]].rename(columns={scheme_col: "w_today"})

    if prev is None or prev.empty or scheme_col not in prev.columns:
        # 没有昨日：全部 BUY，delta=今日权重
        t["delta"] = t["w_today"].fillna(0.0)
        t["action"] = t["delta"].apply(lambda x: "BUY" if x > 0 else "FLAT")
        return t[["date", "fund_code", "action", "delta"]]

    p = prev[["fund_code", scheme_col]].rename(columns={scheme_col: "w_prev"})
    df = t.merge(p, how="left", on="fund_code")
    df["w_prev"] = pd.to_numeric(df["w_prev"], errors="coerce").fillna(0.0)
    df["delta"] = (pd.to_numeric(df["w_today"], errors="coerce").fillna(0.0) - df["w_prev"]).round(12)

    def _label(d):
        if d > 1e-12: return "BUY"
        if d < -1e-12: return "SELL"
        return "FLAT"

    df["action"] = df["delta"].apply(_label)
    return df[["date", "fund_code", "action", "delta"]]

# ---- 把 DataFrame 填到 QTableView ----
def _set_table(view: QTableView, df: pd.DataFrame):
    if view is None: return
    model = QStandardItemModel()
    model.setColumnCount(len(df.columns))
    model.setHorizontalHeaderLabels(list(df.columns))
    for r, row in df.iterrows():
        items = []
        for v in row.tolist():
            # 统一字符串化但保留排序数值（Qt 会按文本排序；我们已在 pandas 里排好）
            items.append(QStandardItem("" if pd.isna(v) else f"{v}"))
        model.appendRow(items)
    view.setModel(model)
    view.resizeColumnsToContents()

# ---- 在一个 Tab 上“自动找”两张表 ----
def _find_tables_under(widget: QWidget) -> tuple[QTableView | None, QTableView | None]:
    tables = widget.findChildren(QTableView)
    if not tables:
        return None, None
    # 按 y 坐标从上到下，第一张=TopN，第二张=Trades
    tables.sort(key=lambda w: w.mapToGlobal(w.pos()).y())
    topn = tables[0] if len(tables) >= 1 else None
    trades = tables[1] if len(tables) >= 2 else None
    return topn, trades

# ---- 取 GUI 里的 TopN / 权重方案（取不到就用环境变量/默认） ----
def _read_topn_from_gui(root: QWidget) -> int:
    # 找所有 QSpinBox，取最大值<=1000 的那个；找不到就用 env
    boxes = root.findChildren(QSpinBox)
    for b in boxes:
        try:
            v = int(b.value())
            # 粗略过滤：把“窗口天数”等巨大值排除
            if 1 <= v <= 1000:
                return v
        except Exception:
            pass
    return int(os.getenv("FUND_TOP_N_FUNDS", "10"))

def _read_scheme_from_gui(root: QWidget) -> str:
    boxes = root.findChildren(QComboBox)
    for c in boxes:
        try:
            t = (c.currentData() or c.currentText() or "").strip()
            if t in ("weight_equal", "weight_risk_parity", "weight_mixed"):
                return t
        except Exception:
            pass
    return os.getenv("FUND_WEIGHT_SCHEME", "weight_mixed")

# ---- 对外：在“组合与交易”页刷新 ----
def render_portfolio_tab(tab_widget: QTabWidget):
    idx = tab_widget.currentIndex()
    tab = tab_widget.widget(idx)
    top_view, trades_view = _find_tables_under(tab)

    # 读取数据
    df_today_raw, df_prev_raw, scheme = _latest_two_portfolios()
    # 尝试用 GUI 的权重方案覆盖
    scheme_gui = _read_scheme_from_gui(tab_widget)
    scheme = scheme_gui or scheme

    df_today = _normalize_portfolio(df_today_raw, scheme)
    # TopN 取 GUI 的值
    topn = _read_topn_from_gui(tab_widget)
    if "rank" in df_today.columns and df_today["rank"].notna().any():
        df_today = df_today.head(topn)
    else:
        df_today = df_today.head(topn)

    # 交易清单
    df_trades = _build_trades(df_today_raw, df_prev_raw, scheme)

    # 渲染
    if top_view is not None:
        _set_table(top_view, df_today)
    if trades_view is not None:
        _set_table(trades_view, df_trades)

# ---- 将渲染钩到 Tab 切换（进到“组合与交易”就刷新一次） ----
def hook_output_rendering(main_window):
    # 尝试找到 QTabWidget
    tabs = main_window.findChildren(QTabWidget)
    if not tabs:
        return
    tabw = tabs[0]

    def _on_changed(i: int):
        try:
            title = tabw.tabText(i)
            if "组合与交易" in title:   # 你的中文标签就是这个
                render_portfolio_tab(tabw)
        except Exception:
            pass

    tabw.currentChanged.connect(_on_changed)
    # 立即刷一次（如果当前就在该页）
    try:
        if "组合与交易" in tabw.tabText(tabw.currentIndex()):
            render_portfolio_tab(tabw)
    except Exception:
        pass
