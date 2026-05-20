# -*- coding: utf-8 -*-
from __future__ import annotations

from src.dao import _connect, EXPLICIT_SCHEMA


def main() -> None:
    with _connect() as conn:
        for sql in EXPLICIT_SCHEMA.values():
            conn.execute(sql)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_nav_latest (
                fund_code TEXT PRIMARY KEY,
                date TEXT,
                nav REAL,
                acc_nav REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_info (
                fund_code TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                manager TEXT,
                custodian TEXT,
                inception_date TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_holdings (
                fund_code TEXT NOT NULL,
                report_date TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                weight REAL,
                shares REAL,
                market_value REAL,
                PRIMARY KEY (fund_code, report_date, stock_code)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fund_allocation (
                fund_code TEXT NOT NULL,
                report_date TEXT NOT NULL,
                equity REAL,
                bond REAL,
                cash REAL,
                other REAL,
                PRIMARY KEY (fund_code, report_date)
            )
            """
        )
    print("✅ DB initialized")


if __name__ == "__main__":
    main()
