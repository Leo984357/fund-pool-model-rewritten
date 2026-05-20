# -*- coding: utf-8 -*-
from __future__ import annotations
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

def plot_equity_curve(nav: pd.Series, out_png: Path):
    """
    画累计净值曲线；nav: index=date, values=净值(起点=1)
    """
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(9,4))
    nav.plot()
    plt.title("Portfolio NAV")
    plt.xlabel("Date"); plt.ylabel("NAV")
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()
