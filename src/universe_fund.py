# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .config import C
from .utils import log


def _normalize_codes(obj) -> pd.DataFrame:
    if obj is None:
        return pd.DataFrame(columns=["fund_code"])
    if isinstance(obj, pd.Series):
        series = obj.astype(str)
    elif isinstance(obj, pd.DataFrame):
        column = None
        for name in ["fund_code", "code", "基金代码", "证券代码"]:
            if name in obj.columns:
                column = name
                break
        if column is None:
            for name in obj.columns:
                if obj[name].astype(str).str.contains(r"\d{6}", regex=True).any():
                    column = name
                    break
        column = column or obj.columns[0]
        series = obj[column].astype(str)
    else:
        series = pd.Series(list(obj), dtype=str)
    series = series.str.extract(r"(\d+)", expand=False).dropna().map(lambda x: x.zfill(6))
    return pd.DataFrame({"fund_code": series}).drop_duplicates(subset=["fund_code"]).reset_index(drop=True)


def _read_csv() -> pd.DataFrame:
    path = Path(C.universe_csv)
    if not path.exists():
        return pd.DataFrame(columns=["fund_code"])
    try:
        return _normalize_codes(pd.read_csv(path, dtype=str))
    except Exception as exc:
        log(f"[UNIVERSE][WARN] 读取 CSV 失败：{exc}")
        return pd.DataFrame(columns=["fund_code"])


def _read_db() -> pd.DataFrame:
    db_path = Path(C.db_path)
    if not db_path.exists():
        return pd.DataFrame(columns=["fund_code"])
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query("SELECT DISTINCT fund_code FROM fund_nav_daily", conn)
        return _normalize_codes(df)
    except Exception as exc:
        log(f"[UNIVERSE][INFO] 从 DB 补齐失败：{exc}")
        return pd.DataFrame(columns=["fund_code"])


def _read_akshare(max_rows: int) -> pd.DataFrame:
    try:
        import akshare as ak
    except Exception as exc:
        log(f"[UNIVERSE][INFO] AKShare 不可用：{exc}")
        return pd.DataFrame(columns=["fund_code"])

    candidates = []
    for fn in ["fund_name_em", "fund_etf_fund_daily_em", "fund_lof_fund_daily_em"]:
        if not hasattr(ak, fn):
            continue
        try:
            df = getattr(ak, fn)()
            if isinstance(df, pd.DataFrame) and not df.empty:
                candidates.append(df)
        except Exception as exc:
            log(f"[UNIVERSE][INFO] {fn} 拉取失败：{exc}")
    if not candidates:
        return pd.DataFrame(columns=["fund_code"])
    return _normalize_codes(pd.concat(candidates, ignore_index=True)).head(max_rows)


def load_universe_fund(limit: Optional[int] = None) -> list[str]:
    limit = int(limit or C.universe_limit)
    base = _read_csv()
    if len(base) < limit:
        base = pd.concat([base, _read_db()], ignore_index=True).drop_duplicates(subset=["fund_code"])
    if len(base) < limit:
        base = pd.concat([base, _read_akshare(max_rows=limit * 2)], ignore_index=True).drop_duplicates(subset=["fund_code"])

    base = _normalize_codes(base).head(limit)
    Path(C.universe_csv).parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(C.universe_csv, index=False, encoding="utf-8-sig")
    codes = base["fund_code"].tolist()
    log(f"[UNIVERSE] 返回 {len(codes)} 只基金（上限={limit}）")
    return codes
