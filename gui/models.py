from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class StrategyRunConfig:
    since: str = "2022-01-01"
    universe_csv: str = "data/universe_fund.csv"
    workers: int = 8
    top_n: int = 5
    window_days: int = 252
    universe_limit: int = 100
    weight_scheme: str = "weight_optimized"
    backfill_days: int = 126
    max_weight: float = 0.45
    min_weight: float = 0.0
    risk_aversion: float = 4.0
    score_tilt: float = 0.03
    turnover_penalty: float = 0.15
    l2_penalty: float = 0.01
    target_vol: float = 0.0
    cov_lookback: int = 126

    def to_env_payload(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UniverseBuildConfig:
    pool_size: int = 100
    lookback_days: int = 252


@dataclass
class RunArtifacts:
    run_id: str
    equity_curve_csv: Optional[str] = None
    equity_curve_png: Optional[str] = None
    weights_csv: Optional[str] = None
    trades_csv: Optional[str] = None
    scores_csv: Optional[str] = None
    report_html: Optional[str] = None
    report_md: Optional[str] = None
    report_json: Optional[str] = None
    params_json: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "RunArtifacts":
        return cls(**{k: payload.get(k) for k in cls.__dataclass_fields__.keys()})
