# -*- coding: utf-8 -*-
"""
incremental_utils.py
增量更新通用工具：
- 读取 fund_nav_daily 的最新交易日（全库）
- 计算增量抓取的 since（含回溯天数，避免 T-1 修复/回滚）
- 兼容：自动定位项目根目录下 db/fund_db.sqlite，并设置 WAL/busy_timeout
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# /path/to/project/src/incremental_utils.py → parents[1] == 项目根目录
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "fund_db.sqlite"

def _conn(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)  # autocommit
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA busy_timeout=8000;")
    cur.close()
    return conn

def get_global_last_nav_date(db_path: Path | str = DEFAULT_DB_PATH) -> Optional[str]:
    """
    返回 fund_nav_daily 的全局最大 date（YYYY-MM-DD），无数据返回 None
    """
    dbp = Path(db_path)
    if not dbp.exists():
        return None
    conn = _conn(dbp)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(date) FROM fund_nav_daily;")
        row = cur.fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        conn.close()

def decide_increment_since(last_date_str: Optional[str], fallback_since: str, lookback_days: int = 5) -> str:
    """
    根据库内最新日期 + 回溯天数，决定本次抓取的 since。
    - last_date_str: 库内最近日期（None 表示空库）
    - fallback_since: 库为空时，退化到此日期（通常为 config.SINCE_DATE）
    - lookback_days: 回溯天数，覆盖公告修复/回滚
    """
    if not last_date_str:
        return fallback_since
    last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
    since = last_date - timedelta(days=max(0, int(lookback_days)))
    return since.isoformat()
