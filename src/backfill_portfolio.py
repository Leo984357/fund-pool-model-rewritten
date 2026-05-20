# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import C
from .data_loader_fund import load_nav, make_equal_benchmark, to_returns
from .feature_engineering_fund import compute_factors
from .optimizer import build_and_save_portfolio
from .scoring_model import score_funds
from .universe_fund import load_universe_fund


def _export_backtest_curve(df: pd.DataFrame, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "backtest_fund_nav.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[OK] 导出回测曲线：{path}")
    return path


def backfill(n_days: int = 126, verbose: bool = True) -> int:
    n_days = int(n_days)
    if n_days <= 0:
        return 0

    universe = load_universe_fund(limit=C.universe_limit)
    df_nav = load_nav(universe, since=C.since_date)
    df_ret = to_returns(df_nav)
    if df_ret.empty:
        if verbose:
            print("[BACKFILL][WARN] 无可用收益序列，跳过。")
        return 0

    all_dates = sorted(pd.to_datetime(df_ret["date"].dropna().unique()))
    if not all_dates:
        return 0

    backfill_dates = all_dates[-n_days:]
    processed = 0
    for dt_value in backfill_dates:
        hist = df_ret[df_ret["date"] <= dt_value].copy()
        if hist.empty:
            continue
        bench = make_equal_benchmark(hist)
        df_fac = compute_factors(hist, bench=bench, window=C.window_days, min_obs=C.min_history_days)
        if df_fac.empty:
            continue
        df_scores = score_funds(df_fac)
        if df_scores.empty:
            continue
        build_and_save_portfolio(
            df_scores,
            hist,
            date_str=pd.Timestamp(dt_value).strftime("%Y-%m-%d"),
            export_csv=False,
            verbose=False,
        )
        processed += 1
        if verbose and (processed == 1 or processed % 20 == 0 or processed == len(backfill_dates)):
            print(f"[BACKFILL] processed {processed}/{len(backfill_dates)}")
    return processed


def backfill_equity_from_latest_weights(
    db_path: str | Path = None,
    nav_table: str | None = None,
    portfolio_table: str | None = None,
    weight_col: str | None = None,
    days: int | None = None,
    out_dir: str | Path | None = None,
) -> pd.DataFrame:
    from .backtest_quick_fund import backtest_from_db

    df = backtest_from_db(
        db_path=db_path or C.DB_PATH,
        nav_table=nav_table or C.NAV_TABLE,
        portfolio_table=portfolio_table or C.PORTFOLIO_TABLE,
        weight_col=weight_col or C.WEIGHT_SCHEME,
        since_date=C.SINCE_DATE,
        out_dir=out_dir or C.OUTPUT_DIR,
    )
    if days and len(df) > days:
        df = df.tail(int(days)).reset_index(drop=True)
    _export_backtest_curve(df, Path(out_dir or C.OUTPUT_DIR))
    return df


def main() -> None:
    print("[BACKFILL] 生成最近窗口的历史组合与净值曲线 ...")
    try:
        processed = backfill(n_days=C.window_days, verbose=True)
        print(f"[BACKFILL] 历史组合回填完成：{processed} 个交易日")
        _ = backfill_equity_from_latest_weights(
            db_path=C.DB_PATH,
            nav_table=C.NAV_TABLE,
            portfolio_table=C.PORTFOLIO_TABLE,
            weight_col=C.WEIGHT_SCHEME,
            days=C.window_days,
            out_dir=C.OUTPUT_DIR,
        )
        print("[BACKFILL] done.")
    except Exception as exc:
        print("[BACKFILL][ERROR]", repr(exc))
