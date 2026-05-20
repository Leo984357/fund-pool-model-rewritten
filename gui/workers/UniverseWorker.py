# -*- coding: utf-8 -*-
"""
UniverseWorker.py — 生成基金池（真实管线）
调用 src.universe_fund.load_universe_fund(limit=K)，FUND_UNIVERSE_CSV 指定输出。
"""
from PySide6.QtCore import QThread, Signal
import os, sys, json, hashlib, datetime as dt, importlib
from typing import Dict, Any, List
import pandas as pd

class UniverseWorker(QThread):
    stage = Signal(str, int)
    log = Signal(str)
    preview = Signal(list)
    saved = Signal(str)
    failed = Signal(str)

    def __init__(self, params: Dict[str, Any], output_csv: str, parent=None):
        super().__init__(parent)
        self.params = params or {}
        self.output_csv = output_csv or "data/universe_fund.csv"
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = f"univ_{ts}_{hashlib.md5(json.dumps(self.params, sort_keys=True).encode()).hexdigest()[:8]}"
        here = os.path.abspath(os.path.dirname(__file__))
        self.project_root = os.path.abspath(os.path.join(here, "..", ".."))

    def run(self):
        try:
            K = int(self.params.get("pool_size", 100))
            self.stage.emit("invoke", 10); self.log.emit(f"[UNIV] limit={K}")

            out_csv = self._abs(self.output_csv)
            os.environ["FUND_UNIVERSE_CSV"] = out_csv
            if self.params.get("lookback_days"):
                os.environ["FUND_LOOKBACK_DAYS"] = str(int(self.params["lookback_days"]))

            sys.path.insert(0, self.project_root)
            for name in list(sys.modules.keys()):
                if name.startswith("src.") or name == "src":
                    sys.modules.pop(name, None)
            mod = importlib.import_module("src.universe_fund")
            if not hasattr(mod, "load_universe_fund"):
                raise RuntimeError("src.universe_fund.load_universe_fund 未找到")
            self.log.emit(f"[UNIV] 调用 src.universe_fund.load_universe_fund(limit={K})")
            codes = mod.load_universe_fund(limit=K)  # 会写 CSV 到 FUND_UNIVERSE_CSV

            recs = [{"fund_code": c} for c in (codes or [])]
            self.preview.emit(recs)
            self.saved.emit(out_csv)
            self.stage.emit("done", 100)
        except Exception as e:
            self.failed.emit(str(e))

    def _abs(self, p: str) -> str:
        return os.path.abspath(os.path.join(self.project_root, p)) if not os.path.isabs(p) else p
