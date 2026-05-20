# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple

import pandas as pd

try:
    from . import config as CFG
    DB_PATH = CFG.DB_PATH
    MIN_HISTORY_DAYS = int(getattr(CFG, "MIN_HISTORY_DAYS", 60))
except Exception:
    DB_PATH, MIN_HISTORY_DAYS = None, 60

FUND_COLS = ["fund_code", "code", "基金代码", "基金代码(6位)", "证券代码"]
DATE_COLS = ["date", "trade_date", "pricedate", "净值日期", "交易日期", "日期"]
NAV_COLS = ["nav", "单位净值", "净值", "nav_unit", "unit_nav", "单位净值(元)", "复权单位净值", "累计净值"]
PREFERRED_TABLES = ["fund_nav_daily", "fund_data_raw", "fund_nav_raw", "fund_nav", "fund_price"]


def _connect() -> sqlite3.Connection:
    if DB_PATH is None:
        raise RuntimeError("config.DB_PATH 未设置")
    return sqlite3.connect(DB_PATH)


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    return [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _pick_first(columns: list[str], candidates: list[str]) -> Optional[str]:
    for item in candidates:
        if item in columns:
            return item
    return None


def _detect_nav_source(conn: sqlite3.Connection) -> Tuple[str, str, str, str]:
    tables = _list_tables(conn)
    order = PREFERRED_TABLES + [t for t in tables if t not in PREFERRED_TABLES]
    for table in order:
        if table not in tables:
            continue
        cols = _table_columns(conn, table)
        fund_col = _pick_first(cols, FUND_COLS)
        date_col = _pick_first(cols, DATE_COLS)
        nav_col = _pick_first(cols, NAV_COLS)
        if fund_col and date_col and nav_col:
            print(f"[DB] 选中净值表: {table} (code={fund_col}, date={date_col}, nav={nav_col})")
            return table, fund_col, date_col, nav_col
    raise RuntimeError(f"未找到净值表，现有表：{tables}")


def _norm_code(value) -> str:
    text = str(value).strip()
    if text == "":
        return text
    try:
        if text.replace(".", "", 1).isdigit() and text.count(".") <= 1:
            return str(int(float(text))).zfill(6)
    except Exception:
        pass
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return digits.zfill(6) if len(digits) <= 6 else digits
    return text


def load_nav(codes: List[str], since: str = "2018-01-01") -> pd.DataFrame:
    if not codes:
        return pd.DataFrame(columns=["fund_code", "date", "nav"])

    requested_codes = {_norm_code(code) for code in codes if str(code).strip() != ""}
    loose_codes = {str(int(code)) for code in requested_codes if code.isdigit()}

    with _connect() as conn:
        table, fund_col, date_col, nav_col = _detect_nav_source(conn)
        bag = list(requested_codes | loose_codes | set(map(str, codes)))
        placeholders = ",".join(["?"] * len(bag))
        sql = (
            f'SELECT "{fund_col}" AS fund_code, "{date_col}" AS date, "{nav_col}" AS nav '
            f'FROM "{table}" WHERE "{date_col}" >= ? AND "{fund_col}" IN ({placeholders})'
        )
        df = pd.read_sql_query(sql, conn, params=[since] + bag)
        if df.empty:
            print("[DB] IN 查询为空，改为按日期读取全表后过滤")
            sql = f'SELECT "{fund_col}" AS fund_code, "{date_col}" AS date, "{nav_col}" AS nav FROM "{table}" WHERE "{date_col}" >= ?'
            df = pd.read_sql_query(sql, conn, params=[since])
        if df.empty:
            print("[DB] 仍为空，起始日期前移 365 天再尝试")
            sql = f'SELECT "{fund_col}" AS fund_code, "{date_col}" AS date, "{nav_col}" AS nav FROM "{table}" WHERE DATE("{date_col}") >= DATE(?, "-365 day")'
            df = pd.read_sql_query(sql, conn, params=[since])

    if df.empty:
        print("[DB] 净值读取为空，请先抓取或检查数据库")
        return pd.DataFrame(columns=["fund_code", "date", "nav"])

    df["fund_code"] = df["fund_code"].map(_norm_code)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna(subset=["fund_code", "date", "nav"])
    df = df[df["fund_code"].isin(requested_codes)]
    df = df.drop_duplicates(subset=["fund_code", "date"]).sort_values(["fund_code", "date"]).reset_index(drop=True)

    lengths = df.groupby("fund_code")["date"].nunique()
    keep = lengths[lengths >= MIN_HISTORY_DAYS].index.tolist()
    if not keep and not lengths.empty:
        print(f"[DB] 历史长度不足 {MIN_HISTORY_DAYS} 天，临时放宽到 >= 2 天")
        keep = lengths[lengths >= 2].index.tolist()
    df = df[df["fund_code"].isin(keep)].reset_index(drop=True)
    print(f"[DB] 净值样本：基金数={len(keep)}，记录数={len(df)}（since={since}）")
    return df


def to_returns(df_nav: pd.DataFrame) -> pd.DataFrame:
    if df_nav is None or df_nav.empty:
        return pd.DataFrame(columns=["fund_code", "date", "ret"])
    df = df_nav.copy().sort_values(["fund_code", "date"])
    df["ret"] = df.groupby("fund_code")["nav"].pct_change(fill_method=None)
    df = df.dropna(subset=["ret"]).reset_index(drop=True)
    return df[["fund_code", "date", "ret"]]


def make_equal_benchmark(df_ret: pd.DataFrame) -> pd.Series:
    if df_ret is None or df_ret.empty:
        return pd.Series(dtype=float, name="bench_ret")
    bench = df_ret.groupby("date")["ret"].mean().rename("bench_ret")
    bench.index = pd.to_datetime(bench.index)
    return bench
