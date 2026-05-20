# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

try:
    from sklearn.covariance import LedoitWolf
except Exception:
    LedoitWolf = None

try:
    from . import config as CFG
    TOP_N_FUNDS = int(getattr(CFG, "TOP_N_FUNDS", 5))
    OUTPUT_DIR = Path(getattr(CFG, "OUTPUT_DIR", Path(__file__).resolve().parents[1] / "output"))
    IV_LOOKBACK_MAX = int(getattr(CFG, "IV_LOOKBACK_MAX", 60))
    IV_LOOKBACK_MIN = int(getattr(CFG, "IV_LOOKBACK_MIN", 20))
    MAX_WEIGHT = float(getattr(CFG, "OPTIMIZER_MAX_WEIGHT", 0.45))
    MIN_WEIGHT = float(getattr(CFG, "OPTIMIZER_MIN_WEIGHT", 0.0))
    RISK_AVERSION = float(getattr(CFG, "OPTIMIZER_RISK_AVERSION", 4.0))
    SCORE_TILT = float(getattr(CFG, "OPTIMIZER_SCORE_TILT", 0.03))
    TURNOVER_PENALTY = float(getattr(CFG, "OPTIMIZER_TURNOVER_PENALTY", 0.15))
    L2_PENALTY = float(getattr(CFG, "OPTIMIZER_L2_PENALTY", 0.01))
    TARGET_VOL = float(getattr(CFG, "OPTIMIZER_TARGET_VOL", 0.0))
    COV_LOOKBACK = int(getattr(CFG, "OPTIMIZER_COV_LOOKBACK", 126))
except Exception:
    TOP_N_FUNDS, IV_LOOKBACK_MAX, IV_LOOKBACK_MIN = 5, 60, 20
    OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
    MAX_WEIGHT, MIN_WEIGHT = 0.45, 0.0
    RISK_AVERSION, SCORE_TILT, TURNOVER_PENALTY, L2_PENALTY = 4.0, 0.03, 0.15, 0.01
    TARGET_VOL, COV_LOOKBACK = 0.0, 126

from .dao import upsert_df

TRADING_DAYS = 252


@dataclass
class OptimizerResult:
    weights: pd.Series
    expected_return_ann: float
    expected_vol_ann: float
    marginal_risk: pd.Series
    risk_contribution: pd.Series
    risk_contribution_pct: pd.Series
    status: str


def _robust_inverse_vol(df_ret: pd.DataFrame, top_codes: list[str]) -> pd.Series:
    if df_ret is None or df_ret.empty or not top_codes:
        return pd.Series(dtype=float)
    sub = df_ret[df_ret["fund_code"].isin(top_codes)].copy()
    cnt = sub.groupby("fund_code")["date"].nunique()
    if cnt.empty:
        return pd.Series(dtype=float)
    lookback = int(min(IV_LOOKBACK_MAX, max(IV_LOOKBACK_MIN, cnt.median())))
    recent = sub.sort_values("date").groupby("fund_code").tail(lookback)
    vol = recent.groupby("fund_code")["ret"].std(ddof=0)
    vol = (vol + 1e-8).replace(0, np.nan)
    iv = (1.0 / vol).replace([np.inf, -np.inf], np.nan).dropna()
    if iv.empty:
        return pd.Series(dtype=float)
    w = iv / iv.sum()
    return w.reindex(top_codes).fillna(0.0)


def _prepare_candidates(df_scores: pd.DataFrame, top_n: int) -> pd.DataFrame:
    cols = [c for c in ["fund_code", "score", "rank", "ann_return", "ann_vol", "down_vol", "mdd", "sharpe", "ir"] if c in df_scores.columns]
    top = (
        df_scores.sort_values(["score", "fund_code"], ascending=[False, True])
        .head(top_n)
        .loc[:, cols]
        .copy()
    )
    top["fund_code"] = top["fund_code"].astype(str)
    return top.reset_index(drop=True)


def _returns_matrix(df_ret: pd.DataFrame, codes: list[str], lookback: int) -> pd.DataFrame:
    if df_ret is None or df_ret.empty or not codes:
        return pd.DataFrame(columns=codes)
    sub = df_ret[df_ret["fund_code"].isin(codes)].copy()
    if sub.empty:
        return pd.DataFrame(columns=codes)
    mat = (
        sub.pivot_table(index="date", columns="fund_code", values="ret", aggfunc="last")
        .sort_index()
        .tail(max(lookback, IV_LOOKBACK_MIN))
    )
    mat = mat.reindex(columns=codes)
    mat = mat.fillna(0.0)
    return mat


def _estimate_expected_returns(candidates: pd.DataFrame, ret_mat: pd.DataFrame) -> pd.Series:
    codes = candidates["fund_code"].tolist()
    hist_mu = ret_mat.mean().reindex(codes).fillna(0.0) * TRADING_DAYS
    vol_ann = ret_mat.std(ddof=0).reindex(codes).fillna(ret_mat.stack().std(ddof=0) if not ret_mat.empty else 0.15) * np.sqrt(TRADING_DAYS)

    if "ann_return" in candidates.columns:
        fac_mu = pd.to_numeric(candidates.set_index("fund_code")["ann_return"], errors="coerce").reindex(codes)
        hist_mu = 0.5 * hist_mu + 0.5 * fac_mu.fillna(hist_mu)

    score = pd.to_numeric(candidates.set_index("fund_code")["score"], errors="coerce").reindex(codes).fillna(0.0)
    score_std = float(score.std(ddof=0)) if len(score) > 1 else 0.0
    if score_std > 1e-12:
        score_z = (score - score.mean()) / score_std
    else:
        score_z = score * 0.0
    mu = hist_mu + SCORE_TILT * score_z * vol_ann.clip(lower=0.05)
    return mu.astype(float)


def _estimate_covariance(ret_mat: pd.DataFrame) -> np.ndarray:
    if ret_mat.empty:
        return np.eye(1) * 1e-4
    x = ret_mat.to_numpy(dtype=float)
    if x.ndim != 2 or x.shape[1] == 0:
        return np.eye(1) * 1e-4
    if x.shape[0] >= max(20, x.shape[1] + 2) and LedoitWolf is not None:
        try:
            cov = LedoitWolf().fit(x).covariance_
        except Exception:
            cov = np.cov(x, rowvar=False, ddof=0)
    else:
        cov = np.cov(x, rowvar=False, ddof=0)
    if np.ndim(cov) == 0:
        cov = np.array([[float(cov)]], dtype=float)
    cov = np.asarray(cov, dtype=float)
    ridge = max(1e-8, float(np.trace(cov)) / max(len(cov), 1) * 1e-4)
    cov = cov + np.eye(cov.shape[0]) * ridge
    return cov


def _optimize_constrained_weights(mu_ann: pd.Series, cov_daily: np.ndarray, anchor: pd.Series) -> OptimizerResult:
    codes = mu_ann.index.tolist()
    n = len(codes)
    if n == 0:
        return OptimizerResult(pd.Series(dtype=float), 0.0, 0.0, pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float), "empty")
    if n == 1:
        w = pd.Series([1.0], index=codes)
        vol_ann = float(np.sqrt(max(cov_daily[0, 0], 0.0) * TRADING_DAYS)) if cov_daily.size else 0.0
        return OptimizerResult(w, float(mu_ann.iloc[0]), vol_ann, pd.Series([vol_ann], index=codes), pd.Series([vol_ann], index=codes), pd.Series([1.0], index=codes), "single_asset")

    mu = mu_ann.to_numpy(dtype=float) / TRADING_DAYS
    cov = np.asarray(cov_daily, dtype=float)
    anchor_vec = anchor.reindex(codes).fillna(0.0).to_numpy(dtype=float)
    x0 = anchor_vec.copy()
    if x0.sum() <= 0:
        x0 = np.repeat(1.0 / n, n)
    x0 = x0 / x0.sum()

    bounds = [(MIN_WEIGHT, MAX_WEIGHT) for _ in range(n)]
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if TARGET_VOL and TARGET_VOL > 0:
        target_daily_var = (TARGET_VOL ** 2) / TRADING_DAYS
        constraints.append({"type": "ineq", "fun": lambda w: target_daily_var - float(w @ cov @ w)})

    def objective(w: np.ndarray) -> float:
        quad = 0.5 * RISK_AVERSION * float(w @ cov @ w)
        reward = -float(mu @ w)
        turnover = TURNOVER_PENALTY * float(np.sum((w - anchor_vec) ** 2))
        l2 = L2_PENALTY * float(np.sum(w ** 2))
        return quad + reward + turnover + l2

    result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints, options={"maxiter": 500, "ftol": 1e-12})
    if not result.success or np.any(np.isnan(result.x)):
        w = x0
        status = f"fallback:{getattr(result, 'message', 'solver_failed')}"
    else:
        w = np.clip(result.x, 0.0, None)
        s = w.sum()
        w = w / s if s > 0 else x0
        status = "optimal"

    w_s = pd.Series(w, index=codes)
    port_var_daily = float(w @ cov @ w)
    exp_ret_ann = float(mu_ann @ w_s)
    exp_vol_ann = float(np.sqrt(max(port_var_daily, 0.0) * TRADING_DAYS))

    sigma_w = cov @ w
    port_vol_daily = float(np.sqrt(max(port_var_daily, 1e-18)))
    marginal = pd.Series(sigma_w / port_vol_daily, index=codes)
    rc = w_s * marginal
    rc_sum = float(rc.sum())
    rc_pct = rc / rc_sum if abs(rc_sum) > 1e-18 else rc * 0.0
    return OptimizerResult(w_s, exp_ret_ann, exp_vol_ann, marginal, rc, rc_pct, status)


def _blended_weights(w_eq: pd.Series, w_rp: pd.Series, w_opt: pd.Series) -> pd.Series:
    out = 0.20 * w_eq.add(w_rp, fill_value=0.0) + 0.60 * w_opt.add(0.0, fill_value=0.0)
    out = out.reindex(sorted(out.index)).fillna(0.0)
    s = out.sum()
    return out / s if s > 0 else out


def build_and_save_portfolio(
    df_scores: pd.DataFrame,
    df_ret: pd.DataFrame,
    date_str: str,
    *,
    export_csv: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    cols = [
        "date", "fund_code", "weight_equal", "weight_risk_parity", "weight_mixed", "weight_optimized",
        "score", "rank", "expected_return_ann", "expected_vol_ann", "marginal_risk", "risk_contribution",
        "risk_contribution_pct", "optimizer_status",
    ]
    if df_scores is None or df_scores.empty:
        return pd.DataFrame(columns=cols)

    candidates = _prepare_candidates(df_scores, TOP_N_FUNDS)
    top_codes = candidates["fund_code"].tolist()
    n = len(top_codes)
    if n == 0:
        return pd.DataFrame(columns=cols)

    w_eq = pd.Series(1.0 / n, index=top_codes, name="weight_equal")
    w_rp = _robust_inverse_vol(df_ret, top_codes).reindex(top_codes).fillna(0.0)
    if w_rp.sum() <= 0:
        w_rp = w_eq.copy()
    else:
        w_rp = w_rp / w_rp.sum()

    ret_mat = _returns_matrix(df_ret, top_codes, COV_LOOKBACK)
    cov = _estimate_covariance(ret_mat)
    mu_ann = _estimate_expected_returns(candidates, ret_mat)
    opt = _optimize_constrained_weights(mu_ann, cov, anchor=w_rp)
    w_opt = opt.weights.reindex(top_codes).fillna(0.0)
    w_mix = _blended_weights(w_eq, w_rp, w_opt).reindex(top_codes).fillna(0.0)

    out = pd.DataFrame({
        "date": date_str,
        "fund_code": top_codes,
        "weight_equal": w_eq.values,
        "weight_risk_parity": w_rp.values,
        "weight_mixed": w_mix.values,
        "weight_optimized": w_opt.values,
        "expected_return_ann": opt.expected_return_ann,
        "expected_vol_ann": opt.expected_vol_ann,
        "marginal_risk": opt.marginal_risk.reindex(top_codes).values,
        "risk_contribution": opt.risk_contribution.reindex(top_codes).values,
        "risk_contribution_pct": opt.risk_contribution_pct.reindex(top_codes).values,
        "optimizer_status": opt.status,
    })
    if {"fund_code", "score", "rank"}.issubset(df_scores.columns):
        out = out.merge(df_scores[[c for c in ["fund_code", "score", "rank"] if c in df_scores.columns]], on="fund_code", how="left")

    upsert_df("portfolio_results", out, pk_cols=["date", "fund_code"])

    if export_csv:
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            outfile = OUTPUT_DIR / f"portfolio_fund_{date_str}.csv"
            out.to_csv(outfile, index=False, encoding="utf-8-sig")
            if verbose:
                print(f"[导出] {outfile}")
        except Exception as exc:
            print(f"[WARN] 导出 CSV 失败：{exc}")

    if verbose:
        try:
            disp = out[["fund_code", "weight_optimized", "weight_mixed", "weight_risk_parity", "weight_equal", "score", "rank", "risk_contribution_pct"]]
            print("[组合] 当日持仓（按优化权重）")
            print(disp.sort_values("weight_optimized", ascending=False).to_string(index=False))
            print(
                f"[优化器] status={opt.status} | ex-ante return={opt.expected_return_ann:.2%} | "
                f"ex-ante vol={opt.expected_vol_ann:.2%}"
            )
        except Exception:
            pass

    return out.reindex(columns=[c for c in cols if c in out.columns])
