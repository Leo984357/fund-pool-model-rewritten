# -*- coding: utf-8 -*-
from __future__ import annotations
import pandas as pd

def adapt_factor_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    统一/兼容不同名称的因子列（如果你的上游命名不同）。
    不会改变已存在的标准列：ann_return, ann_vol, down_vol, sharpe, ir, mdd
    """
    if df is None or df.empty:
        return df
    mapping = {
        "annual_return":"ann_return",
        "annual_vol":"ann_vol",
        "downside_vol":"down_vol",
        "max_drawdown":"mdd",
        "information_ratio":"ir",
    }
    out = df.copy()
    for old, new in mapping.items():
        if old in out.columns and new not in out.columns:
            out = out.rename(columns={old:new})
    return out
