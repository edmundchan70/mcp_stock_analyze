"""Finalized VariableDef surfaces for the 4 built-in components (T14-17).

Defaults sourced from ticket 01 inventory
(``.scratch/pipeline-graph-editor/issues/01-inventory-phase-inspector-tunables.md``)
and the component stub's ``SCANNER_VARS``/``QUANT_VARS``/``SEARCH_VARS``/
``REPORT_VARS`` pools. Quant exposes only *filterable* thresholds — deep
scoring rubric params (contraction counts, trough factor, tight-close CV) are
NOT exposed in v1 (T19: Quant is a pure row-filter over scanner fields).
"""

from __future__ import annotations

from .protocol import VariableDef

# ── Scanner (R1) ─────────────────────────────────────────────────────

SCANNER_VARS: list[VariableDef] = [
    VariableDef("family", "Screening family", "select", "ep",
                "Family", ["ep", "vcp", "bo", "custom"]),
    # EP
    VariableDef("ep_select", "Gate bucket", "select", "strict", "EP", ["strict", "baseline", "both"]),
    VariableDef("ep_limit", "Universe cap", "number", 300, "EP"),
    VariableDef("ep_apply_gates", "Apply gates", "boolean", True, "EP"),
    VariableDef("ep_base_min_price", "Base: min price", "number", 1.0, "EP baseline"),
    VariableDef("ep_base_min_gap_pct", "Base: min gap %", "number", 4.0, "EP baseline"),
    VariableDef("ep_base_min_rvol10", "Base: min RVOL10", "number", 1.5, "EP baseline"),
    VariableDef("ep_strict_min_price", "Strict: min price", "number", 10.0, "EP strict"),
    VariableDef("ep_strict_min_gap_pct", "Strict: min gap %", "number", 8.0, "EP strict"),
    VariableDef("ep_strict_min_rvol10", "Strict: min RVOL10", "number", 3.0, "EP strict"),
    VariableDef("ep_strict_min_mcap", "Strict: min market cap", "number", 300_000_000, "EP strict"),
    VariableDef("ep_strict_max_mcap", "Strict: max market cap", "number", 10_000_000_000, "EP strict"),
    VariableDef("ep_strict_min_adv_50d", "Strict: 50d ADV$", "number", 5_000_000, "EP strict"),
    VariableDef("ep_strict_min_event_dollar", "Strict: event-day $ vol", "number", 20_000_000, "EP strict"),
    # VCP
    VariableDef("vcp_min_adv_dollar", "Liquidity ADV$", "number", 10_000_000, "VCP"),
    VariableDef("vcp_adv_window", "ADV$ window (d)", "number", 60, "VCP"),
    VariableDef("vcp_min_market_cap", "Min market cap", "number", 300_000_000, "VCP"),
    VariableDef("vcp_rs_floor", "Stage-2 RS floor", "number", 70.0, "VCP"),
    VariableDef("vcp_structural_floor", "Structural gate floor", "number", 4, "VCP"),
    # BO
    VariableDef("bo_min_impulse_pct", "Min impulse %", "number", 30.0, "BO"),
    VariableDef("bo_adr_lo", "ADR20 low", "number", 4.0, "BO"),
    VariableDef("bo_adr_hi", "ADR20 high", "number", 12.0, "BO"),
    VariableDef("bo_base_min_days", "Base min days", "number", 5, "BO"),
    VariableDef("bo_base_max_days", "Base max days", "number", 40, "BO"),
    VariableDef("bo_vci_max", "Max VCI", "number", 0.65, "BO"),
    VariableDef("bo_surfing_max_pct", "Max surfing %", "number", 8.0, "BO"),
    VariableDef("bo_surge_min", "Surge min", "number", 1.5, "BO"),
    VariableDef("bo_profile", "Funnel profile", "select", "best", "BO", ["best", "moderate-lose", "widen"]),
    # Custom
    VariableDef("scan_id", "Registered scan", "select", "momentum", "Custom", ["momentum", "gapper", "rs_leader"]),
]

# Scanner shows only the groups of its selected family.
SCANNER_GROUPS: dict[str, list[str]] = {
    "ep": ["Family", "EP", "EP baseline", "EP strict"],
    "vcp": ["Family", "VCP"],
    "bo": ["Family", "BO"],
    "custom": ["Family", "Custom"],
}


def scanner_visible_vars(family: str) -> list[VariableDef]:
    """Scanner variables for a family (family select + its threshold groups)."""
    groups = SCANNER_GROUPS.get(family, SCANNER_GROUPS["ep"])
    return [v for v in SCANNER_VARS if v.group in groups]


# ── Quant Filter/Gate (R2) ───────────────────────────────────────────

QUANT_VARS: list[VariableDef] = [
    VariableDef("q_min_adv_dollar", "Min ADV$", "number", 10_000_000, "Liquidity"),
    VariableDef("q_adv_window", "ADV$ window (d)", "number", 60, "Liquidity"),
    VariableDef("q_min_market_cap", "Min market cap", "number", 300_000_000, "Market cap"),
    VariableDef("q_rs_floor", "Stage-2 RS floor", "number", 70.0, "Stage 2 trend"),
    VariableDef("q_structural_floor", "Structural floor", "number", 4, "Structural rating"),
    VariableDef("q_bo_min_impulse", "Min impulse %", "number", 30.0, "BO essentials"),
    VariableDef("q_bo_adr_lo", "ADR20 low", "number", 4.0, "BO essentials"),
    VariableDef("q_bo_adr_hi", "ADR20 high", "number", 12.0, "BO essentials"),
    VariableDef("q_bo_base_min", "Base min days", "number", 5, "BO essentials"),
    VariableDef("q_bo_base_max", "Base max days", "number", 40, "BO essentials"),
    VariableDef("q_bo_vci_max", "Max VCI", "number", 0.65, "BO essentials"),
    VariableDef("q_bo_surfing", "Max surfing %", "number", 8.0, "BO essentials"),
    VariableDef("q_bo_surge_min", "Surge min", "number", 1.5, "BO essentials"),
    VariableDef("q_bo_dryup", "Max dry-up ×", "number", 0.5, "BO essentials"),
    VariableDef("q_bo_profile", "Funnel profile", "select", "best", "BO funnel", ["best", "moderate-lose", "widen"]),
    VariableDef("q_qbase_5", "Q_base 5★ floor", "number", 90, "BO funnel"),
    VariableDef("q_qbase_4", "Q_base 4★ floor", "number", 75, "BO funnel"),
    VariableDef("q_qbase_3", "Q_base 3★ floor", "number", 60, "BO funnel"),
]

# Fields the Quant filter reads off scanner rows. A row missing a required
# filter field is soft-failed with an ``error`` marker (T19).
QUANT_FIELD_KEYS: dict[str, str] = {
    "q_min_adv_dollar": "adv_20d",          # BO funnel field on BoSetupRating
    "q_min_market_cap": "market_cap",       # resolved ticker detail
    "q_rs_floor": "rs_rating",              # VCP / BO RS line
    "q_structural_floor": "structural_rating",  # VCP structural rating
    "q_bo_min_impulse": "prior_impulse_pct",
    "q_bo_adr_lo": "adr20_pct",
    "q_bo_adr_hi": "adr20_pct",
    "q_bo_base_min": "base_duration_days",
    "q_bo_base_max": "base_duration_days",
    "q_bo_vci_max": "vci_ratio",
    "q_bo_surfing": "surfing_dist_pct",
    "q_bo_surge_min": "surge_pct",
    "q_bo_dryup": "dryup_ratio",
}

# ── AI Search (R3) ───────────────────────────────────────────────────

SEARCH_VARS: list[VariableDef] = [
    VariableDef("topic", "Search topic", "select", "finance", "Query", ["finance", "news", "general"]),
    VariableDef("depth", "Search depth", "select", "advanced", "Query", ["basic", "advanced"]),
    VariableDef("time_range", "Time range", "select", "month", "Query", ["day", "week", "month", "year"]),
    VariableDef("max_results", "Max results / symbol", "number", 5, "Query"),
    VariableDef("taxonomy_query", "Sector taxonomy query", "boolean", True, "Queries"),
    VariableDef("leadership_query", "Market leadership query", "boolean", True, "Queries"),
    VariableDef("confirm_threshold", "Confirm above N symbols", "number", 50, "Confirmation"),
    VariableDef("prompt_template", "Compression prompt", "text", "Summarize the catalyst and leadership context for {symbol}.", "LLM"),
]

# ── Report (R4) ──────────────────────────────────────────────────────

REPORT_VARS: list[VariableDef] = [
    VariableDef("report_format", "Report format", "select", "ranked", "Output", ["ranked", "watchlist", "full"]),
    VariableDef("min_rating", "Min rating to include", "number", 4, "Output"),
    VariableDef("apply_caps", "Apply down-only caps", "boolean", True, "Caps"),
    VariableDef("cap_no_catalyst", "Cap: no catalyst", "number", 2, "Caps"),
    VariableDef("cap_pr", "Cap: PR", "number", 3, "Caps"),
    VariableDef("cap_contract_fda", "Cap: CONTRACT / FDA", "number", 4, "Caps"),
    VariableDef("cap_rvol10", "Cap: RVOL10 < 3", "number", 4, "Caps"),
]


__all__ = [
    "QUANT_FIELD_KEYS",
    "QUANT_VARS",
    "REPORT_VARS",
    "SCANNER_GROUPS",
    "SCANNER_VARS",
    "SEARCH_VARS",
    "scanner_visible_vars",
]
