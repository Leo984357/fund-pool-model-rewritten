# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _getenv_str(key: str, default: str) -> str:
    value = os.getenv(key)
    return default if value is None or str(value).strip() == "" else str(value).strip()


def _getenv_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or str(value).strip() == "":
        return int(default)
    try:
        return int(str(value).strip())
    except Exception as exc:
        raise ValueError(f"环境变量 {key} 应为整数，收到 {value!r}") from exc


def _getenv_float(key: str, default: float) -> float:
    value = os.getenv(key)
    if value is None or str(value).strip() == "":
        return float(default)
    try:
        return float(str(value).strip())
    except Exception as exc:
        raise ValueError(f"环境变量 {key} 应为浮点数，收到 {value!r}") from exc


def _getenv_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or str(value).strip() == "":
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"环境变量 {key} 应为布尔值，收到 {value!r}")


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(_getenv_str("FUND_DATA_DIR", str(PROJECT_ROOT / "data"))))
    db_path: Path = field(default_factory=lambda: Path(_getenv_str("FUND_DB_PATH", str(PROJECT_ROOT / "db" / "fund_db.sqlite"))))
    output_dir: Path = field(default_factory=lambda: Path(_getenv_str("FUND_OUTPUT_DIR", str(PROJECT_ROOT / "output"))))
    universe_csv: Path = field(default_factory=lambda: Path(_getenv_str("FUND_UNIVERSE_CSV", str(PROJECT_ROOT / "data" / "universe_fund.csv"))))

    universe_limit: int = field(default_factory=lambda: _getenv_int("FUND_UNIVERSE_LIMIT", 100))
    top_n_funds: int = field(default_factory=lambda: _getenv_int("FUND_TOP_N_FUNDS", 5))
    window_days: int = field(default_factory=lambda: _getenv_int("FUND_WINDOW_DAYS", 252))
    since_date: str = field(default_factory=lambda: _getenv_str("FUND_SINCE_DATE", "2022-01-01"))
    min_history_days: int = field(default_factory=lambda: _getenv_int("FUND_MIN_HISTORY_DAYS", 60))
    pure_sharpe_only: bool = field(default_factory=lambda: _getenv_bool("FUND_PURE_SHARPE_ONLY", False))
    parallel_workers: int = field(default_factory=lambda: _getenv_int("PARALLEL_WORKERS", 8))

    weight_scheme: str = field(default_factory=lambda: _getenv_str("FUND_WEIGHT_SCHEME", "weight_optimized"))
    nav_table: str = field(default_factory=lambda: _getenv_str("FUND_NAV_TABLE", "fund_nav_daily"))
    portfolio_table: str = field(default_factory=lambda: _getenv_str("FUND_PORTFOLIO_TABLE", "portfolio_results"))

    optimizer_max_weight: float = field(default_factory=lambda: _getenv_float("FUND_MAX_WEIGHT", 0.45))
    optimizer_min_weight: float = field(default_factory=lambda: _getenv_float("FUND_MIN_WEIGHT", 0.00))
    optimizer_risk_aversion: float = field(default_factory=lambda: _getenv_float("FUND_OPT_RISK_AVERSION", 4.0))
    optimizer_score_tilt: float = field(default_factory=lambda: _getenv_float("FUND_OPT_SCORE_TILT", 0.03))
    optimizer_turnover_penalty: float = field(default_factory=lambda: _getenv_float("FUND_OPT_TURNOVER_PENALTY", 0.15))
    optimizer_l2_penalty: float = field(default_factory=lambda: _getenv_float("FUND_OPT_L2_PENALTY", 0.01))
    optimizer_target_vol: float = field(default_factory=lambda: _getenv_float("FUND_OPT_TARGET_VOL", 0.0))
    optimizer_cov_lookback: int = field(default_factory=lambda: _getenv_int("FUND_OPT_COV_LOOKBACK", 126))

    report_title: str = field(default_factory=lambda: _getenv_str("FUND_REPORT_TITLE", "Fund Pool Model Research Report"))

    factor_weights: Dict[str, float] = field(default_factory=lambda: {
        "ann_return": _getenv_float("FACTOR_ann_return", 0.35),
        "ann_vol": _getenv_float("FACTOR_ann_vol", -0.15),
        "down_vol": _getenv_float("FACTOR_down_vol", -0.10),
        "mdd": _getenv_float("FACTOR_mdd", -0.10),
        "sharpe": _getenv_float("FACTOR_sharpe", 0.35),
        "ir": _getenv_float("FACTOR_ir", 0.15),
    })

    def validate(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if self.universe_limit <= 0:
            raise ValueError("FUND_UNIVERSE_LIMIT 必须 > 0")
        if self.top_n_funds <= 0:
            raise ValueError("FUND_TOP_N_FUNDS 必须 > 0")
        if self.window_days <= 1:
            raise ValueError("FUND_WINDOW_DAYS 必须 > 1")
        if self.min_history_days < 2:
            raise ValueError("FUND_MIN_HISTORY_DAYS 必须 >= 2")
        if self.parallel_workers <= 0:
            raise ValueError("PARALLEL_WORKERS 必须 > 0")
        if self.weight_scheme not in {"weight_equal", "weight_risk_parity", "weight_mixed", "weight_optimized"}:
            raise ValueError("FUND_WEIGHT_SCHEME 必须为 weight_equal / weight_risk_parity / weight_mixed / weight_optimized")
        if not (0.0 <= self.optimizer_min_weight <= 1.0):
            raise ValueError("FUND_MIN_WEIGHT 必须在 [0,1] 内")
        if not (0.0 < self.optimizer_max_weight <= 1.0):
            raise ValueError("FUND_MAX_WEIGHT 必须在 (0,1] 内")
        if self.optimizer_min_weight > self.optimizer_max_weight:
            raise ValueError("FUND_MIN_WEIGHT 不能大于 FUND_MAX_WEIGHT")
        if self.optimizer_max_weight * self.top_n_funds < 1.0 - 1e-12:
            raise ValueError("当前 Top-N 与最大权重约束不可行：TopN * MaxWeight < 1")
        if self.optimizer_cov_lookback < 20:
            raise ValueError("FUND_OPT_COV_LOOKBACK 必须 >= 20")

    def update_from_gui(self, kv: Dict[str, Any]) -> None:
        mapping = {
            "DATA_DIR": "data_dir",
            "DB_PATH": "db_path",
            "OUTPUT_DIR": "output_dir",
            "UNIVERSE_CSV": "universe_csv",
            "UNIVERSE_LIMIT": "universe_limit",
            "TOP_N_FUNDS": "top_n_funds",
            "WINDOW_DAYS": "window_days",
            "SINCE_DATE": "since_date",
            "MIN_HISTORY_DAYS": "min_history_days",
            "PURE_SHARPE_ONLY": "pure_sharpe_only",
            "PARALLEL_WORKERS": "parallel_workers",
            "WEIGHT_SCHEME": "weight_scheme",
            "NAV_TABLE": "nav_table",
            "PORTFOLIO_TABLE": "portfolio_table",
            "FACTOR_WEIGHTS": "factor_weights",
            "OPTIMIZER_MAX_WEIGHT": "optimizer_max_weight",
            "OPTIMIZER_MIN_WEIGHT": "optimizer_min_weight",
            "OPTIMIZER_RISK_AVERSION": "optimizer_risk_aversion",
            "OPTIMIZER_SCORE_TILT": "optimizer_score_tilt",
            "OPTIMIZER_TURNOVER_PENALTY": "optimizer_turnover_penalty",
            "OPTIMIZER_L2_PENALTY": "optimizer_l2_penalty",
            "OPTIMIZER_TARGET_VOL": "optimizer_target_vol",
            "OPTIMIZER_COV_LOOKBACK": "optimizer_cov_lookback",
            "REPORT_TITLE": "report_title",
        }
        for key, value in (kv or {}).items():
            attr = mapping.get(key, key)
            if not hasattr(self, attr):
                continue
            current = getattr(self, attr)
            if isinstance(current, bool):
                value = bool(int(value)) if isinstance(value, str) else bool(value)
            elif isinstance(current, int):
                value = int(value)
            elif isinstance(current, float):
                value = float(value)
            elif isinstance(current, Path):
                value = Path(str(value))
            elif isinstance(current, dict) and isinstance(value, dict):
                merged = dict(current)
                merged.update(value)
                value = merged
            elif current is not None:
                value = type(current)(value)
            setattr(self, attr, value)
        self.validate()

    def summary_lines(self) -> list[str]:
        payload = asdict(self)
        return [
            f"[CFG] data_dir={payload['data_dir']}",
            f"[CFG] db_path={payload['db_path']}",
            f"[CFG] output_dir={payload['output_dir']}",
            f"[CFG] universe_csv={payload['universe_csv']}",
            f"[CFG] universe_limit={payload['universe_limit']}",
            f"[CFG] top_n_funds={payload['top_n_funds']}",
            f"[CFG] window_days={payload['window_days']}",
            f"[CFG] since_date={payload['since_date']}",
            f"[CFG] min_history_days={payload['min_history_days']}",
            f"[CFG] pure_sharpe_only={payload['pure_sharpe_only']}",
            f"[CFG] parallel_workers={payload['parallel_workers']}",
            f"[CFG] weight_scheme={payload['weight_scheme']}",
            f"[CFG] optimizer_max_weight={payload['optimizer_max_weight']}",
            f"[CFG] optimizer_min_weight={payload['optimizer_min_weight']}",
            f"[CFG] optimizer_risk_aversion={payload['optimizer_risk_aversion']}",
            f"[CFG] optimizer_score_tilt={payload['optimizer_score_tilt']}",
            f"[CFG] optimizer_turnover_penalty={payload['optimizer_turnover_penalty']}",
            f"[CFG] optimizer_l2_penalty={payload['optimizer_l2_penalty']}",
            f"[CFG] optimizer_target_vol={payload['optimizer_target_vol']}",
            f"[CFG] optimizer_cov_lookback={payload['optimizer_cov_lookback']}",
        ]


C = Config()
C.validate()

DATA_DIR = C.data_dir
DB_PATH = C.db_path
OUTPUT_DIR = C.output_dir
UNIVERSE_CSV = str(C.universe_csv)
UNIVERSE_LIMIT = C.universe_limit
TOP_N_FUNDS = C.top_n_funds
WINDOW_DAYS = C.window_days
SINCE_DATE = C.since_date
MIN_HISTORY_DAYS = C.min_history_days
PURE_SHARPE_ONLY = C.pure_sharpe_only
PARALLEL_WORKERS = C.parallel_workers
WEIGHT_SCHEME = C.weight_scheme
NAV_TABLE = C.nav_table
PORTFOLIO_TABLE = C.portfolio_table
FACTOR_WEIGHTS = C.factor_weights
OPTIMIZER_MAX_WEIGHT = C.optimizer_max_weight
OPTIMIZER_MIN_WEIGHT = C.optimizer_min_weight
OPTIMIZER_RISK_AVERSION = C.optimizer_risk_aversion
OPTIMIZER_SCORE_TILT = C.optimizer_score_tilt
OPTIMIZER_TURNOVER_PENALTY = C.optimizer_turnover_penalty
OPTIMIZER_L2_PENALTY = C.optimizer_l2_penalty
OPTIMIZER_TARGET_VOL = C.optimizer_target_vol
OPTIMIZER_COV_LOOKBACK = C.optimizer_cov_lookback
REPORT_TITLE = C.report_title


def print_summary() -> None:
    for line in C.summary_lines():
        print(line)


for _name, _value in {
    "DATA_DIR": DATA_DIR,
    "DB_PATH": DB_PATH,
    "OUTPUT_DIR": OUTPUT_DIR,
    "UNIVERSE_CSV": UNIVERSE_CSV,
    "UNIVERSE_LIMIT": UNIVERSE_LIMIT,
    "TOP_N_FUNDS": TOP_N_FUNDS,
    "WINDOW_DAYS": WINDOW_DAYS,
    "SINCE_DATE": SINCE_DATE,
    "MIN_HISTORY_DAYS": MIN_HISTORY_DAYS,
    "PURE_SHARPE_ONLY": PURE_SHARPE_ONLY,
    "PARALLEL_WORKERS": PARALLEL_WORKERS,
    "WEIGHT_SCHEME": WEIGHT_SCHEME,
    "NAV_TABLE": NAV_TABLE,
    "PORTFOLIO_TABLE": PORTFOLIO_TABLE,
    "FACTOR_WEIGHTS": FACTOR_WEIGHTS,
    "OPTIMIZER_MAX_WEIGHT": OPTIMIZER_MAX_WEIGHT,
    "OPTIMIZER_MIN_WEIGHT": OPTIMIZER_MIN_WEIGHT,
    "OPTIMIZER_RISK_AVERSION": OPTIMIZER_RISK_AVERSION,
    "OPTIMIZER_SCORE_TILT": OPTIMIZER_SCORE_TILT,
    "OPTIMIZER_TURNOVER_PENALTY": OPTIMIZER_TURNOVER_PENALTY,
    "OPTIMIZER_L2_PENALTY": OPTIMIZER_L2_PENALTY,
    "OPTIMIZER_TARGET_VOL": OPTIMIZER_TARGET_VOL,
    "OPTIMIZER_COV_LOOKBACK": OPTIMIZER_COV_LOOKBACK,
    "REPORT_TITLE": REPORT_TITLE,
}.items():
    setattr(C, _name, _value)
