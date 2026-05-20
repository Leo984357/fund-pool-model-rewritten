from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

try:
    from . import config as CFG
    FACTOR_WEIGHTS = dict(getattr(CFG, "FACTOR_WEIGHTS", {}))
    PURE_SHARPE_ONLY = bool(getattr(CFG, "PURE_SHARPE_ONLY", False))
except Exception:
    FACTOR_WEIGHTS = {
        "ann_return": 0.35,
        "ann_vol": -0.15,
        "down_vol": -0.10,
        "mdd": -0.10,
        "sharpe": 0.35,
        "ir": 0.15,
    }
    PURE_SHARPE_ONLY = False


def _winsor(series: pd.Series, p: float = 0.01) -> pd.Series:
    if series.notna().sum() < 5:
        return series
    lo, hi = series.quantile(p), series.quantile(1 - p)
    return series.clip(lower=lo, upper=hi)


def _robust_zscore(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        std = x.std(ddof=0)
        if std and np.isfinite(std):
            return (x - x.mean()) / std
        return x - x.mean()
    return (x - med) / (1.4826 * mad)


def score_funds(df_fac: pd.DataFrame) -> pd.DataFrame:
    if df_fac is None or df_fac.empty:
        return pd.DataFrame(columns=["fund_code", "score", "rank"])

    df = df_fac.copy()
    cols = [col for col in FACTOR_WEIGHTS if col in df.columns]
    if PURE_SHARPE_ONLY and "sharpe" in df.columns:
        cols = ["sharpe"]
    if not cols:
        return pd.DataFrame(columns=["fund_code", "score", "rank"])

    use_cols: List[str] = []
    for col in cols:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().sum() <= 1 or values.nunique(dropna=True) <= 1:
            continue
        scaled = _robust_zscore(_winsor(values))
        df[col] = scaled.fillna(0.0)
        use_cols.append(col)

    if not use_cols:
        return pd.DataFrame(columns=["fund_code", "score", "rank"])

    abs_weight_sum = 0.0
    df["score"] = 0.0
    for col in use_cols:
        weight = float(FACTOR_WEIGHTS.get(col, 0.0))
        if weight == 0:
            continue
        df["score"] += weight * df[col]
        abs_weight_sum += abs(weight)
    if abs_weight_sum > 0:
        df["score"] = df["score"] / abs_weight_sum

    df = df.sort_values(["score", "fund_code"], ascending=[False, True]).reset_index(drop=True)
    df["rank"] = pd.Series(range(1, len(df) + 1), dtype="int64")
    return df[["fund_code", "score", "rank"] + use_cols]
