# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from src.config import C
from src.dao import _connect
import init_db

MODE = os.getenv("RESET_MODE", "hard").lower()
TABLES = [
    "fund_nav_daily",
    "fund_nav_latest",
    "fund_info",
    "fund_holdings",
    "fund_allocation",
    "portfolio_results",
]


def backup_db(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_name(f"{db_path.stem}.bak_{ts}{db_path.suffix}")
    shutil.copy2(db_path, backup)
    return backup


def hard_reset(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_db(db_path)
    if backup:
        print(f"[RESET] 已备份：{backup}")
    if db_path.exists():
        db_path.unlink()
        print(f"[RESET] 已删除旧库：{db_path}")
    init_db.main()


def soft_reset(db_path: Path) -> None:
    with _connect() as conn:
        for table in TABLES:
            try:
                conn.execute(f'DELETE FROM "{table}"')
                print(f"[RESET] 已清空 {table}")
            except Exception as exc:
                print(f"[RESET][WARN] 清空 {table} 失败：{exc}")
        conn.execute("VACUUM")


def main() -> None:
    db_path = Path(C.db_path)
    if MODE == "soft":
        soft_reset(db_path)
    else:
        hard_reset(db_path)


if __name__ == "__main__":
    main()
