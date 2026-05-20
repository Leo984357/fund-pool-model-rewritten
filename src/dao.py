# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

try:
    from . import config as CFG
    DB_PATH = Path(CFG.DB_PATH)
    NAV_TABLE = str(getattr(CFG, "NAV_TABLE", "fund_nav_daily"))
    PORTFOLIO_TABLE = str(getattr(CFG, "PORTFOLIO_TABLE", "portfolio_results"))
except Exception:
    DB_PATH = Path(__file__).resolve().parents[1] / "db" / "fund_db.sqlite"
    NAV_TABLE = "fund_nav_daily"
    PORTFOLIO_TABLE = "portfolio_results"

CODE_LIKE = {"fund_code", "code", "基金代码", "基金代码(6位)", "证券代码"}
EXPLICIT_SCHEMA = {
    "fund_nav_daily": """
        CREATE TABLE IF NOT EXISTS fund_nav_daily (
            fund_code TEXT NOT NULL,
            date TEXT NOT NULL,
            nav REAL,
            acc_nav REAL,
            PRIMARY KEY (fund_code, date)
        )
    """,
    "portfolio_results": """
        CREATE TABLE IF NOT EXISTS portfolio_results (
            date TEXT NOT NULL,
            fund_code TEXT NOT NULL,
            weight_equal REAL,
            weight_risk_parity REAL,
            weight_mixed REAL,
            weight_optimized REAL,
            score REAL,
            rank INTEGER,
            expected_return_ann REAL,
            expected_vol_ann REAL,
            marginal_risk REAL,
            risk_contribution REAL,
            risk_contribution_pct REAL,
            optimizer_status TEXT,
            PRIMARY KEY (date, fund_code)
        )
    """,
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=8000;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    return conn


def _norm_code_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        if text.replace(".", "", 1).isdigit() and text.count(".") <= 1:
            return str(int(float(text))).zfill(6)
    except Exception:
        pass
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return digits.zfill(6) if len(digits) <= 6 else digits
    return text


def _python_scalar(value):
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (np.bool_,)):
        return int(bool(value))
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return None
    return value


def _infer_sql_type(col: str, series: pd.Series) -> str:
    if col in CODE_LIKE:
        return "TEXT"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    return "TEXT"


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {row[1] for row in rows}


def _ensure_columns(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    existing = _existing_columns(conn, table)
    for col in df.columns:
        if col in existing:
            continue
        col_type = _infer_sql_type(col, df[col])
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type}')


def _ensure_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame, pk_cols: Sequence[str]) -> None:
    if table in EXPLICIT_SCHEMA:
        conn.execute(EXPLICIT_SCHEMA[table])
        _ensure_columns(conn, table, df)
        return
    col_defs = []
    for col in df.columns:
        col_defs.append(f'"{col}" {_infer_sql_type(col, df[col])}')
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(col_defs)})')
    _ensure_columns(conn, table, df)
    if pk_cols:
        idx_name = f'idx_{table}_{"_".join(pk_cols)}'
        cols_expr = ", ".join(f'"{c}"' for c in pk_cols)
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ({cols_expr})')


def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in CODE_LIKE:
            out[col] = out[col].map(_norm_code_str)
        elif col == "date":
            try:
                out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
            except Exception:
                out[col] = out[col].astype(str)
        else:
            out[col] = out[col].map(_python_scalar)
    return out


def _chunked(rows: Iterable[tuple], size: int = 1000):
    buffer = []
    for row in rows:
        buffer.append(row)
        if len(buffer) >= size:
            yield buffer
            buffer = []
    if buffer:
        yield buffer


def upsert_df(table: str, df: pd.DataFrame, pk_cols: Sequence[str]) -> int:
    if df is None or df.empty:
        return 0
    pk_cols = list(pk_cols)
    cols = list(df.columns)
    non_pk = [col for col in cols if col not in pk_cols]
    prepared = _prepare_df(df)

    with _connect() as conn:
        _ensure_table(conn, table, prepared, pk_cols)
        col_expr = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["?"] * len(cols))
        pk_expr = ", ".join(f'"{c}"' for c in pk_cols)
        update_expr = ", ".join(f'"{c}"=excluded."{c}"' for c in non_pk)
        if update_expr:
            sql = (
                f'INSERT INTO "{table}" ({col_expr}) VALUES ({placeholders}) '
                f'ON CONFLICT({pk_expr}) DO UPDATE SET {update_expr}'
            )
        else:
            sql = f'INSERT OR IGNORE INTO "{table}" ({col_expr}) VALUES ({placeholders})'

        rows = (
            tuple(_python_scalar(prepared.iloc[i][col]) for col in cols)
            for i in range(len(prepared))
        )
        before = conn.total_changes
        for chunk in _chunked(rows, size=1000):
            conn.executemany(sql, chunk)
        return int(conn.total_changes - before)


def upsert_nav(df_nav: pd.DataFrame, table: str = NAV_TABLE) -> int:
    required = {"fund_code", "date", "nav"}
    if not required.issubset(df_nav.columns):
        raise ValueError(f"upsert_nav 缺少字段：{required - set(df_nav.columns)}")
    cols = [c for c in ["fund_code", "date", "nav", "acc_nav"] if c in df_nav.columns]
    return upsert_df(table, df_nav[cols], pk_cols=("fund_code", "date"))


def upsert_portfolio(df_port: pd.DataFrame, table: str = PORTFOLIO_TABLE) -> int:
    required = {"date", "fund_code"}
    if not required.issubset(df_port.columns):
        raise ValueError(f"upsert_portfolio 缺少字段：{required - set(df_port.columns)}")
    return upsert_df(table, df_port, pk_cols=("date", "fund_code"))
