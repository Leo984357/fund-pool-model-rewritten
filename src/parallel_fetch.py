# -*- coding: utf-8 -*-
"""
并行抓取封装：
- fetch_and_save_nav_batch：并行抓指定起点（全量/局部）
- fetch_and_save_nav_incremental：自动增量（读取库内最新日期 + 回溯 N 天）

不改变既有常量与外部接口。并发度可用环境变量 PARALLEL_WORKERS 覆盖。
"""
from __future__ import annotations
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

from .utils import log
from .data_fetcher_ak_fund import fetch_one_fund_nav, save_nav

DEFAULT_WORKERS = max(16, os.cpu_count() or 16)

def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return max(1, int(v))
    except Exception:
        return default

def fetch_and_save_nav_batch(
    codes: Iterable[str],
    since: Optional[str] = None,
    max_workers: Optional[int] = None
) -> int:
    """
    并行抓取一批基金净值并落库（全量/指定起点）。
    Parameters
    ----------
    codes: 基金代码列表
    since: 起始日期 YYYY-MM-DD（None 表示数据源默认）
    max_workers: 并发线程数（默认读取 PARALLEL_WORKERS 或 CPU 核心数）
    Returns
    -------
    写库总行数（粗略）
    """
    codes = list(dict.fromkeys(codes))
    if not codes:
        log("无基金需要抓取")
        return 0

    workers = max_workers or _int_env("PARALLEL_WORKERS", DEFAULT_WORKERS)
    log(f"开始并行抓取：总数={len(codes)}，workers={workers}，since={since or '-'}")
    write_rows = 0

    def _task(code: str) -> int:
        try:
            df = fetch_one_fund_nav(code, since=since)
            return save_nav(df) if df is not None and not df.empty else 0
        except Exception as e:
            log(f"[ERR] {code} 抓取失败：{e}")
            tb = traceback.format_exc().splitlines()[-3:]
            log(" | ".join(tb))
            return 0

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fund-dl") as ex:
        futures = {ex.submit(_task, c): c for c in codes}
        done = 0
        for fut in as_completed(futures):
            rows = fut.result()
            write_rows += int(rows or 0)
            done += 1
            if done % 10 == 0 or done == len(codes):
                log(f"[并行进度] {done}/{len(codes)} 已完成，累计写库 {write_rows} 行")

    log(f"并行抓取完成：共写库 {write_rows} 行")
    return write_rows

# === 新增：自动增量入口 ===
def fetch_and_save_nav_incremental(
    codes: Iterable[str],
    fallback_since: str,
    lookback_days: int = 5,
    max_workers: Optional[int] = None
) -> int:
    """
    增量抓取：根据库内最新日期自动决定 since，并回溯 lookback_days 天。
    环境变量 INCR_LOOKBACK_DAYS 可覆盖回溯天数。
    """
    from .incremental_utils import get_global_last_nav_date, decide_increment_since

    env_lb = os.getenv("INCR_LOOKBACK_DAYS")
    if env_lb:
        try:
            lookback_days = max(0, int(env_lb))
        except Exception:
            pass

    last_date = get_global_last_nav_date()
    since = decide_increment_since(last_date, fallback_since=fallback_since, lookback_days=lookback_days)
    log(f"[增量] 库内最新: {last_date or 'None'} → 本次 since: {since} (回溯 {lookback_days} 天)")

    return fetch_and_save_nav_batch(codes, since=since, max_workers=max_workers)
