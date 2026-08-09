"""EP scanner schemas — identity + filter metrics only (no OHLC arrays)."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EpStock(BaseModel):
    """One symbol's metrics for Baseline / Strict evaluation."""

    symbol: str
    exchange: str
    price: float
    market_cap: Optional[float] = None
    avg_dollar_volume_50d: Optional[float] = None
    gap_pct: float
    rvol10: float
    event_dollar_volume: Optional[float] = None
    force_included: bool = False
    as_of: date


class GateThresholds(BaseModel):
    """Serializable gate config written into scan JSON."""

    min_price: float
    min_gap_pct: float
    min_rvol10: float
    min_market_cap: Optional[float] = None
    max_market_cap: Optional[float] = None
    min_avg_dollar_volume_50d: Optional[float] = None
    min_event_dollar_volume: Optional[float] = None


class StockBucket(BaseModel):
    count: int = 0
    stocks: list[EpStock] = Field(default_factory=list)


class EpScanResult(BaseModel):
    """Dual-bucket Agent 1 output."""

    as_of: datetime
    universe_source: Literal["screener", "force", "hybrid"]
    session: Literal["rth"] = "rth"
    gates: dict[str, GateThresholds]
    baseline: StockBucket = Field(default_factory=StockBucket)
    strict: StockBucket = Field(default_factory=StockBucket)

    def model_dump_selected(self, select: Literal["baseline", "strict", "both"] = "both") -> dict[str, Any]:
        data = self.model_dump(mode="json")
        if select == "baseline":
            data.pop("strict", None)
        elif select == "strict":
            data.pop("baseline", None)
        return data
