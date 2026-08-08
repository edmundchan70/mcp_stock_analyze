"""Agent 2 catalyst schemas — EP technical fields plus compressed news catalyst."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

CatalystType = Literal["EARNINGS", "GUIDANCE", "CONTRACT", "FDA", "PR", "UNKNOWN"]


class CatalystSummary(BaseModel):
    """Structured LLM compression of Tavily news snippets."""

    ticker: str
    catalyst_found: bool = Field(description="True if a clear news event/earnings beat was found")
    catalyst_type: CatalystType = Field(
        description="EARNINGS | GUIDANCE | CONTRACT | FDA | PR | UNKNOWN"
    )
    summary: str = Field(description="Max 2 bullet points or 30 words summarizing the catalyst")


class CatalystEnrichedStock(BaseModel):
    """Agent 1 EpStock fields plus Agent 2 catalyst fields."""

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


class CatalystBucket(BaseModel):
    """Envelope for Agent 2 output."""

    count: int = 0
    stocks: list[CatalystEnrichedStock] = Field(default_factory=list)
