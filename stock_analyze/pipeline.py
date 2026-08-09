"""Daily Run pipeline — stamped Agent 1→2→3 chain (scheduler-ready)."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence

from dotenv import load_dotenv

from stock_analyze.agents.catalyst import enrich_with_catalysts, load_stocks_from_input
from stock_analyze.agents.enrichment import enrich_with_vcp_context, load_vcp_stocks_from_input
from stock_analyze.agents.rating import rate_ep_catalysts
from stock_analyze.data.screener import fetch_symbols, fetch_us_ep_universe, fetch_us_vcp_universe
from stock_analyze.data.symbols import SymbolKey, row_symbol_key
from stock_analyze.data.tradingview import enrich_with_retry
from stock_analyze.models.catalyst import CatalystBucket
from stock_analyze.models.rating import EpRatedStock, RatedBucket
from stock_analyze.models.vcp import VcpEnrichedBucket, VcpRatedBucket, VcpRatedStock, VcpScanBucket
from stock_analyze.progress import RunProgress, build_rating_table
from stock_analyze.scanners.ep.gates import BASELINE
from stock_analyze.scanners.ep.runner import merge_force_rows, run_ep_scan
from stock_analyze.scanners.vcp.gates import build_rated_stock
from stock_analyze.scanners.vcp.runner import merge_vcp_force_rows as _merge_vcp_force_rows
from stock_analyze.scanners.vcp.runner import run_vcp_scan

logger = logging.getLogger(__name__)

GateSelect = Literal["baseline", "strict", "both"]
AnalysisMethod = Literal["ep_rating"]
TickerFn = Callable[[int, int, str, str], None]
StageFn = Callable[[str], None]

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


def _now() -> datetime:
    return datetime.now()


def sanitize_run_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name.strip()).strip("_")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        raise ValueError("Run name must contain letters, digits, '_' or '-'")
    return cleaned


@dataclass
class RunConfig:
    name: str
    select: GateSelect = "strict"
    run_catalyst: bool = True
    analysis_method: Optional[AnalysisMethod] = "ep_rating"
    limit: int = 300
    force_keys: Optional[list[SymbolKey]] = None
    use_screener: bool = True
    apply_gates: bool = True
    output_root: Path = field(default_factory=lambda: Path("output"))
    min_rating: int = 4
    pipeline_type: str = "daily_ep_scan"


@dataclass
class RunResult:
    exit_code: int
    run_dir: Path
    steps_completed: list[str] = field(default_factory=list)
    error: Optional[str] = None


def create_run_dir(config: RunConfig) -> Path:
    name = sanitize_run_name(config.name)
    now = _now()
    run_dir = Path(config.output_root) / now.strftime("%Y-%m-%d") / f"{now.strftime('%H%M%S')}_{name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_meta(run_dir: Path, meta: dict[str, Any]) -> None:
    _write_json(run_dir / "run_meta.json", meta)


def execute_ep_scan(
    *,
    force_keys: Optional[Sequence[SymbolKey]] = None,
    select: GateSelect,
    limit: int,
    use_screener: bool = True,
    apply_gates: bool = True,
    on_stage: Optional[StageFn] = None,
) -> dict[str, Any]:
    """Run Agent 1 and return selected JSON payload.

    Always attaches ``_counts`` (baseline/strict) for CLI logging; callers that
    persist the payload should strip it via :func:`strip_internal_keys`.

    When ``use_screener`` is False, the Universe is only ``force_keys`` (paste-only).

    When ``on_stage`` is given, it is called with a short description before
    each major step so a Run Progress reporter can show Agent 1 substeps.
    """
    force_key_list: list[SymbolKey] = list(force_keys or [])
    if not use_screener and not force_key_list:
        raise ValueError("use_screener=False requires non-empty force_keys")

    if use_screener:
        if on_stage is not None:
            on_stage("fetching universe (screener)")
        try:
            screener_rows = fetch_us_ep_universe(
                min_price=BASELINE.min_price,
                min_gap_pct=BASELINE.min_gap_pct,
                min_rvol10=BASELINE.min_rvol10,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("Screener fetch failed: %s — continuing with force-only universe", exc)
            screener_rows = []
    else:
        screener_rows = []

    force_rows: list = []
    failed_force: list[dict[str, str]] = []
    if force_key_list:
        if on_stage is not None:
            on_stage("fetching force symbols")
        try:
            force_rows = fetch_symbols(force_key_list)
        except Exception as exc:
            logger.warning("Force-symbol fetch failed: %s — falling back to OHLCV enrichment", exc)
            force_rows = []
        found_keys = {row_symbol_key(r) for r in force_rows}
        missing = [(s, e) for s, e in force_key_list if (s, e) not in found_keys]
        total_missing = len(missing)
        for enrich_idx, (sym, exch) in enumerate(missing, start=1):
            logger.info(
                "[%d/%d] enriching %s:%s — screener missed, trying OHLCV...",
                enrich_idx,
                total_missing,
                exch,
                sym,
            )
            t0 = time.perf_counter()
            result = enrich_with_retry(sym, exch)
            elapsed_s = time.perf_counter() - t0
            if result.ok:
                logger.info(
                    "[%d/%d] enrich %s:%s — ok (%.1fs)",
                    enrich_idx,
                    total_missing,
                    exch,
                    sym,
                    elapsed_s,
                )
                force_rows.append(result.row)
            else:
                logger.warning(
                    "[%d/%d] enrich %s:%s — FAIL (%.1fs)\n  errors: %s",
                    enrich_idx,
                    total_missing,
                    exch,
                    sym,
                    elapsed_s,
                    result.errors,
                )
                failed_force.append({
                    "symbol": sym.upper(),
                    "exchange": exch.upper(),
                    "errors": result.errors,
                })

    if on_stage is not None:
        on_stage("running scan")
    rows, force_set, source = merge_force_rows(screener_rows, force_key_list, force_rows)
    result = run_ep_scan(
        rows=rows,
        as_of=date.today(),
        force_keys=force_set,
        universe_source=source,
        apply_gates=apply_gates,
    )
    payload = result.model_dump_selected(select)
    payload["_counts"] = {
        "baseline": result.baseline.count,
        "strict": result.strict.count,
    }
    if failed_force:
        payload["_failed_force"] = failed_force
    return payload


def strip_internal_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop pipeline-only keys before writing Run Artifacts / CLI --out files."""
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def execute_catalyst_enrich(
    stocks: Sequence[Any],
    *,
    on_ticker: Optional[TickerFn] = None,
) -> dict[str, Any]:
    load_dotenv()
    enriched = enrich_with_catalysts(stocks, on_ticker=on_ticker)
    return CatalystBucket(count=len(enriched), stocks=enriched).model_dump(mode="json")


def execute_ep_rating(
    stocks: Sequence[Any],
    *,
    on_ticker: Optional[TickerFn] = None,
) -> tuple[dict[str, Any], list[EpRatedStock]]:
    load_dotenv()
    rated = rate_ep_catalysts(stocks, on_ticker=on_ticker)
    payload = RatedBucket(count=len(rated), stocks=rated).model_dump(mode="json")
    return payload, rated


def format_rating_table(stocks: list[EpRatedStock], *, min_rating: int = 4) -> str:
    visible = [s for s in stocks if s.ep_rating >= min_rating]
    if not visible:
        return "(no names at this min-rating)"
    lines = ["stars  symbol   type       rationale"]
    for s in visible:
        lines.append(
            f"{s.ep_rating}★     {s.symbol:<8} {s.catalyst_type:<10} {s.ep_rationale}"
        )
    return "\n".join(lines)


def execute_vcp_scan(
    *,
    force_keys: Optional[Sequence[SymbolKey]] = None,
    limit: int = 300,
    use_screener: bool = True,
    apply_gates: bool = True,
    on_stage: Optional[StageFn] = None,
    batch_progress: Any = None,
) -> dict[str, Any]:
    """Run VCP Agent 1 and return scan bucket payload.

    Always attaches ``_counts`` (5/4/3★) for CLI logging; callers that
    persist the payload should strip it via :func:`strip_internal_keys`.

    Args:
        batch_progress: Optional RunProgress for live batch OHLCV ticker.
    """
    force_key_list: list[SymbolKey] = list(force_keys or [])
    if not use_screener and not force_key_list:
        raise ValueError("use_screener=False requires non-empty force_keys")

    if use_screener:
        if on_stage is not None:
            on_stage("fetching VCP universe (screener)")
        try:
            screener_rows = fetch_us_vcp_universe(limit=limit)
        except Exception as exc:
            logger.warning("VCP screener fetch failed: %s — continuing with force-only", exc)
            screener_rows = []
    else:
        screener_rows = []

    force_rows_result: list = []
    failed_force: list[dict[str, str]] = []
    if force_key_list:
        if on_stage is not None:
            on_stage("fetching force symbols")
        try:
            force_rows_result = fetch_symbols(force_key_list, limit=200)
        except Exception as exc:
            logger.warning("Force-symbol fetch failed: %s", exc)
            force_rows_result = []
        found_keys = {row_symbol_key(r) for r in force_rows_result}
        missing = [(s, e) for s, e in force_key_list if (s, e) not in found_keys]
        total_missing = len(missing)
        for enrich_idx, (sym, exch) in enumerate(missing, start=1):
            logger.info(
                "[%d/%d] enriching %s:%s — screener missed, trying OHLCV...",
                enrich_idx, total_missing, exch, sym,
            )
            t0 = time.perf_counter()
            result = enrich_with_retry(sym, exch)
            elapsed_s = time.perf_counter() - t0
            if result.ok:
                logger.info(
                    "[%d/%d] enrich %s:%s — ok (%.1fs)",
                    enrich_idx, total_missing, exch, sym, elapsed_s,
                )
                force_rows_result.append(result.row)
            else:
                logger.warning(
                    "[%d/%d] enrich %s:%s — FAIL (%.1fs)\n  errors: %s",
                    enrich_idx, total_missing, exch, sym, elapsed_s, result.errors,
                )
                failed_force.append({
                    "symbol": sym.upper(),
                    "exchange": exch.upper(),
                    "errors": result.errors,
                })

    if on_stage is not None:
        on_stage("running VCP scan")

    force_set = {(s.upper(), e.upper()) for s, e in force_key_list}

    bucket = run_vcp_scan(
        screener_rows=screener_rows,
        force_keys=force_set,
        force_rows=force_rows_result,
        universe_source="hybrid" if screener_rows and force_key_list else ("screener" if screener_rows else "force"),
        apply_gates=apply_gates,
        batch_progress=batch_progress,
    )
    payload = bucket.model_dump(mode="json")
    payload["_counts"] = bucket.counts
    if failed_force:
        payload["_failed_force"] = failed_force
    return payload


def execute_vcp_enrichment(
    stocks: Sequence[Any],
    *,
    on_ticker: Optional[TickerFn] = None,
) -> dict[str, Any]:
    """Run VCP Agent 2 (context enrichment) and Agent 3 (final rating).

    Returns VCP rated bucket payload.
    """
    load_dotenv()

    # Agent 2: Context enrichment
    enriched = enrich_with_vcp_context(stocks, on_ticker=on_ticker)
    enriched_payload = VcpEnrichedBucket(
        count=len(enriched), stocks=enriched,
    ).model_dump(mode="json")

    # Agent 3: Final rating with caps
    rated: list[VcpRatedStock] = []
    for structural, context in zip(stocks, enriched):
        if isinstance(structural, dict):
            from stock_analyze.models.vcp import VcpStructuralRating
            structural_model = VcpStructuralRating(**structural)
        else:
            structural_model = structural
        rated_stock = build_rated_stock(structural_model, context)
        rated.append(rated_stock)

    # Sort best→worst
    rated.sort(key=lambda r: (-r.final_rating, r.symbol))

    rated_payload = VcpRatedBucket(
        count=len(rated), stocks=rated,
    ).model_dump(mode="json")

    return {
        "agent2": enriched_payload,
        "agent3": rated_payload,
        "rated_stocks": rated,
    }


def format_vcp_rating_table(stocks: list[VcpRatedStock], *, min_rating: int = 4) -> str:
    visible = [s for s in stocks if s.final_rating >= min_rating]
    if not visible:
        return "(no names at this min-rating)"
    lines = ["stars  symbol   sector       cap?  rationale"]
    for s in visible:
        cap = "Y" if s.cap_applied else "N"
        lines.append(
            f"{s.final_rating}★     {s.symbol:<8} {s.sector:<12} {cap:<5} "
            f"{s.industry_group_strength_flag}"
        )
    return "\n".join(lines)


def _run_daily_vcp(
    *,
    config: RunConfig,
    name: str,
    run_dir: Path,
    force_keys: list[SymbolKey],
    meta: dict[str, Any],
    steps: list[str],
    reporter: RunProgress,
) -> RunResult:
    """Run the VCP pipeline: Agent 1 (scan) → Agent 2 (enrichment) → Agent 3 (final)."""
    try:
        agent1_raw = execute_vcp_scan(
            force_keys=force_keys or None,
            limit=config.limit,
            use_screener=config.use_screener,
            apply_gates=config.apply_gates,
            on_stage=lambda text: reporter.stage(f"Agent 1 — {text}"),
            batch_progress=reporter,
        )
        agent1 = strip_internal_keys(agent1_raw)
        agent1_path = run_dir / f"{name}_agent1.json"
        _write_json(agent1_path, agent1)
        steps.append("agent1")
        _write_meta(run_dir, {**meta, "steps_completed": list(steps)})
        counts = agent1_raw.get("_counts") or {}
        failed_force = agent1_raw.get("_failed_force") or []
        agent1_done_msg = (
            f"Agent 1 done "
            f"(5★={counts.get('5', '?')}, 4★={counts.get('4', '?')}, 3★={counts.get('3', '?')})"
        )
        if failed_force:
            agent1_done_msg += f" [red]⚠ {len(failed_force)} force-include failed[/red]"
        reporter.stage_done(agent1_done_msg)
        if failed_force:
            reporter.console.print(
                "\n[bold yellow]Force-include symbols could not be enriched after retries "
                "on all exchanges:[/bold yellow]"
            )
            for f in failed_force:
                reporter.console.print(
                    f"  • [red]{f['symbol']}[/red] (tried {f['exchange']} + fallbacks)"
                )

        ratings = agent1.get("ratings") or agent1.get("stocks") or []
        # Get passing stocks (4-5★) for enrichment
        passing = [
            r for r in ratings
            if r.get("structural_rating", 0) >= 4
        ]
        if not passing:
            meta.update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                steps_completed=list(steps),
            )
            _write_meta(run_dir, meta)
            reporter.stage_done(f"VCP Daily Run complete (no 4-5★ stocks): {run_dir}")
            return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

        if not config.run_catalyst:
            meta.update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                steps_completed=list(steps),
            )
            _write_meta(run_dir, meta)
            reporter.stage_done(f"VCP Daily Run complete: {run_dir}")
            return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

        reporter.stage(f"VCP Enrichment — researching ({len(passing)} symbols)")
        reporter.begin_ticker(len(passing), "VCP Context")

        enrichment_result = execute_vcp_enrichment(passing, on_ticker=reporter.ticker)
        reporter.end_ticker()

        agent2 = enrichment_result["agent2"]
        agent3 = enrichment_result["agent3"]
        rated = enrichment_result["rated_stocks"]

        agent2_path = run_dir / f"{name}_agent2.json"
        _write_json(agent2_path, agent2)
        steps.append("agent2")
        _write_meta(run_dir, {**meta, "steps_completed": list(steps)})
        reporter.stage_done(f"VCP Context done (count={agent2.get('count')})")

        agent3_path = run_dir / f"{name}_agent3.json"
        _write_json(agent3_path, agent3)
        steps.append("agent3")
        matches_5 = sum(1 for s in rated if s.final_rating >= 5)
        matches_4 = sum(1 for s in rated if s.final_rating >= 4)
        reporter.stage_done(
            f"VCP Final Rating done "
            f"(count={agent3.get('count')}, 5★={matches_5}, 4★={matches_4})"
        )

        vcp_table = format_vcp_rating_table(rated, min_rating=config.min_rating)
        reporter.console.print(vcp_table)

        meta.update(
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            steps_completed=list(steps),
            run_dir=str(run_dir),
        )
        _write_meta(run_dir, meta)
        reporter.stage_done(f"VCP Daily Run complete: {run_dir}")
        return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

    except Exception as exc:
        reporter.end_ticker()
        logger.error("VCP Daily Run failed: %s", exc)
        meta.update(
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            steps_completed=list(steps),
            error=str(exc),
            run_dir=str(run_dir),
        )
        _write_meta(run_dir, meta)
        reporter.fail(f"VCP Daily Run failed after {steps}; artifacts in {run_dir}")
        return RunResult(
            exit_code=1,
            run_dir=run_dir,
            steps_completed=list(steps),
            error=str(exc),
        )


def run_daily(
    config: RunConfig,
    reporter: Optional[RunProgress] = None,
) -> RunResult:
    reporter = reporter or RunProgress()
    try:
        name = sanitize_run_name(config.name)
        force_keys = list(config.force_keys or [])
        if not config.use_screener and not force_keys:
            raise ValueError("use_screener=False requires non-empty force_keys")
        stamped = RunConfig(
            name=name,
            select=config.select,
            run_catalyst=config.run_catalyst,
            analysis_method=config.analysis_method,
            limit=config.limit,
            force_keys=force_keys or None,
            use_screener=config.use_screener,
            apply_gates=config.apply_gates,
            output_root=config.output_root,
            min_rating=config.min_rating,
            pipeline_type=config.pipeline_type,
        )
        run_dir = create_run_dir(stamped)
    except Exception as exc:
        logger.error("Daily Run setup failed: %s", exc)
        reporter.fail(f"Daily Run setup failed: {exc}")
        return RunResult(exit_code=1, run_dir=Path(config.output_root), error=str(exc))

    steps: list[str] = []
    started = datetime.now(timezone.utc).isoformat()
    meta: dict[str, Any] = {
        "name": name,
        "pipeline_type": config.pipeline_type,
        "select": config.select,
        "run_catalyst": config.run_catalyst,
        "analysis_method": config.analysis_method,
        "use_screener": config.use_screener,
        "apply_gates": config.apply_gates,
        "force_include_count": len(force_keys),
        "started_at": started,
        "status": "started",
        "steps_completed": steps,
    }
    _write_meta(run_dir, meta)

    try:
        reporter.stage(f"Daily Run started — {name}")

        # ── VCP Pipeline Branch ──────────────────────────────────
        if config.pipeline_type == "daily_vcp_scan":
            return _run_daily_vcp(
                config=stamped,
                name=name,
                run_dir=run_dir,
                force_keys=force_keys,
                meta=meta,
                steps=steps,
                reporter=reporter,
            )

        # ── EP Pipeline (existing) ──────────────────────────────
        agent1_raw = execute_ep_scan(
            force_keys=force_keys or None,
            select=config.select,
            limit=config.limit,
            use_screener=config.use_screener,
            apply_gates=config.apply_gates,
            on_stage=lambda text: reporter.stage(f"Agent 1 — {text}"),
        )
        agent1 = strip_internal_keys(agent1_raw)
        agent1_path = run_dir / f"{name}_agent1.json"
        _write_json(agent1_path, agent1)
        steps.append("agent1")
        _write_meta(run_dir, {**meta, "steps_completed": list(steps)})
        counts = agent1_raw.get("_counts") or {}
        failed_force = agent1_raw.get("_failed_force") or []
        agent1_done_msg = (
            f"Agent 1 done "
            f"(baseline={counts.get('baseline', '?')}, strict={counts.get('strict', '?')})"
        )
        if failed_force:
            agent1_done_msg += f" [red]⚠ {len(failed_force)} force-include failed[/red]"
        reporter.stage_done(agent1_done_msg)
        if failed_force:
            reporter.console.print(
                "\n[bold yellow]Force-include symbols could not be enriched after retries "
                "on all exchanges:[/bold yellow]"
            )
            for f in failed_force:
                reporter.console.print(
                    f"  • [red]{f['symbol']}[/red] (tried {f['exchange']} + fallbacks)"
                )
            reporter.console.print(
                "\n[italic]To resolve: check the ticker/exchange, correct them, "
                "then re-run the pipeline with the corrected symbols "
                "using `python -m stock_analyze ep --force` or the interactive wizard.[/italic]\n"
            )

        if not config.run_catalyst:
            meta.update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                steps_completed=list(steps),
            )
            _write_meta(run_dir, meta)
            reporter.stage_done(f"Daily Run complete: {run_dir}")
            return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

        stocks = load_stocks_from_input(agent1, select=config.select)
        reporter.stage(f"Catalyst — searching news ({len(stocks)} symbols)")
        reporter.begin_ticker(len(stocks), "Catalyst")
        agent2 = execute_catalyst_enrich(stocks, on_ticker=reporter.ticker)
        reporter.end_ticker()
        agent2_path = run_dir / f"{name}_agent2.json"
        _write_json(agent2_path, agent2)
        steps.append("agent2")
        _write_meta(run_dir, {**meta, "steps_completed": list(steps)})
        found = sum(1 for s in agent2.get("stocks") or [] if s.get("catalyst_found"))
        reporter.stage_done(
            f"Catalyst done (count={agent2.get('count')}, catalyst_found={found})"
        )

        if config.analysis_method != "ep_rating":
            meta.update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                steps_completed=list(steps),
            )
            _write_meta(run_dir, meta)
            reporter.stage_done(f"Daily Run complete: {run_dir}")
            return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

        rated_stocks_in = load_stocks_from_input(agent2, select=config.select)
        reporter.stage(f"EP Rating — rating ({len(rated_stocks_in)} symbols)")
        reporter.begin_ticker(len(rated_stocks_in), "EP Rating")
        agent3, rated = execute_ep_rating(rated_stocks_in, on_ticker=reporter.ticker)
        reporter.end_ticker()
        agent3_path = run_dir / f"{name}_agent3.json"
        _write_json(agent3_path, agent3)
        steps.append("agent3")
        matches = sum(1 for s in rated if s.ep_catalyst_match)
        reporter.stage_done(
            f"EP Rating done (count={agent3.get('count')}, ep_catalyst_match={matches})"
        )
        rating_table = build_rating_table(rated, min_rating=config.min_rating)
        if rating_table is not None:
            reporter.console.print(rating_table)
        else:
            reporter.console.print("[yellow](no names at this min-rating)[/yellow]")

        meta.update(
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            steps_completed=list(steps),
            run_dir=str(run_dir),
        )
        _write_meta(run_dir, meta)
        reporter.stage_done(f"Daily Run complete: {run_dir}")
        return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

    except Exception as exc:
        reporter.end_ticker()
        logger.error("Daily Run failed: %s", exc)
        meta.update(
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            steps_completed=list(steps),
            error=str(exc),
            run_dir=str(run_dir),
        )
        _write_meta(run_dir, meta)
        reporter.fail(f"Daily Run failed after {steps}; artifacts in {run_dir}")
        return RunResult(
            exit_code=1,
            run_dir=run_dir,
            steps_completed=list(steps),
            error=str(exc),
        )
