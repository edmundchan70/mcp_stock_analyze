"""Agent 3 EP Rating schemas — catalyst-enriched stock plus 1–5 EP Rating."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from stock_analyze.models.catalyst import CatalystType

EpRating = Literal[1, 2, 3, 4, 5]
EpRatingLabel = Literal["bs", "no", "better_not", "acceptable", "textbook"]

RATING_LABELS: dict[int, EpRatingLabel] = {
    1: "bs",
    2: "no",
    3: "better_not",
    4: "acceptable",
    5: "textbook",
}


class EpRatingProposal(BaseModel):
    """Structured LLM proposal before hard clamps."""

    ticker: str
    ep_rating: EpRating
    ep_rationale: str = Field(description="Max ~40 words why this star")


class EpRatedStock(BaseModel):
    """Agent 2 fields plus Agent 3 EP Rating fields."""

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
    catalyst_found: bool
    catalyst_type: CatalystType
    catalyst_summary: str
    ep_rating: EpRating
    ep_rating_label: EpRatingLabel
    ep_rationale: str
    ep_catalyst_match: bool


class RatedBucket(BaseModel):
    """Envelope for Agent 3 output (stocks sorted best→worst)."""

    count: int = 0
    stocks: list[EpRatedStock] = Field(default_factory=list)
