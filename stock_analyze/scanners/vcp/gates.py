"""VCP Stage 2 gate, liquidity gate, and structural gate predicates + down-only cap logic."""

import pandas as pd

# Shared ADV$ threshold — matches screener.py:fetch_us_vcp_universe min_adv default.
# Any stock whose 60d average daily dollar volume is below this is untradeable.
MIN_ADV_DOLLAR = 10_000_000

from stock_analyze.models.vcp import (
    IndustryGroupStrengthFlag,
    VcpContextEnrichment,
    VcpRatedStock,
    VcpStructuralRating,
)


def compute_adv_dollar(df: pd.DataFrame, window: int = 60) -> float:
    """Compute average daily dollar volume from OHLCV DataFrame.

    Uses the last ``window`` bars of (volume × close).
    """
    if df is None or len(df) < window:
        return 0.0
    avg_volume = float(df["volume"].tail(window).mean())
    close = float(df["close"].iloc[-1])
    return avg_volume * close


def passes_liquidity_gate(
    df: pd.DataFrame,
    min_adv: float = MIN_ADV_DOLLAR,
    window: int = 60,
) -> bool:
    """Hard pre-requisite: 60d ADV$ >= threshold.

    This mirrors the screener pre-filter (average_volume_60d_calc × close)
    and is enforced post-OHLCV-fetch on every stock — including force-included
    symbols that never passed through the TradingView screener.
    """
    return compute_adv_dollar(df, window=window) >= min_adv


def passes_stage2_gate(rating: VcpStructuralRating) -> bool:
    """Pre-VCP filter: RS < 70 or non-Stage-2 → discard."""
    return rating.stage2_trend and rating.rs_rating >= 70.0


def passes_vcp_gate(rating: VcpStructuralRating) -> bool:
    """Post-detection gate: only 4-5★ survive to enrichment."""
    return rating.structural_rating >= 4


# ── Market-Cap Gate ──────────────────────────────────────────────

MIN_MARKET_CAP = 300_000_000  # $300M — strict gate floor shared by VCP/BO (post-screener)


def passes_market_cap_gate(
    market_cap: float | None,
    min_mcap: float = MIN_MARKET_CAP,
) -> bool:
    """Post-screener replacement: market_cap >= $300M hard gate.

    None / missing market_cap always rejects (conservative).
    """
    if market_cap is None:
        return False
    try:
        return float(market_cap) >= min_mcap
    except (TypeError, ValueError):
        return False


# ── Down-Only Caps ─────────────────────────────────────────────────


def apply_vcp_caps(
    structural_rating: int,
    context: VcpContextEnrichment,
) -> tuple[int, bool, str]:
    """Apply down-only caps from context enrichment to structural rating.

    Context can only cap (never boost) the structural rating.

    Returns (final_rating, cap_applied, cap_reason).
    """
    rating = structural_rating
    flag = context.industry_group_strength_flag
    is_leader = context.is_category_leader

    # 3★ stays 3★ regardless of context
    if rating <= 3:
        return rating, False, ""

    cap_applied = False
    cap_reason = ""

    if rating == 5:
        if not is_leader:
            rating = 4
            cap_applied = True
            cap_reason = "non-leader cap (5★ → 4★)"
        elif flag == "DECLINING_GROUP":
            rating = 4
            cap_applied = True
            cap_reason = "declining sector cap (5★ → 4★)"
        # leader + HOT_SECTOR or NEUTRAL → 5★ (no cap)

    elif rating == 4:
        if flag == "DECLINING_GROUP":
            rating = 3
            cap_applied = True
            cap_reason = "declining sector cap (4★ → 3★)"

    return rating, cap_applied, cap_reason


def build_rated_stock(
    structural: VcpStructuralRating,
    context: VcpContextEnrichment,
) -> VcpRatedStock:
    """Merge structural rating + context enrichment → final rated stock."""
    final_rating, cap_applied, cap_reason = apply_vcp_caps(
        structural.structural_rating, context
    )

    from stock_analyze.models.vcp import STRUCTURAL_LABELS

    label = STRUCTURAL_LABELS.get(final_rating, "sub_standard")

    return VcpRatedStock(
        symbol=structural.symbol,
        exchange=structural.exchange,
        company_name=context.symbol,  # Will be overridden by runner
        structural_rating=structural.structural_rating,
        structural_label=structural.structural_label,
        as_of=structural.as_of,
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
