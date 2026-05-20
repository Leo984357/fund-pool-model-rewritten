# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("FUND_BACKFILL_DAYS", "10")

ROOT = Path(__file__).resolve().parent
DB = ROOT / "db" / "fund_db.sqlite"


def check(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)
    print(f"[OK] {message}")


print("[1/5] run daily pipeline")
from run_daily_fund import main as run_daily
result = run_daily()
check(result.df_scores is not None and not result.df_scores.empty, "daily pipeline produced scores")
check(result.df_portfolio is not None and not result.df_portfolio.empty, "daily pipeline produced portfolio")
check(result.report_path is not None and Path(result.report_path).exists(), "daily pipeline produced HTML report")
check(Path(str(result.report_path).replace('.html', '.md')).exists(), "daily pipeline produced Markdown report")
check(Path(str(result.report_path).replace('.html', '.json')).exists(), "daily pipeline produced JSON report")

print("[2/5] run backtest")
from run_backtest_fund import main as run_backtest
curve = run_backtest()
check(curve is not None and not curve.empty, "backtest returned non-empty curve")
check({"date", "equity"}.issubset(curve.columns), "backtest curve has required columns")

print("[3/5] inspect database schema")
check(DB.exists(), "database exists")
with sqlite3.connect(DB) as con:
    cols = {row[1] for row in con.execute('PRAGMA table_info("portfolio_results")').fetchall()}
required_cols = {
    "date", "fund_code", "weight_equal", "weight_risk_parity", "weight_mixed", "weight_optimized",
    "score", "rank", "expected_return_ann", "expected_vol_ann", "risk_contribution_pct", "optimizer_status",
}
check(required_cols.issubset(cols), "portfolio_results contains upgraded optimizer/report columns")

print("[4/5] verify output artifacts")
output_dir = ROOT / "output"
check((output_dir / "backtest_fund_nav.csv").exists(), "backtest CSV exists in output/")
check((output_dir / f"scores_{result.run_date}.csv").exists(), "score CSV exists in output/")
check((output_dir / f"portfolio_fund_{result.run_date}.csv").exists(), "portfolio CSV exists in output/")

print("[5/5] GUI smoke test")
try:
    from PySide6.QtWidgets import QApplication
    from gui.widgets.MainWindow import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    check(window.windowTitle() != "", "GUI main window instantiates successfully")
    window.close()
except ModuleNotFoundError:
    import ast

    gui_files = [
        ROOT / "gui" / "app.py",
        ROOT / "gui" / "widgets" / "MainWindow.py",
        ROOT / "gui" / "widgets" / "main_window_v2.py",
        ROOT / "gui" / "workers" / "RunStrategyWorker.py",
    ]
    for fp in gui_files:
        ast.parse(fp.read_text(encoding="utf-8"))
    print("[WARN] PySide6 未安装，改为完成 GUI 语法级校验。")
    check(True, "GUI source files pass syntax validation")

print("\nValidation completed successfully.")
