# -*- coding: utf-8 -*-
"""
基金净值抓取（东财 F10 真分页 + AKShare 兜底）
- 先走 F10DataApi.aspx，先请求第1页，解析 pages，总页数 >1 时逐页抓取
- 每页固定返回20行（服务端限制），因此不能用 per=20000；必须分页
- 失败再用 AKShare 的 JS 端点兜底（单位/累计净值走势）
输出统一：fund_code, date, nav, acc_nav
"""
from __future__ import annotations

import re
import time
from io import StringIO
from datetime import datetime
import pandas as pd
import requests
import akshare as ak

from .dao import upsert_df
from .utils import log

# -------- 通用设置 --------
HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
CODE_RE = re.compile(r"^\d{6}$")
PREFER_JS = False  # 如需优先 AKShare，把它改为 True

def _fix_code(code: str) -> str:
    s = re.sub(r"\D", "", str(code)).zfill(6)
    return s if CODE_RE.match(s) else ""

def _try(fn, tag="", tries=2, wait=1.0, backoff=2.0):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            log(f"[retry] {tag} {i+1}/{tries} 失败: {e}，sleep {wait:.1f}s")
            time.sleep(wait); wait *= backoff
    log(f"[fail] {tag}: {last}")
    raise last

# -------- F10 表格（真分页） --------
_PAT_PAGES = re.compile(r"pages\s*:\s*(\d+)", re.I)
def _extract_table_html(text: str) -> str:
    """从 F10DataApi 响应里抽出 <table>...</table> 片段"""
    m1 = re.search(r"<table[^>]*>", text, re.I|re.S)
    m2 = re.search(r"</table>", text, re.I|re.S)
    if not (m1 and m2):
        return ""
    start = m1.start()
    end = m2.end()
    return text[start:end]

def _fetch_f10_pages(code6: str, max_pages: int = 999) -> pd.DataFrame:
    url = "http://fundf10.eastmoney.com/F10DataApi.aspx"
    # 先请求第1页，解析总页数
    headers = {**HEADERS_BASE, "Referer": f"http://fundf10.eastmoney.com/jjjz_{code6}.html"}
    params = {"type": "lsjz", "code": code6, "page": 1, "per": 20}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    text = r.text
    # 解析页数
    m = _PAT_PAGES.search(text)
    pages = int(m.group(1)) if m else 1
    pages = min(pages, max_pages)

    all_frames = []
    for p in range(1, pages+1):
        params["page"] = p
        rp = requests.get(url, params=params, headers=headers, timeout=15)
        rp.raise_for_status()
        html = _extract_table_html(rp.text)
        if not html:
            # 兜底：直接让 pandas 自己找
            tables = pd.read_html(StringIO(rp.text))
        else:
            tables = pd.read_html(StringIO(html))
        if not tables:
            break
        dfp = tables[0]

        # 列重命名
        ren = {}
        for c in dfp.columns:
            if "日期" in c: ren[c] = "date"
            elif "单位" in c: ren[c] = "nav"
            elif "累计" in c: ren[c] = "acc_nav"
        dfp = dfp.rename(columns=ren)
        keep = [c for c in ["date","nav","acc_nav"] if c in dfp.columns]
        if "date" not in keep or "nav" not in keep:
            continue

        # 基础清洗
        dfp["date"] = pd.to_datetime(dfp["date"], errors="coerce")
        dfp["nav"]  = pd.to_numeric(dfp["nav"], errors="coerce")
        if "acc_nav" in dfp.columns:
            dfp["acc_nav"] = pd.to_numeric(dfp["acc_nav"], errors="coerce")
        else:
            dfp["acc_nav"] = pd.NA
        dfp = dfp.dropna(subset=["date","nav"])
        if dfp.empty:
            continue

        all_frames.append(dfp[["date","nav","acc_nav"]])
        # 轻限速
        time.sleep(0.08)

    if not all_frames:
        return pd.DataFrame(columns=["date","nav","acc_nav"])

    df = pd.concat(all_frames, ignore_index=True)
    # 去重、排序
    df = df.drop_duplicates(subset=["date"]).sort_values("date")
    return df

# -------- AKShare JS 兜底 --------
def _fetch_js(code6: str) -> pd.DataFrame:
    dfu = ak.fund_open_fund_info_em(symbol=code6, indicator="单位净值走势")
    try:
        dfa = ak.fund_open_fund_info_em(symbol=code6, indicator="累计净值走势")
        df = pd.merge(dfu[["净值日期","单位净值"]], dfa[["净值日期","累计净值"]],
                      on="净值日期", how="left")
    except Exception:
        df = dfu.rename(columns={"净值日期":"净值日期","单位净值":"单位净值"})
    df = df.rename(columns={"净值日期":"date","单位净值":"nav","累计净值":"acc_nav"})
    if "acc_nav" not in df.columns:
        df["acc_nav"] = pd.NA
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["nav"]  = pd.to_numeric(df["nav"], errors="coerce")
    df["acc_nav"] = pd.to_numeric(df["acc_nav"], errors="coerce")
    df = df.dropna(subset=["date","nav"]).drop_duplicates(subset=["date"]).sort_values("date")
    return df[["date","nav","acc_nav"]]

# -------- 统一清洗/入库 --------
def _normalize(code6: str, raw: pd.DataFrame, since: str | None) -> pd.DataFrame:
    df = raw.copy()
    if df.empty:
        return pd.DataFrame(columns=["fund_code","date","nav","acc_nav"])
    if since:
        sd = pd.to_datetime(since)
        df = df[df["date"] >= sd]
    df.insert(0, "fund_code", code6)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[["fund_code","date","nav","acc_nav"]].where(pd.notna(df), None)

def fetch_one_fund_nav(code: str, since: str | None = None) -> pd.DataFrame:
    code6 = _fix_code(code)
    if not code6:
        raise ValueError(f"非法基金代码: {code}")
    if PREFER_JS:
        try:
            raw = _try(lambda: _fetch_js(code6), tag=f"{code6}-js")
            src = "js"
        except Exception as e_js:
            log(f"[warn] JS失败，回退F10分页：{e_js}")
            raw = _try(lambda: _fetch_f10_pages(code6), tag=f"{code6}-f10")
            src = "f10"
    else:
        try:
            raw = _try(lambda: _fetch_f10_pages(code6), tag=f"{code6}-f10")
            src = "f10"
        except Exception as e_f10:
            log(f"[warn] F10失败，改用JS：{e_f10}")
            raw = _try(lambda: _fetch_js(code6), tag=f"{code6}-js")
            src = "js"

    df = _normalize(code6, raw, since)
    log(f"[OK] {code6} rows={len(df)} src={src}")
    time.sleep(0.1)
    return df

def save_nav(df: pd.DataFrame) -> int:
    if df is None or df.empty: return 0
    return upsert_df("fund_nav_daily", df, pk_cols=["fund_code","date"])
