"""VCP pipeline schemas — volatility contraction pattern structural + contextual."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class VcpContraction(BaseModel):
    """Single VCP wave (high pivot → low pivot) with measured characteristics."""

    index: int = Field(description="0-based contraction number (oldest first)")
    high_pivot: float = Field(description="High pivot price")
    low_pivot: float = Field(description="Low pivot price")
    dollar_range: float = Field(description="High - Low")
    depth_pct: float = Field(description="(High - Low) / High * 100")
    avg_volume: float = Field(description="Average volume during contraction")
    duration_days: int = Field(description="Calendar days from high to low pivot")


class VcpStructuralRating(BaseModel):
    """Pure-math VCP structural rating (1-5★)."""

    symbol: str
    exchange: str
    structural_rating: Literal[1, 2, 3, 4, 5] = Field(
        description="Overall structural rating (1-5)"
    )
    structural_label: Literal["disqualified", "sub_standard", "tradable", "strong", "textbook"] = Field(
        description="Label for structural_rating"
    )

    # 9 parameter scores
    stage2_trend: bool = Field(description="Stage 2 trend template passed")
    rs_rating: float = Field(description="RS rating (0-100)")
    proximity_52w_pct: float = Field(description="% below 52-week high")
    contraction_count: int = Field(description="Number of VCP waves (k)")
    trough_symmetry_score: int = Field(description="Trough symmetry score (3/4/5)")
    peak_symmetry_score: int = Field(description="Peak symmetry score (3/4/5)")
    dollar_range_score: int = Field(description="Dollar range contraction score (3/4/5)")
    depth_score: int = Field(description="Depth percentage score (3/4/5)")
    tight_closes_score: int = Field(description="Tight closes signature score (3/4/5)")
    volume_decay_score: int = Field(description="Volume decay score (3/4/5)")
    time_contraction_score: int = Field(description="Time contraction score (3/4/5)")

    contractions: list[VcpContraction] = Field(
        default_factory=list,
        description="Detected contractions (oldest first)",
    )
    as_of: date = Field(default_factory=date.today)


STRUCTURAL_LABELS: dict[int, str] = {
    1: "disqualified",
    2: "disqualified",
    3: "sub_standard",
    4: "strong",
    5: "textbook",
}


IndustryGroupStrengthFlag = Literal["HOT_SECTOR", "NEUTRAL", "DECLINING_GROUP"]


class VcpContextEnrichment(BaseModel):
    """Tavily dual-query enrichment parsed by LLM."""

    symbol: str
    exchange: str
    sector: str = Field(
        default="Unknown",
        description="Broad sector (e.g. Technology, Healthcare)",
    )
    industry: str = Field(
        default="Unknown",
        description="Specific industry/sub-industry",
    )
    industry_group_strength_flag: IndustryGroupStrengthFlag = Field(
        default="NEUTRAL",
        description="HOT_SECTOR | NEUTRAL | DECLINING_GROUP",
    )
    top_competitors: list[str] = Field(
        default_factory=list,
        description="Top 3-5 competitors",
    )
    is_category_leader: bool = Field(
        default=False,
        description="Top 1-3 in market share, revenue growth, or tech leadership",
    )
    market_leadership_context: str = Field(
        default="",
        description="1-2 sentence summary of market position",
    )
    growth_catalysts: str = Field(
        default="",
        description="Key growth drivers/catalysts",
    )
    thematic_momentum: str = Field(
        default="",
        description="Broader thematic/industry tailwinds",
    )
    error: Optional[str] = Field(
        default=None,
        description="Set on soft-fail (Tavily/LLM error message)",
    )


class VcpRatedStock(BaseModel):
    """Structural rating + context enrichment + final rating (post-cap)."""

    # Identity
    symbol: str
    exchange: str
    company_name: str = ""

    # Structural (Agent 1)
    structural_rating: Literal[1, 2, 3, 4, 5]
    structural_label: str
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
    final_rating: Literal[1, 2, 3, 4, 5] = Field(
        description="Final rating after down-only caps"
    )
    final_label: str = Field(description="Label for final_rating")
    cap_applied: bool = Field(
        default=False,
        description="True if down-only cap was applied",
    )
    cap_reason: str = Field(
        default="",
        description="Reason for cap (empty if no cap)",
    )
    error: Optional[str] = None


# --- Bucket envelopes ---


class VcpScanBucket(BaseModel):
    """Agent 1 output: structural rating buckets."""

    as_of: datetime = Field(default_factory=datetime.utcnow)
    universe_source: Literal["screener", "force", "hybrid"] = "screener"
    gates_applied: bool = True
    ratings: list[VcpStructuralRating] = Field(default_factory=list)
    five_star: list[VcpStructuralRating] = Field(default_factory=list)
    four_star: list[VcpStructuralRating] = Field(default_factory=list)
    three_star: list[VcpStructuralRating] = Field(default_factory=list)
    count: int = 0
    counts: dict[str, int] = Field(default_factory=lambda: {"5": 0, "4": 0, "3": 0})


class VcpEnrichedBucket(BaseModel):
    """Agent 2 output: context-enriched stocks."""

    count: int = 0
    stocks: list[VcpContextEnrichment] = Field(default_factory=list)


class VcpRatedBucket(BaseModel):
    """Agent 3 output: final rated stocks (sorted best→worst)."""

    count: int = 0
    stocks: list[VcpRatedStock] = Field(default_factory=list)


__all__ = [
    "IndustryGroupStrengthFlag",
    "STRUCTURAL_LABELS",
    "VcpContraction",
    "VcpContextEnrichment",
    "VcpEnrichedBucket",
    "VcpRatedBucket",
    "VcpRatedStock",
    "VcpScanBucket",
    "VcpStructuralRating",
]
