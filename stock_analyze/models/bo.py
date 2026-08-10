"""BO pipeline schemas — Qullamaggie breakout setup structural + contextual."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from stock_analyze.models.vcp import IndustryGroupStrengthFlag, VcpContextEnrichment


class BoBase(BaseModel):
    """A single Qullamaggie consolidation base (impulse peak → breakout)."""

    start_idx: int = Field(description="0-based index of first base bar")
    end_idx: int = Field(description="0-based index of last base bar")
    base_high: float = Field(description="Highest high within the base")
    base_low: float = Field(description="Lowest low within the base")
    depth_pct: float = Field(description="(High - Low) / High * 100")
    duration_days: int = Field(description="Number of trading days in the base")
    pivot: float = Field(description="KDE resistance pivot (global mode in upper quartile)")
    vci: float = Field(description="ATR_short / ATR_medium volatility contraction index")
    dryup_ratio: float = Field(description="Base-end volume / pre-base baseline volume")


BO_VARIANT = Literal["classic", "lower_base", "none"]

BO_LABELS: dict[int, str] = {
    3: "sub_standard",
    4: "strong",
    5: "textbook",
}


class BoSetupRating(BaseModel):
    """Pure-math Qullamaggie BO setup rating (3-5★)."""

    symbol: str
    exchange: str
    variant: BO_VARIANT = "none"
    rating: Literal[3, 4, 5] = Field(description="Overall setup rating (3-5)")
    label: Literal["sub_standard", "strong", "textbook"] = Field(
        description="Label for rating"
    )

    # 9 parameter scores (booleans) + measured values
    prior_impulse: bool = Field(description="Prior impulse >= 30% over 20-63d window")
    prior_impulse_pct: float = Field(default=0.0, description="Measured prior impulse %")
    adr20: bool = Field(description="ADR20 within [4%, 12%] envelope")
    adr20_pct: float = Field(default=0.0, description="Measured 20-day ADR %")
    base_duration: bool = Field(description="Base duration within 10-40 trading days")
    base_duration_days: int = Field(default=0, description="Measured base duration in days")
    vci: bool = Field(description="VCI (ATR_short/ATR_medium) <= 0.65")
    vci_ratio: float = Field(default=0.0, description="Measured VCI ratio")
    ma_stack: bool = Field(description="EMA10>EMA20, positive EMA50 slope, close within 8% of EMA10")
    surfing_dist_pct: float = Field(default=0.0, description="Close distance from EMA10 (%)")
    pivot_kde: bool = Field(description="Gaussian KDE pivot found in base upper quartile")
    higher_lows: bool = Field(description="Consecutive higher lows (S_HL >= 1) into pivot")
    higher_lows_count: int = Field(default=0, description="Measured higher-lows count")
    volume_surge: bool = Field(description="Breakout volume surge >= 1.5x baseline")
    surge_pct: float = Field(default=0.0, description="Measured breakout volume surge %")
    extension: bool = Field(description="True when close > 8% above EMA10 (overextended)")
    extension_pct: float = Field(default=0.0, description="Measured extension above EMA10 (%)")
    sma50_extension_pct: float = Field(
        default=0.0, description="Secondary report field: close distance from 50d SMA (%)"
    )

    # Meta
    base_high: float = Field(default=0.0, description="Base high price")
    base_low: float = Field(default=0.0, description="Base low price")
    pivot: float = Field(default=0.0, description="KDE pivot (resistance) price")
    breakout_idx: Optional[int] = Field(default=None, description="0-based breakout bar index")
    breakout_date: Optional[date] = Field(default=None, description="Breakout bar date")
    rvol10: float = Field(default=0.0, description="Breakout bar relative volume (10d)")
    rs_rating: Optional[float] = Field(default=None, description="RS percentile vs benchmark (0-100)")
    as_of: date = Field(default_factory=date.today)


# --- Bucket envelopes ---


class BoScanBucket(BaseModel):
    """Agent 1 output: BO setup rating buckets."""

    as_of: datetime = Field(default_factory=datetime.utcnow)
    universe_source: Literal["screener", "force", "hybrid"] = "screener"
    gates_applied: bool = True
    ratings: list[BoSetupRating] = Field(default_factory=list)
    five_star: list[BoSetupRating] = Field(default_factory=list)
    four_star: list[BoSetupRating] = Field(default_factory=list)
    three_star: list[BoSetupRating] = Field(default_factory=list)
    count: int = 0
    counts: dict[str, int] = Field(default_factory=lambda: {"5": 0, "4": 0, "3": 0})


class BoEnrichedBucket(BaseModel):
    """Agent 2 output: context-enriched BO stocks (reuses VCP enrichment)."""

    count: int = 0
    stocks: list[VcpContextEnrichment] = Field(default_factory=list)


class BoRatedStock(BaseModel):
    """Setup rating + context enrichment + final rating (post-cap)."""

    # Identity
    symbol: str
    exchange: str
    company_name: str = ""

    # Setup (Agent 1)
    setup_rating: Literal[3, 4, 5]
    setup_label: str
    variant: BO_VARIANT = "none"
    as_of: date

    # Context (Agent 2)
    sector: str = "Unknown"
    industry: str = "Unknown"
    industry_group_strength_flag: IndustryGroupStrengthFlag = "NEUTRAL"
    is_category_leader: bool = False
    market_leadership_context: str = ""
    growth_catalysts: str = ""
    thematic_momentum: str = ""
    top_competitors: list[str] = Field(default_factory=list)

    # Final (Agent 3 — post-cap)
    final_rating: Literal[3, 4, 5] = Field(
        description="Final rating after down-only caps"
    )
    final_label: str = Field(description="Label for final_rating")
    cap_applied: bool = Field(default=False)
    cap_reason: str = Field(default="")
    error: Optional[str] = None


class BoRatedBucket(BaseModel):
    """Agent 3 output: final rated stocks (sorted best→worst)."""

    count: int = 0
    stocks: list[BoRatedStock] = Field(default_factory=list)


__all__ = [
    "BO_LABELS",
    "BO_VARIANT",
    "BoBase",
    "BoEnrichedBucket",
    "BoRatedBucket",
    "BoRatedStock",
    "BoScanBucket",
    "BoSetupRating",
]
