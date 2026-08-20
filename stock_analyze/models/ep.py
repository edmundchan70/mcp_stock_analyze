"""EP scanner schemas — identity + filter metrics only (no OHLC arrays)."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EpSetupFeatures(BaseModel):
    """Pure-math EP technical setup snapshot (``score_ep_setup`` output).

    Event-day shock → post-event base / pullback / EMA / VWAP support
    features. ``features_held`` counts enabled features that hold.
    """

    symbol: str = ""
    exchange: str = ""
    event_idx: Optional[int] = Field(
        default=None, description="0-based index of the event day (highest-volume bar in last 63)"
    )
    base_detected: bool = False
    volume_spike: bool = False
    pullback_contrast: bool = False
    ema_support: bool = False
    vwap_support: bool = False
    features_held: int = 0

    # Measured values (reported alongside the booleans)
    event_volume_ratio: float = Field(default=0.0, description="Event volume / 50d avg volume")
    pullback_vol_ratio: float = Field(default=0.0, description="Pullback avg volume / event volume")
    ema_stack_aligned: bool = Field(default=False, description="close > EMA9 > EMA20 > EMA50")
    vwap_anchor: Literal["event", "pivot", "none"] = Field(
        default="none", description="Which anchor's VWAP showed support"
    )
    as_of: date = Field(default_factory=date.today)


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

    # EP technical setup features (flattened from EpSetupFeatures when the
    # feature test is active; all False otherwise)
    event_idx: Optional[int] = None
    base_detected: bool = False
    volume_spike: bool = False
    pullback_contrast: bool = False
    ema_support: bool = False
    vwap_support: bool = False
    features_held: int = 0
    ep_keep: bool = Field(default=False, description="Kept by the EP technical test (feature mode)")

    # Informational gate outcomes — always evaluated, but in feature mode they
    # never filter (kept list = feature survivors only)
    passes_baseline: bool = Field(default=False, description="Would pass the Baseline gate")
    passes_strict: bool = Field(default=False, description="Would pass the Strict gate")


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
