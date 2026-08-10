"""BO gates — liquidity reuse, ADR20 envelope, structural gate, rated-stock builder."""

from typing import Optional

from stock_analyze.models.bo import BO_LABELS, BoRatedStock, BoSetupRating
from stock_analyze.models.vcp import VcpContextEnrichment
from stock_analyze.scanners.vcp.gates import apply_vcp_caps, passes_liquidity_gate

ADR_LO = 4.0
ADR_HI = 12.0


def passes_adr_envelope(adr20: float, lo: float = ADR_LO, hi: float = ADR_HI) -> bool:
    """ADR20 must sit within [4%, 12%] — reject sluggish and excessive-spread names."""
    return lo <= adr20 <= hi


def passes_bo_gate(rating: BoSetupRating) -> bool:
    """Post-detection gate: only 4-5★ survivors pass to enrichment."""
    return rating.rating >= 4


def build_bo_rated_stock(
    setup: BoSetupRating,
    context: VcpContextEnrichment,
) -> BoRatedStock:
    """Merge setup rating + context enrichment → final rated stock.

    Reuses the shared down-only cap logic (``apply_vcp_caps``) from the VCP
    pipeline; only the merge structure is BO-specific.
    """
    final_rating, cap_applied, cap_reason = apply_vcp_caps(setup.rating, context)
    label = BO_LABELS.get(final_rating, "sub_standard")

    return BoRatedStock(
        symbol=setup.symbol,
        exchange=setup.exchange,
        company_name=context.symbol,  # Overridden by the runner with the real name.
        setup_rating=setup.rating,
        setup_label=setup.label,
        variant=setup.variant,
        as_of=setup.as_of,
        sector=context.sector,
        industry=context.industry,
        industry_group_strength_flag=context.industry_group_strength_flag,
        is_category_leader=context.is_category_leader,
        market_leadership_context=context.market_leadership_context,
        growth_catalysts=context.growth_catalysts,
        thematic_momentum=context.thematic_momentum,
        top_competitors=context.top_competitors,
        final_rating=final_rating,  # type: ignore[arg-type]
        final_label=label,
        cap_applied=cap_applied,
        cap_reason=cap_reason,
        error=context.error,
    )


__all__ = [
    "ADR_HI",
    "ADR_LO",
    "build_bo_rated_stock",
    "passes_adr_envelope",
    "passes_bo_gate",
    "passes_liquidity_gate",
]
