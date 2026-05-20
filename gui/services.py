from __future__ import annotations

import os
import sys
from typing import Iterable

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTableView


def dataframe_to_model(df: pd.DataFrame | None) -> QStandardItemModel:
    model = QStandardItemModel()
    if df is None or df.empty:
        return model
    cols = [str(c) for c in df.columns]
    model.setColumnCount(len(cols))
    model.setHorizontalHeaderLabels(cols)
    for _, row in df.iterrows():
        items = []
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                text = ""
            elif isinstance(val, float):
                text = f"{val:.9g}"
            else:
                text = str(val)
            item = QStandardItem(text)
            item.setEditable(False)
            if isinstance(val, (int, float)) and not pd.isna(val):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            else:
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            items.append(item)
        model.appendRow(items)
    return model


def load_csv(csv_path: str | None) -> pd.DataFrame:
    if not csv_path or not os.path.exists(csv_path):
        return pd.DataFrame()
    try:
        return pd.read_csv(csv_path)
    except UnicodeDecodeError:
        return pd.read_csv(csv_path, encoding="gbk")



def apply_dataframe(view: QTableView, df: pd.DataFrame | None) -> None:
    model = dataframe_to_model(df)
    view.setModel(model)
    view.setSortingEnabled(True)
    try:
        view.resizeColumnsToContents()
        view.horizontalHeader().setStretchLastSection(True)
    except Exception:
        pass


def open_path(path: str) -> None:
    if not path:
        return
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}"')


def format_metric_dict(metrics: dict) -> str:
    if not metrics:
        return "结果摘要：-"
    def pct(v):
        try:
            return f"{float(v):.2%}"
        except Exception:
            return "-"
    def num(v):
        try:
            return f"{float(v):.2f}"
        except Exception:
            return "-"
    return (
        f"结果摘要：CAGR={pct(metrics.get('cagr'))} | Sharpe={num(metrics.get('sharpe'))} | "
        f"MaxDD={pct(metrics.get('max_drawdown'))} | Vol={pct(metrics.get('vol'))}"
    )
