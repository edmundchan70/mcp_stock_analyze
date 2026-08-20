"""Premarket grep scanner schemas — one snapshot call → change% filter → cap."""

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PremarketGateThresholds(BaseModel):
    """Editable premarket thresholds (mirror the Scanner ``premarket_*`` vars)."""

    min_change_pct: float = Field(default=5.0, description="Min premarket change % vs prior close")
    min_vol_mult: float = Field(default=0.0, description="Min volume × 20d ADV (0 = flag off)")
    cap: int = Field(default=300, description="Max survivors kept from the sweep")


class PremarketStock(BaseModel):
    """One premarket survivor row."""

    symbol: str
    exchange: str
    change_pct: float
    price: Optional[float] = None
    volume: Optional[float] = None
    company_name: str = ""
    sector: str = "Unknown"
    adv_20d: Optional[float] = Field(default=None, description="20-day average dollar volume")
    vol_flag: bool = Field(default=False, description="volume >= min_vol_mult × adv_20d")
    strength: int = Field(default=2, description="Deterministic 1-5 strength tier")
    as_of: date = Field(default_factory=date.today)


class PremarketScanBucket(BaseModel):
    """Agent-1 output for a premarket grep run."""

    as_of: datetime = Field(default_factory=_utcnow)
    universe_source: str = "snapshot"
    gates_applied: bool = True
    min_change_pct: float = 5.0
    ratings: list[PremarketStock] = Field(default_factory=list)
    count: int = 0
    counts: dict[str, int] = Field(default_factory=lambda: {"5": 0, "4": 0, "3": 0, "2": 0})


__all__ = ["PremarketGateThresholds", "PremarketScanBucket", "PremarketStock"]
