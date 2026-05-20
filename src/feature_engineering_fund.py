# -*- coding: utf-8 -*-
from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd

TRADING_DAYS = 252
REQUIRED_COLUMNS = ["fund_code", "ann_return", "ann_vol", "down_vol", "sharpe", "ir", "mdd"]


def _mdd_from_returns(returns: pd.Series) -> float:
    if returns is None or returns.empty:
        return np.nan
    wealth = (1.0 + returns.fillna(0.0)).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    return float(drawdown.min()) if len(drawdown) else np.nan


def _auto_equal_bench(df_ret: pd.DataFrame) -> pd.Series:
    if df_ret is None or df_ret.empty:
        return pd.Series(dtype=float, name="bench_ret")
    bench = df_ret.groupby("date")["ret"].mean().rename("bench_ret")
    bench.index = pd.to_datetime(bench.index)
    return bench


def _resolve_bench(args, kwargs, df_ret: pd.DataFrame) -> pd.Series:
    if isinstance(kwargs.get("bench"), pd.Series):
        return kwargs["bench"]
    for item in args:
        if isinstance(item, pd.Series):
            return item
    return _auto_equal_bench(df_ret)


def compute_factors(df_ret: pd.DataFrame, *args, window: int = 126, min_obs: int | None = None, **kwargs) -> pd.DataFrame:
    if df_ret is None or df_ret.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    bench = _resolve_bench(args, kwargs, df_ret)
    min_obs = int(min_obs or max(30, int(window * 0.5)))

    df = df_ret.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["ret"] = pd.to_numeric(df["ret"], errors="coerce")
    df = df.dropna(subset=["date", "ret"])

    bench = bench.copy()
    bench.index = pd.to_datetime(bench.index)
    df = df.merge(bench.rename("bench_ret"), left_on="date", right_index=True, how="left")
    df["bench_ret"] = pd.to_numeric(df["bench_ret"], errors="coerce").fillna(0.0)
    df["excess_ret"] = df["ret"] - df["bench_ret"]

    rows = []
    for code, group in df.groupby("fund_code", sort=False):
        group = group.sort_values("date")
        if len(group) < min_obs:
            continue
        sample = group.tail(window)
        r = sample["ret"].astype(float)
        ex = sample["excess_ret"].astype(float)

        mu = r.mean()
        sigma = r.std(ddof=0)
        down = r[r < 0].std(ddof=0)
        ex_sigma = ex.std(ddof=0)

        ann_return = float(mu * TRADING_DAYS) if np.isfinite(mu) else np.nan
        ann_vol = float(sigma * sqrt(TRADING_DAYS)) if np.isfinite(sigma) else np.nan
        down_vol = float(down * sqrt(TRADING_DAYS)) if np.isfinite(down) else np.nan
        sharpe = float(mu / sigma * sqrt(TRADING_DAYS)) if sigma and np.isfinite(sigma) and sigma > 0 else np.nan
        ir = float(ex.mean() / ex_sigma * sqrt(TRADING_DAYS)) if ex_sigma and np.isfinite(ex_sigma) and ex_sigma > 0 else np.nan

        rows.append(
            {
                "fund_code": str(code),
                "ann_return": ann_return,
                "ann_vol": ann_vol,
                "down_vol": down_vol,
                "sharpe": sharpe,
                "ir": ir,
                "mdd": float(_mdd_from_returns(r)),
            }
        )

    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)
