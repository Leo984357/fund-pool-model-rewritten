# gui/widgets/RunTable.py
from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTableView

# 默认按这些列做数值排序/清洗
NUMERIC_COLS_DEFAULT: tuple[str, ...] = ("rank", "score", "weight", "delta")


# ---------- 数值清洗 ----------

def _to_number(x) -> float:
    """把 bytes / 'b\"..\"' / 混入符号的字符串都转成 float；失败返回 nan。"""
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    if isinstance(x, (bytes, bytearray)):
        try:
            return float(x.decode("utf-8", "ignore"))
        except Exception:
            s = re.sub(r"[^0-9\.\-]+", "", x.decode("latin1", "ignore"))
            return float(s) if s else np.nan
    s = re.sub(r"[^0-9\.\-]+", "", str(x))
    return float(s) if s else np.nan


def normalize_numeric_cols(
    df: pd.DataFrame,
    numeric_cols: Sequence[str] = NUMERIC_COLS_DEFAULT,
) -> pd.DataFrame:
    """把 df 中的数值列清洗成可排序的真实数值；rank 变成整数（Int64）。"""
    df = df.copy()
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].map(_to_number)
    if "rank" in df.columns:
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").astype("Int64")
    return df


# ---------- Top-N 修剪（按 rank 升序） ----------

def df_fix_topn(
    df: pd.DataFrame,
    top_n: Optional[int] = None,
    numeric_cols: Sequence[str] = NUMERIC_COLS_DEFAULT,
) -> pd.DataFrame:
    """
    1) 数值列清洗（含 rank/score/weight 等）；
    2) 先按 rank 升序，再 head(top_n) 截断（若给了 top_n）。
    3) 若没有 rank，则按 score 降序。
    """
    df = normalize_numeric_cols(df, numeric_cols)

    if "rank" in df.columns:
        df = df.sort_values("rank", kind="stable", ascending=True)
        if top_n is not None:
            df = df.head(int(top_n))
    elif "score" in df.columns:
        df = df.sort_values("score", kind="stable", ascending=False)
        if top_n is not None:
            df = df.head(int(top_n))

    # 仅用于显示的格式化文本（值仍保留为数值以便排序）
    if "score" in df.columns and "_score_disp" not in df.columns:
        df["_score_disp"] = df["score"].map(lambda v: "" if pd.isna(v) else f"{float(v):.6f}")
    if "weight" in df.columns and "_weight_disp" not in df.columns:
        df["_weight_disp"] = df["weight"].map(lambda v: "" if pd.isna(v) else f"{float(v):.8f}")

    return df


# ---------- DataFrame → QTableView（数值排序友好） ----------

def set_table_from_df(
    view: QTableView,
    df: pd.DataFrame,
    numeric_cols: Sequence[str] = NUMERIC_COLS_DEFAULT,
    default_sort_col: Optional[str] = "rank",
    default_sort_order: Qt.SortOrder = Qt.AscendingOrder,
) -> QSortFilterProxyModel:
    """
    把 DataFrame 填进 QTableView：
      - 文本走 DisplayRole，真实数值放到 UserRole（确保排序按数值而不是字符串）；
      - 默认按 rank 升序排（如果存在）。
    """
    df = normalize_numeric_cols(df, numeric_cols)
    model = QStandardItemModel(view)
    model.setColumnCount(len(df.columns))
    model.setHorizontalHeaderLabels(list(df.columns))

    numeric_set = set(numeric_cols)

    for _, row in df.iterrows():
        items: list[QStandardItem] = []
        for col in df.columns:
            it = QStandardItem()

            # 显示文本：若存在 *_disp 列优先用，否则用原值字符串
            disp = row[col]
            if isinstance(col, str) and col.endswith("_disp"):
                disp = row[col]
            elif col in ("score", "weight") and f"_{col}_disp" in df.columns:
                disp = row[f"_{col}_disp"]
            it.setData("" if pd.isna(disp) else str(disp), Qt.DisplayRole)

            # 数值排序：把真实数值塞进 UserRole
            if col in numeric_set:
                try:
                    it.setData(float(row[col]), Qt.UserRole)
                except Exception:
                    it.setData(float("nan"), Qt.UserRole)

            items.append(it)
        model.appendRow(items)

    proxy = QSortFilterProxyModel(view)
    proxy.setSourceModel(model)
    proxy.setSortRole(Qt.UserRole)
    view.setModel(proxy)

    if default_sort_col in df.columns:
        col_idx = list(df.columns).index(default_sort_col) if default_sort_col else 0
        view.sortByColumn(col_idx, default_sort_order)

    view.setSortingEnabled(True)
    view.horizontalHeader().setSortIndicatorShown(True)
    return proxy
