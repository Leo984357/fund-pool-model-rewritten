from __future__ import annotations

import pandas as pd


def basic_risk_sanity(df_scores: pd.DataFrame, df_port: pd.DataFrame | None = None) -> list[str]:
    warnings: list[str] = []
    if df_scores is None or df_scores.empty:
        return ["打分结果为空"]

    if "score" not in df_scores.columns:
        return ["得分列缺失"]

    score = pd.to_numeric(df_scores["score"], errors="coerce")
    if score.nunique(dropna=True) <= 3:
        warnings.append("得分区分度较低，建议检查窗口长度、因子有效性或基金池规模。")
    if score.std(ddof=0) < 0.05:
        warnings.append("横截面得分波动很小，组合可能缺乏有效区分。")

    factor_cols = [c for c in df_scores.columns if c not in {"fund_code", "score", "rank"}]
    if not factor_cols:
        warnings.append("除得分外无有效因子列。")

    if df_port is not None and not df_port.empty:
        weight_col = "weight_optimized" if "weight_optimized" in df_port.columns else "weight_mixed"
        weights = pd.to_numeric(df_port.get(weight_col), errors="coerce")
        if weights.notna().sum() > 0 and abs(float(weights.sum()) - 1.0) > 1e-6:
            warnings.append(f"{weight_col} 未严格归一。")
        if weights.notna().sum() > 0 and float(weights.max()) > 0.55:
            warnings.append("组合过度集中，单一基金权重超过 55%。")
        if weights.notna().sum() > 0 and float((weights ** 2).sum()) > 0.40:
            warnings.append("组合集中度偏高，等效持仓数偏低。")
        if "risk_contribution_pct" in df_port.columns:
            rc = pd.to_numeric(df_port["risk_contribution_pct"], errors="coerce").dropna().abs()
            if not rc.empty and float(rc.max()) > 0.60:
                warnings.append("风险贡献过于集中，单一基金主导组合风险。")
        if "optimizer_status" in df_port.columns:
            statuses = set(df_port["optimizer_status"].astype(str).str.lower().unique())
            if any(s.startswith("fallback") for s in statuses):
                warnings.append("优化器未完全收敛，当前权重包含回退方案。")
        if "expected_vol_ann" in df_port.columns:
            ex_vol = pd.to_numeric(df_port["expected_vol_ann"], errors="coerce").dropna()
            if not ex_vol.empty and float(ex_vol.iloc[0]) > 0.35:
                warnings.append("组合前瞻波动率较高，需关注净值回撤风险。")

    return warnings
