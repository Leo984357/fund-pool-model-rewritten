# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from . import config as CFG
from .config import C
from .data_loader_fund import load_nav, make_equal_benchmark, to_returns
from .feature_engineering_fund import compute_factors
from .optimizer import build_and_save_portfolio
from .reporting import generate_daily_report
from .risk_checks import basic_risk_sanity
from .scoring_model import score_funds
from .universe_fund import load_universe_fund

try:
    from .parallel_fetch import fetch_and_save_nav_batch
except Exception:
    fetch_and_save_nav_batch = None

try:
    from .backfill_portfolio import backfill as backfill_portfolio
except Exception:
    backfill_portfolio = None


@dataclass
class PipelineResult:
    run_date: str
    universe: list[str]
    df_nav: pd.DataFrame
    df_ret: pd.DataFrame
    df_factors: pd.DataFrame
    df_scores: pd.DataFrame
    df_portfolio: pd.DataFrame
    risk_warnings: list[str]
    score_path: Path | None
    portfolio_path: Path | None
    report_path: Path | None


def today_ymd() -> str:
    return date.today().isoformat()


def run_daily_pipeline() -> PipelineResult:
    C.validate()
    run_date = today_ymd()
    print(f"[STEP 0] 运行日：{run_date}")
    CFG.print_summary()

    print(f"[STEP 1] 准备基金池（上限={C.universe_limit}）")
    universe = load_universe_fund(limit=C.universe_limit)
    print(f"[UNIVERSE] 实际数量：{len(universe)} → {universe[:min(5, len(universe))]} ...")

    if fetch_and_save_nav_batch is not None:
        print(f"[STEP 1.5] 尝试抓取净值（workers={C.parallel_workers}, since={C.since_date}）")
        try:
            fetch_and_save_nav_batch(universe, since=C.since_date, max_workers=C.parallel_workers)
        except Exception as exc:
            print(f"[WARN] 抓取失败，将直接使用本地数据库：{exc}")

    print("[STEP 2] 从库读取净值并转日收益")
    df_nav = load_nav(universe, since=C.since_date)
    df_ret = to_returns(df_nav)
    bench = make_equal_benchmark(df_ret)

    print("[STEP 3] 计算因子")
    df_factors = compute_factors(df_ret, bench=bench, window=C.window_days, min_obs=C.min_history_days)

    print("[STEP 4] 打分")
    df_scores = score_funds(df_factors)
    score_path = None
    if df_scores is not None and not df_scores.empty:
        score_path = Path(C.output_dir) / f"scores_{run_date}.csv"
        df_scores.to_csv(score_path, index=False, encoding="utf-8-sig")
        print(f"[导出] {score_path}")
    else:
        print("[WARN] 打分结果为空")

    print("[STEP 5] 构建组合并落库")
    df_port = build_and_save_portfolio(df_scores, df_ret, date_str=run_date, export_csv=True, verbose=True)
    portfolio_path = Path(C.output_dir) / f"portfolio_fund_{run_date}.csv"
    if df_port is None or df_port.empty:
        print("[WARN] 组合为空，请检查基金池、历史长度或抓取结果")

    backfill_days = int(os.getenv("FUND_BACKFILL_DAYS", "0") or 0)
    if backfill_days > 0 and backfill_portfolio is not None:
        print(f"[STEP 6] 回填最近 {backfill_days} 个交易日的组合")
        try:
            processed = backfill_portfolio(n_days=backfill_days, verbose=True)
            print(f"[BACKFILL] 完成 {processed} 个交易日")
        except Exception as exc:
            print(f"[WARN] 历史回填失败：{exc}")

    risk_warnings = basic_risk_sanity(df_scores, df_port)
    if risk_warnings:
        print("[RISK] 风险提示：")
        for item in risk_warnings:
            print(" -", item)

    print("[STEP 7] 生成研究报告")
    report_dir = Path(C.output_dir) / "reports"
    report_path = generate_daily_report(
        run_date,
        df_scores,
        df_port,
        risk_warnings,
        report_dir,
        universe=universe,
        df_factors=df_factors,
        df_ret=df_ret,
        weight_col=C.weight_scheme,
    )
    print(f"[导出] {report_path}")

    print("====== 全流程完成 ======")
    return PipelineResult(
        run_date=run_date,
        universe=universe,
        df_nav=df_nav,
        df_ret=df_ret,
        df_factors=df_factors,
        df_scores=df_scores,
        df_portfolio=df_port,
        risk_warnings=risk_warnings,
        score_path=score_path,
        portfolio_path=portfolio_path if portfolio_path.exists() else None,
        report_path=report_path,
    )
