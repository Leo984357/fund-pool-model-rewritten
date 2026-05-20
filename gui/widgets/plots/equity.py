# -*- coding: utf-8 -*-
from __future__ import annotations
import pandas as pd
from pathlib import Path
from matplotlib import pyplot as plt

def plot_equity(equity_csv_path: str | Path):
    p = Path(equity_csv_path)
    ax = plt.gca()

    if not p.exists():
        ax.text(0.5, 0.5, "没有找到 equity_curve.csv", ha="center", va="center")
        plt.title("Equity Curve")
        plt.tight_layout()
        return

    try:
        df = pd.read_csv(p)
    except Exception as e:
        ax.text(0.5, 0.5, f"读取失败: {e}", ha="center", va="center")
        plt.title("Equity Curve")
        plt.tight_layout()
        return

    # 容错列名：优先 equity；否则找同义；否则退回第一数值列
    ycol = None
    for c in df.columns:
        if c.lower() in {"equity", "curve", "value", "nav"}:
            ycol = c
            break
    if ycol is None:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if num_cols:
            ycol = num_cols[0]

    if not ycol:
        ax.text(0.5, 0.5, "曲线文件缺少数值列", ha="center", va="center")
        plt.title("Equity Curve")
        plt.tight_layout()
        return

    x = pd.to_datetime(df["date"], errors="coerce") if "date" in df.columns else range(len(df))
    y = df[ycol]

    if y.dropna().empty:
        ax.text(0.5, 0.5, "曲线为空", ha="center", va="center")
        plt.title("Equity Curve")
        plt.tight_layout()
        return

    plt.plot(x, y)
    plt.title("Equity Curve")
    plt.tight_layout()
