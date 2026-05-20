# -*- coding: utf-8 -*-
"""基金池日度主流程入口。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from src.pipeline import run_daily_pipeline


def main():
    return run_daily_pipeline()


if __name__ == "__main__":
    main()
