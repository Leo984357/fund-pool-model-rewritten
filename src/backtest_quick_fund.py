# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd

from .config import C


def _read_sql(conn, sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, conn, parse_dates=["date"])


def _ensure_equity_csv(df_equity: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "backtest_fund_nav.csv"
    df_equity.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path


def backtest_from_db(
    db_path: str | Path = None,
    nav_table: str | None = None,
    portfolio_table: str | None = None,
    weight_col: str | None = None,
    since_date: str | None = None,
    out_dir: str | Path | None = None,
) -> pd.DataFrame:
    db_path = Path(db_path or C.DB_PATH)
    nav_table = nav_table or C.NAV_TABLE
    portfolio_table = portfolio_table or C.PORTFOLIO_TABLE
    weight_col = weight_col or C.WEIGHT_SCHEME
    since_date = since_date or C.SINCE_DATE
    out_dir = Path(out_dir or C.OUTPUT_DIR)

    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在：{db_path}")

    with sqlite3.connect(db_path) as conn:
        sql_w = f"""
        SELECT date, fund_code, {weight_col} AS weight
        FROM {portfolio_table}
        WHERE date >= date('{since_date}')
        """
        w = _read_sql(conn, sql_w)
        if w.empty:
            raise ValueError(f"{portfolio_table} 自 {since_date} 起无权重（列={weight_col}）。")

        w = w.pivot_table(index="date", columns="fund_code", values="weight", aggfunc="last").sort_index()
        w = w.ffill().fillna(0.0)
        row_sum = w.abs().sum(axis=1)
        row_sum[row_sum == 0.0] = 1.0
        w = w.div(row_sum, axis=0)

        sql_n = f"SELECT date, fund_code, nav FROM {nav_table}"
        nav = _read_sql(conn, sql_n)
        if nav.empty:
            raise ValueError(f"{nav_table} 无净值数据。")

        px = nav.pivot_table(index="date", columns="fund_code", values="nav", aggfunc="last").sort_index()
        px = px.reindex(w.index.union(px.index)).sort_index()
        rets = px.pct_change(fill_method=None)
        rets = rets.reindex(w.index).fillna(0.0)

        common_cols = [c for c in w.columns if c in rets.columns]
        w = w.reindex(columns=common_cols).fillna(0.0)
        rets = rets.reindex(columns=common_cols).fillna(0.0)
        if not common_cols:
            raise ValueError("权重与净值无重合基金代码。")

        port_ret = (w.shift(1).fillna(0.0) * rets).sum(axis=1)
        benchmark_ret = rets.mean(axis=1).fillna(0.0)

        equity = (1.0 + port_ret).cumprod()
        benchmark = (1.0 + benchmark_ret).cumprod()
        df_equity = pd.DataFrame({"date": equity.index, "equity": equity.values, "benchmark": benchmark.values})

        _ensure_equity_csv(df_equity, Path(out_dir))
        return df_equity


def main(weight_col: str | None = None) -> pd.DataFrame:
    weight_col = weight_col or C.WEIGHT_SCHEME
    print(f"[BT] 使用权重列：{weight_col}")
    try:
        df = backtest_from_db(
            db_path=C.DB_PATH,
            nav_table=C.NAV_TABLE,
            portfolio_table=C.PORTFOLIO_TABLE,
            weight_col=weight_col,
            since_date=C.SINCE_DATE,
            out_dir=C.OUTPUT_DIR,
        )
        print("[BT] 回测完成，已产出 backtest_fund_nav.csv")
        return df
    except Exception as exc:
        print("[BT][ERROR]", repr(exc))
        return pd.DataFrame(columns=["date", "equity", "benchmark"])
