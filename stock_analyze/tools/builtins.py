"""The 4 built-in graph components (T12) + their real callables.

Callable contract: ``(inputs: dict[port_id, list[dict]], params: dict) ->
list[dict]``. Rows carry ``symbol``/``exchange`` plus opaque columns; a row
marked with ``ERROR_KEY`` is a soft-fail (dropped from the forward stream,
recorded by the walker). Builtin callables wrap the existing runners so a
graph run reuses the production scan/enrich/report paths.
"""

from __future__ import annotations

from typing import Any

from .protocol import ERROR_KEY, PortDef, ToolSpec
from .registry import register
from .variables import QUANT_VARS, REPORT_VARS, SCANNER_VARS, SEARCH_VARS

# ── row helpers ──────────────────────────────────────────────────────

def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("symbol") or "").upper(), str(row.get("exchange") or "NASDAQ").upper())


def _rows_from_payload(payload: dict[str, Any], family: str) -> list[dict[str, Any]]:
    """Flatten an execute_*_scan payload into rows (deduped by symbol key).

    EP's dual buckets overlap (strict ⊆ baseline, and feature mode mirrors
    the same survivor list into both) so EP rows are deduped by SymbolKey.
    """
    if family == "ep":
        stocks: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for bucket in ("baseline", "strict"):
            for s in payload.get(bucket, {}).get("stocks", []):
                item = s if isinstance(s, dict) else s.model_dump(mode="json")
                key = _key(item)
                if key in seen:
                    continue
                seen.add(key)
                stocks.append(item)
        return stocks

    ratings = payload.get("ratings", [])
    return [
        (r if isinstance(r, dict) else r.model_dump(mode="json")) for r in ratings
    ]


def _row_number(row: dict[str, Any], key: str, default: Any = None) -> Any:
    v = row.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ── Scanner (R1) ─────────────────────────────────────────────────────


def _ep_feature_keys(params: dict[str, Any]) -> list[str]:
    """EP feature keys whose per-feature toggle is ON (default: all on)."""
    from stock_analyze.scanners.ep.setup import FEATURE_KEYS

    return [k for k in FEATURE_KEYS if bool(params.get(f"ep_feature_{k}", True))]


def _ep_thresholds_from_params(params: dict[str, Any]) -> Any:
    """Build EpSetupThresholds from override vars, or None for defaults."""
    from stock_analyze.scanners.ep.setup import EpSetupThresholds

    mapping = {
        "spike_min": "ep_spike_min",
        "pullback_vol_ratio": "ep_pullback_vol_ratio",
        "pullback_depth_pct": "ep_pullback_depth_pct",
        "ema_touch_pct": "ep_ema_touch_pct",
        "vwap_touch_pct": "ep_vwap_touch_pct",
        "base_min_days": "ep_base_min_days",
        "base_max_days": "ep_base_max_days",
    }
    overrides = {attr: params[var] for attr, var in mapping.items() if var in params}
    return EpSetupThresholds(**overrides) if overrides else None


def _scanner_callable(inputs: dict[str, list[dict]], params: dict[str, Any]) -> list[dict]:
    from stock_analyze.pipeline import (
        execute_bo_scan,
        execute_ep_scan,
        execute_premarket_scan,
        execute_vcp_scan,
        execute_zhao_scan,
    )

    rows = inputs.get("universe") or []
    keys = [_key(r) for r in rows if r.get("symbol")]
    if not keys:
        return []

    family = str(params.get("family", "ep"))
    apply_gates = bool(params.get("ep_apply_gates", True))
    progress = params.get("__progress__")
    payload: dict[str, Any]
    if family == "vcp":
        payload = execute_vcp_scan(
            force_keys=keys,
            limit=int(params.get("ep_limit", 300)),
            apply_gates=apply_gates,
            batch_progress=progress,
        )
    elif family == "bo":
        payload = execute_bo_scan(
            force_keys=keys,
            limit=int(params.get("ep_limit", 300)),
            apply_gates=apply_gates,
            batch_progress=progress,
        )
    elif family == "zhao":
        payload = execute_zhao_scan(
            force_keys=keys,
            variant=str(params.get("zhao_variant", "realtime")),
            benchmark=str(params.get("zhao_benchmark", "SPY")),
            apply_gates=apply_gates,
            sma20_buffer_pct=float(params.get("zhao_sma20_buffer_pct", 0.0)),
            min_margin_pct=float(params.get("zhao_min_margin_pct", 1.0)),
            min_rs_pct=float(params.get("zhao_min_rs_pct", 0.0)),
            max_high_dist_pct=float(params.get("zhao_max_high_dist_pct", 15.0)),
            streaks=params.get("__streaks__"),
            batch_progress=progress,
        )
    elif family == "premarket":
        payload = execute_premarket_scan(
            force_keys=keys,
            min_change_pct=float(params.get("premarket_min_change_pct", 5.0)),
            min_vol_mult=float(params.get("premarket_min_vol_mult", 0.0)),
            cap=int(params.get("premarket_cap", 300)),
            apply_gates=apply_gates,
            batch_progress=progress,
        )
    elif family == "custom":
        raise ValueError(f"custom scan {params.get('scan_id')!r} not registered")
    else:  # ep
        payload = execute_ep_scan(
            force_keys=keys,
            select=str(params.get("ep_select", "strict")),
            limit=int(params.get("ep_limit", 300)),
            apply_gates=apply_gates,
            batch_progress=progress,
            ep_features=bool(params.get("ep_features_enabled", True)),
            ep_feature_keys=_ep_feature_keys(params),
            ep_keep_if_any=bool(params.get("ep_keep_if_any", True)),
            ep_thresholds=_ep_thresholds_from_params(params),
        )

    out = _rows_from_payload(payload, family if family != "custom" else "ep")
    return [r for r in out if r.get("symbol")]


# ── Quant (R2) — pure row-filter over scanner fields ────────────────


def _row_field(row: dict[str, Any], field: str) -> Any:
    """Resolve a filter field on a scanner row (nested ``context`` tolerated)."""
    if field in row:
        return row[field]
    ctx = row.get("context") or row.get("enrichment")
    if isinstance(ctx, dict) and field in ctx:
        return ctx[field]
    return None


def _quant_callable(inputs: dict[str, list[dict]], params: dict[str, Any]) -> list[dict]:
    rows = inputs.get("in") or []
    q_min_adv = float(params.get("q_min_adv_dollar", 0))
    q_min_mcap = float(params.get("q_min_market_cap", 0))
    q_rs = float(params.get("q_rs_floor", 0))
    q_struct = float(params.get("q_structural_floor", 0))
    q_impulse = float(params.get("q_bo_min_impulse", 0))
    q_adr_lo = float(params.get("q_bo_adr_lo", 0))
    q_adr_hi = float(params.get("q_bo_adr_hi", 1e12))
    q_base_min = int(params.get("q_bo_base_min", 0))
    q_base_max = int(params.get("q_bo_base_max", 1e9))
    q_vci = float(params.get("q_bo_vci_max", 1e9))
    q_surf = float(params.get("q_bo_surfing", 1e9))
    q_surge = float(params.get("q_bo_surge_min", 0))
    q_dryup = float(params.get("q_bo_dryup", 1e9))

    kept: list[dict[str, Any]] = []
    for row in rows:
        errors: list[str] = []
        adv = _row_field(row, "adv_20d")
        if q_min_adv and adv is None:
            errors.append("missing adv_20d")
        if q_min_mcap and _row_field(row, "market_cap") is None:
            errors.append("missing market_cap")
        rs = _row_field(row, "rs_rating")
        if q_rs and rs is None:
            errors.append("missing rs_rating")
        struct = _row_field(row, "structural_rating")
        if q_struct and struct is None:
            errors.append("missing structural_rating")

        if errors:
            row = dict(row)
            row[ERROR_KEY] = ", ".join(errors)
            kept.append(row)
            continue

        ok = True
        if q_min_adv and _row_number(row, "adv_20d") < q_min_adv:
            ok = False
        if q_min_mcap and _row_number(row, "market_cap") < q_min_mcap:
            ok = False
        if q_rs and _row_number(row, "rs_rating") < q_rs:
            ok = False
        if q_struct and _row_number(row, "structural_rating") < q_struct:
            ok = False
        if q_impulse and _row_number(row, "prior_impulse_pct") < q_impulse:
            ok = False
        adr = _row_number(row, "adr20_pct")
        if adr is not None and not (q_adr_lo <= adr <= q_adr_hi):
            ok = False
        bd = _row_number(row, "base_duration_days")
        if bd is not None and not (q_base_min <= bd <= q_base_max):
            ok = False
        if q_vci and _row_number(row, "vci_ratio") > q_vci:
            ok = False
        if q_surf and _row_number(row, "surfing_dist_pct") > q_surf:
            ok = False
        if q_surge and _row_number(row, "surge_pct") < q_surge:
            ok = False
        if q_dryup and _row_number(row, "dryup_ratio") > q_dryup:
            ok = False
        if ok:
            kept.append(row)

    return kept


# ── Search (R3) — LLM context enrichment ────────────────────────────


def _is_structural(row: dict[str, Any]) -> bool:
    """A row is a structural (VCP or BO) lane when it carries a structural
    rating or a BO funnel-star rating — BO rows have no ``structural_rating``
    but do carry ``funnel_stars``."""
    return row.get("structural_rating") is not None or row.get("funnel_stars") is not None


def _search_callable(inputs: dict[str, list[dict]], params: dict[str, Any]) -> list[dict]:
    from stock_analyze.agents.catalyst import enrich_with_catalysts
    from stock_analyze.agents.enrichment import enrich_with_vcp_context
    from stock_analyze.agents.rating import rate_ep_catalysts
    from stock_analyze.tools.control import checkpoint_for

    rows = inputs.get("in") or []
    vcp_rows = [r for r in rows if _is_structural(r)]
    ep_rows = [r for r in rows if not _is_structural(r)]

    checkpoint = checkpoint_for(params.get("__control_id__"))
    progress = params.get("__progress__")
    on_ticker = progress.ticker if progress is not None else None

    out: list[dict[str, Any]] = []

    # VCP path: Tavily dual-query enrichment (per-symbol soft-fail).
    if vcp_rows:
        context_map: dict[tuple[str, str], dict[str, Any]] = {}
        if progress is not None:
            progress.begin_ticker(len(vcp_rows), "VCP enrichment", throttle=1)
        enriched = enrich_with_vcp_context(
            vcp_rows, checkpoint=checkpoint, on_ticker=on_ticker,
        )
        if progress is not None:
            progress.end_ticker()
        for c in enriched:
            item = c if isinstance(c, dict) else c.model_dump(mode="json")
            key = (str(item.get("symbol") or "").upper(), str(item.get("exchange") or "NASDAQ").upper())
            context_map[key] = item
        for row in vcp_rows:
            row = dict(row)
            ctx = context_map.get(_key(row))
            if ctx is not None and ctx.get("error"):
                row[ERROR_KEY] = str(ctx["error"])
            elif ctx is not None:
                row["enrichment"] = ctx
            out.append(row)

    # EP path: catalyst search + LLM rating (Agent 2 + Agent 3 chain).
    if ep_rows:
        if progress is not None:
            progress.begin_ticker(len(ep_rows), "Catalyst search", throttle=1)
        enriched = enrich_with_catalysts(
            ep_rows, checkpoint=checkpoint, on_ticker=on_ticker,
        )
        if progress is not None:
            progress.end_ticker()
        if progress is not None:
            progress.begin_ticker(len(enriched), "EP rating", throttle=1)
        rated = rate_ep_catalysts(
            enriched, checkpoint=checkpoint, on_ticker=on_ticker,
        )
        if progress is not None:
            progress.end_ticker()
        rated_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for r in rated:
            item = r if isinstance(r, dict) else r.model_dump(mode="json")
            rated_by_key[(str(item.get("symbol") or "").upper(), str(item.get("exchange") or "NASDAQ").upper())] = item
        for row in ep_rows:
            row = dict(row)
            rated_item = rated_by_key.get(_key(row))
            if rated_item is None:
                row[ERROR_KEY] = "catalyst rating unavailable"
            elif rated_item.get("ep_rating") is None:
                row[ERROR_KEY] = str(rated_item.get("ep_rationale") or "catalyst rating failed")
            else:
                row["ep_rating"] = rated_item["ep_rating"]
                row["catalyst_type"] = rated_item.get("catalyst_type")
                row["catalyst_summary"] = rated_item.get("catalyst_summary", "")
                row["ep_rationale"] = rated_item.get("ep_rationale", "")
            out.append(row)

    return out


# ── Report (R4) — normalize, sort, cap ───────────────────────────────


def extract_rating(row: dict[str, Any]) -> float:
    """Best-effort numeric rating from any row shape."""
    for k in ("ep_rating", "funnel_stars", "rating", "structural_rating", "strength"):
        v = row.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return 0.0


def _report_callable(inputs: dict[str, list[dict]], params: dict[str, Any]) -> list[dict]:
    rows = inputs.get("structural") or []
    min_rating = float(params.get("min_rating", 0))
    apply_caps = bool(params.get("apply_caps", True))

    out: list[dict[str, Any]] = []
    for row in rows:
        row = dict(row)
        rating = extract_rating(row)
        if apply_caps and rating > 0:
            rating = _apply_caps(row, rating, params)
        row["rating"] = rating
        row["lanes"] = "component-graph"
        if rating >= min_rating:
            out.append(row)

    out.sort(key=lambda r: (extract_rating(r), _key(r)), reverse=True)
    return out


def _apply_caps(row: dict[str, Any], rating: float, params: dict[str, Any]) -> float:
    """Down-only caps: never raise a rating, only clamp it.

    Caps are EP-lane semantics; only apply them to rows that actually carry
    catalyst fields (``catalyst_type`` exists on EpRatedStock). VCP/BO lanes
    have no catalyst concept and are never clamped by these caps.
    """
    if "catalyst_type" not in row:
        return rating

    capped = rating
    has_catalyst = bool(row.get("catalyst_type")) and row.get("catalyst_type") != "NONE"
    if not has_catalyst:
        capped = min(capped, float(params.get("cap_no_catalyst", 2)))
    catalyst_type = str(row.get("catalyst_type") or "").upper()
    if catalyst_type == "PR":
        capped = min(capped, float(params.get("cap_pr", 3)))
    if catalyst_type in ("CONTRACT", "FDA"):
        capped = min(capped, float(params.get("cap_contract_fda", 4)))
    rvol = _row_number(row, "rvol10")
    if rvol is not None and rvol < 3:
        capped = min(capped, float(params.get("cap_rvol10", 4)))
    return capped


# ── ToolSpec definitions ─────────────────────────────────────────────


def _ports(in_ports: list[tuple[str, str, bool, str]], out_ports: list[tuple[str, str, bool, str]]):
    def _p(items):
        return [PortDef(id=i, type=t, required=r, label=l) for i, t, r, l in items]

    return _p(in_ports), _p(out_ports)


SCANNER_IN, SCANNER_OUT = _ports(
    [("universe", "symbolkey", True, "symbols")],
    [("bucket", "scan_rows", True, "scan rows")],
)
QUANT_IN, QUANT_OUT = _ports(
    [("in", "filtered_rows", True, "rows")],
    [("out", "filtered_rows", True, "filtered rows")],
)
SEARCH_IN, SEARCH_OUT = _ports(
    [("in", "enriched_rows", True, "rows")],
    [("out", "enriched_rows", True, "enriched rows")],
)
REPORT_IN, REPORT_OUT = _ports(
    [
        ("structural", "report_rows", True, "rows"),
        ("context", "enriched_rows", False, "context"),
    ],
    [("rated", "report_rows", True, "report rows")],
)

SCANNER = ToolSpec(
    id="scanner",
    name="Scanner",
    description="Technical screening",
    phase=1,
    inputs=SCANNER_IN,
    outputs=SCANNER_OUT,
    variables=SCANNER_VARS,
    callable=_scanner_callable,
)

QUANT = ToolSpec(
    id="quant",
    name="Quant Filter / Gate",
    description="Gate & threshold filters",
    phase=2,
    inputs=QUANT_IN,
    outputs=QUANT_OUT,
    variables=QUANT_VARS,
    callable=_quant_callable,
)

SEARCH = ToolSpec(
    id="search",
    name="AI Search",
    description="LLM news / catalyst search",
    phase=3,
    inputs=SEARCH_IN,
    outputs=SEARCH_OUT,
    variables=SEARCH_VARS,
    callable=_search_callable,
)

REPORT = ToolSpec(
    id="report",
    name="Report",
    description="Rating, ranking, caps",
    phase=4,
    inputs=REPORT_IN,
    outputs=REPORT_OUT,
    variables=REPORT_VARS,
    callable=_report_callable,
)

for _spec in (SCANNER, QUANT, SEARCH, REPORT):
    register(_spec.id)(_spec)


__all__ = [
    "QUANT",
    "REPORT",
    "SCANNER",
    "SEARCH",
    "extract_rating",
]
