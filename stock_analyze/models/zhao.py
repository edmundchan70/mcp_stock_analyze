"""照妖鏡 (zhao) scanner schemas — realtime market-margin + daily relative strength."""

from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


ZHAO_VARIANT = Literal["realtime", "daily"]
BENCHMARK = Literal["SPY", "QQQ"]


class ZhaoGateThresholds(BaseModel):
    """Editable zhao thresholds (mirror the Scanner ``zhao_*`` vars)."""

    variant: ZHAO_VARIANT = "realtime"
    benchmark: BENCHMARK = "SPY"
    sma20_buffer_pct: float = Field(default=0.0, description="Min close % above SMA20 to keep")
    min_margin_pct: float = Field(default=1.0, description="Realtime: min stock-benchmark margin %")
    min_rs_pct: float = Field(default=0.0, description="Daily: min 20d relative strength vs benchmark")
    max_high_dist_pct: float = Field(default=15.0, description="Daily: max % below the 252d high")


class ZhaoStock(BaseModel):
    """One zhao survivor row (carries every Scanner results column)."""

    symbol: str
    exchange: str
    variant: ZHAO_VARIANT
    strength: int = Field(description="Deterministic 1-5 strength tier")
    close: float
    sma20: float
    sector: str = "Unknown"
    # realtime fields
    today_pct: Optional[float] = Field(default=None, description="Stock today's change vs prior close")
    bench_pct: Optional[float] = Field(default=None, description="Benchmark today's change")
    bench_symbol: Optional[str] = Field(default=None)
    margin_pct: Optional[float] = Field(default=None, description="today_pct - bench_pct")
    # daily fields
    rs_20d: Optional[float] = Field(default=None, description="20d relative strength vs benchmark")
    pct_from_high: Optional[float] = Field(default=None, description="(close / 252d high - 1) * 100")
    streak: int = Field(default=0, description="Consecutive-day scan_signals streak (1/2/3+, 0 = none)")
    as_of: date = Field(default_factory=date.today)


class ZhaoScanBucket(BaseModel):
    """Agent-1 output for a zhao scan run."""

    as_of: datetime = Field(default_factory=_utcnow)
    universe_source: Literal["screener", "force", "hybrid", "snapshot"] = "screener"
    gates_applied: bool = True
    variant: ZHAO_VARIANT = "realtime"
    benchmark: BENCHMARK = "SPY"
    ratings: list[ZhaoStock] = Field(default_factory=list)
    count: int = 0
    counts: dict[str, int] = Field(default_factory=lambda: {"5": 0, "4": 0, "3": 0, "2": 0})


__all__ = ["BENCHMARK", "ZHAO_VARIANT", "ZhaoGateThresholds", "ZhaoScanBucket", "ZhaoStock"]
