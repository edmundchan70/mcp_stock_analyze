"""Daily Run pipeline — stamped Agent 1→2→3 chain (scheduler-ready, Polygon.io)."""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from logging import FileHandler
from pathlib import Path
from typing import Any, Callable, Generator, Literal, Optional, Sequence

from dotenv import load_dotenv

from stock_analyze.agents.catalyst import enrich_with_catalysts, load_stocks_from_input
from stock_analyze.agents.enrichment import enrich_with_vcp_context, load_vcp_stocks_from_input
from stock_analyze.agents.rating import rate_ep_catalysts
from stock_analyze.data.polygon import resolve_force_symbol, to_ep_row
from stock_analyze.data.symbols import SymbolKey
from stock_analyze.models.catalyst import CatalystBucket
from stock_analyze.models.bo import BoEnrichedBucket, BoRatedBucket, BoRatedStock, BoScanBucket
from stock_analyze.models.rating import EpRatedStock, RatedBucket
from stock_analyze.models.vcp import VcpEnrichedBucket, VcpRatedBucket, VcpRatedStock, VcpScanBucket
from stock_analyze.progress import RunProgress, build_rating_table
from stock_analyze.scanners.bo.gates import build_bo_rated_stock
from stock_analyze.scanners.bo.runner import run_bo_scan
from stock_analyze.scanners.bo.watchlist import apply_funnel, q_base_to_stars, tradable_count
from stock_analyze.scanners.ep.gates import BASELINE
from stock_analyze.scanners.ep.runner import merge_force_rows, run_ep_scan
from stock_analyze.scanners.vcp.gates import build_rated_stock
from stock_analyze.scanners.vcp.runner import merge_vcp_force_rows as _merge_vcp_force_rows
from stock_analyze.scanners.vcp.runner import run_vcp_scan

logger = logging.getLogger(__name__)

FILE_LOG_LEVEL = logging.DEBUG


@contextmanager
def _run_log(run_dir: Path) -> Generator[None, None, None]:
    """Add a FileHandler writing to run_dir/run.log for the duration of the context."""
    handler: Optional[FileHandler] = None
    try:
        handler = FileHandler(run_dir / "run.log", encoding="utf-8")
        handler.setLevel(FILE_LOG_LEVEL)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root = logging.getLogger()
        root.setLevel(min(root.level or logging.DEBUG, FILE_LOG_LEVEL))
        root.addHandler(handler)
        yield
    finally:
        if handler is not None:
            root = logging.getLogger()
            root.removeHandler(handler)
            handler.close()

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
    use_screener: bool = False   # always False post-migration
    apply_gates: bool = True
    output_root: Path = field(default_factory=lambda: Path("output"))
    min_rating: int = 4
    pipeline_type: str = "daily_ep_scan"
    bo_profile: str = "best"


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


def _resolve_symbols(
    force_key_list: list[SymbolKey],
    *,
    on_stage: Optional[StageFn] = None,
    on_ticker: Optional[TickerFn] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Resolve paste-only symbols via Polygon Ticker Details.

    Returns (resolved_rows, failed_force).
    """
    if on_stage is not None:
        on_stage("resolving symbols (Polygon)")

    resolved: list[dict[str, Any]] = []
    failed_force: list[dict[str, str]] = []
    total = len(force_key_list)

    for i, (sym, exch) in enumerate(force_key_list, start=1):
        details = resolve_force_symbol(sym)
        if details is None:
            logger.warning("Polygon: symbol resolution failed for %s", sym)
            failed_force.append({
                "symbol": sym.upper(),
                "exchange": exch.upper(),
                "errors": ["Symbol not found in Polygon"],
            })
        else:
            resolved.append(details)
        if on_ticker is not None:
            on_ticker(i, total, sym.upper(), "resolving")

    return resolved, failed_force


def execute_ep_scan(
    *,
    force_keys: Optional[Sequence[SymbolKey]] = None,
    select: GateSelect,
    limit: int,
    use_screener: bool = False,
    apply_gates: bool = True,
    on_stage: Optional[StageFn] = None,
    batch_progress: Any = None,
) -> dict[str, Any]:
    """Run EP Agent 1 with paste-only Polygon symbols.

    Always attaches ``_counts`` (baseline/strict) for CLI logging.
    """
    force_key_list: list[SymbolKey] = list(force_keys or [])
    if not force_key_list:
        raise ValueError("EP scan requires non-empty force_keys (paste-only)")

    # Resolve symbols via Polygon
    if batch_progress is not None:
        batch_progress.begin_ticker(len(force_key_list), "Resolving symbols", throttle=1)
    resolved, failed_force = _resolve_symbols(
        force_key_list,
        on_stage=on_stage,
        on_ticker=batch_progress.ticker if batch_progress is not None else None,
    )
    if batch_progress is not None:
        batch_progress.end_ticker()

    if not resolved:
        payload: dict[str, Any] = {
            "baseline": {"count": 0, "stocks": []},
            "strict": {"count": 0, "stocks": []},
            "_counts": {"baseline": 0, "strict": 0},
        }
        if failed_force:
            payload["_failed_force"] = failed_force
        return payload

    # Build EP rows for each resolved symbol: combine ticker details + OHLCV-derived metrics
    if on_stage is not None:
        on_stage("computing EP metrics (Polygon OHLCV)")
    if batch_progress is not None:
        batch_progress.begin_ticker(len(resolved), "EP metrics", throttle=1)

    ep_rows: list[dict[str, Any]] = []
    for i, detail in enumerate(resolved, start=1):
        symbol = detail.get("symbol", "")
        if not symbol:
            continue
        try:
            ohlcv_row = to_ep_row(symbol)
            # Merge: ticker details win for name/exchange/market_cap; OHLCV for metrics
            row = {
                "name": detail.get("name", f"POLYGON:{symbol}"),
                "symbol": symbol,
                "exchange": detail.get("exchange", "NASDAQ"),
                "close": ohlcv_row.get("close"),
                "open": ohlcv_row.get("open"),
                "prior_close": ohlcv_row.get("prior_close"),
                "gap": ohlcv_row.get("gap"),
                "volume": ohlcv_row.get("volume"),
                "relative_volume_10d_calc": ohlcv_row.get("relative_volume_10d_calc"),
                "Value.Traded": ohlcv_row.get("Value.Traded"),
                "avg_dollar_volume_50d": ohlcv_row.get("avg_dollar_volume_50d"),
                "market_cap_basic": detail.get("market_cap"),
                "market_cap": detail.get("market_cap"),
                "description": detail.get("description", ""),
            }
            ep_rows.append(row)
        except Exception as exc:
            logger.warning("EP row build failed for %s: %s", symbol, exc)
            failed_force.append({
                "symbol": symbol.upper(),
                "exchange": detail.get("exchange", "NASDAQ"),
                "errors": [str(exc)],
            })
        if batch_progress is not None:
            batch_progress.ticker(i, len(resolved), symbol.upper(), "computing")

    if batch_progress is not None:
        batch_progress.end_ticker()

    if not ep_rows:
        payload = {
            "baseline": {"count": 0, "stocks": []},
            "strict": {"count": 0, "stocks": []},
            "_counts": {"baseline": 0, "strict": 0},
        }
        if failed_force:
            payload["_failed_force"] = failed_force
        return payload

    if on_stage is not None:
        on_stage("running EP scan")

    _, force_set, source = merge_force_rows([], force_key_list, ep_rows)
    result = run_ep_scan(
        rows=ep_rows,
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
    use_screener: bool = False,
    apply_gates: bool = True,
    on_stage: Optional[StageFn] = None,
    batch_progress: Any = None,
) -> dict[str, Any]:
    """Run VCP Agent 1 with paste-only Polygon symbols.

    Args:
        batch_progress: Optional RunProgress for live batch OHLCV ticker.
    """
    force_key_list: list[SymbolKey] = list(force_keys or [])
    if not force_key_list:
        raise ValueError("VCP scan requires non-empty force_keys (paste-only)")

    if batch_progress is not None:
        batch_progress.begin_ticker(len(force_key_list), "Resolving symbols", throttle=1)
    resolved, failed_force = _resolve_symbols(
        force_key_list,
        on_stage=on_stage,
        on_ticker=batch_progress.ticker if batch_progress is not None else None,
    )
    if batch_progress is not None:
        batch_progress.end_ticker()

    if not resolved:
        payload: dict[str, Any] = {
            "ratings": [],
            "five_star": [], "four_star": [], "three_star": [],
            "count": 0,
            "counts": {"5": 0, "4": 0, "3": 0},
            "universe_source": "force",
            "gates_applied": apply_gates,
        }
        if failed_force:
            payload["_failed_force"] = failed_force
        return payload

    if on_stage is not None:
        on_stage("running VCP scan")

    force_set = {(s.upper(), e.upper()) for s, e in force_key_list}

    bucket = run_vcp_scan(
        screener_rows=[],
        force_keys=force_set,
        force_rows=resolved,
        universe_source="force",
        apply_gates=apply_gates,
        batch_progress=batch_progress,
    )
    payload = bucket.model_dump(mode="json")
    payload["_counts"] = bucket.counts
    if failed_force:
        payload["_failed_force"] = failed_force
    return payload


def execute_bo_scan(
    *,
    force_keys: Optional[Sequence[SymbolKey]] = None,
    limit: int = 300,
    use_screener: bool = False,
    apply_gates: bool = True,
    on_stage: Optional[StageFn] = None,
    batch_progress: Any = None,
) -> dict[str, Any]:
    """Run Qullamaggie BO Agent 1 with paste-only Polygon symbols.

    Args:
        batch_progress: Optional RunProgress for live batch OHLCV ticker.
    """
    force_key_list: list[SymbolKey] = list(force_keys or [])
    if not force_key_list:
        raise ValueError("BO scan requires non-empty force_keys (paste-only)")

    if batch_progress is not None:
        batch_progress.begin_ticker(len(force_key_list), "Resolving symbols", throttle=1)
    resolved, failed_force = _resolve_symbols(
        force_key_list,
        on_stage=on_stage,
        on_ticker=batch_progress.ticker if batch_progress is not None else None,
    )
    if batch_progress is not None:
        batch_progress.end_ticker()

    if not resolved:
        payload: dict[str, Any] = {
            "ratings": [],
            "five_star": [], "four_star": [], "three_star": [],
            "count": 0,
            "counts": {"5": 0, "4": 0, "3": 0},
            "universe_source": "force",
            "gates_applied": apply_gates,
        }
        if failed_force:
            payload["_failed_force"] = failed_force
        return payload

    if on_stage is not None:
        on_stage("running BO scan")

    force_set = {(s.upper(), e.upper()) for s, e in force_key_list}

    bucket = run_bo_scan(
        screener_rows=[],
        force_keys=force_set,
        force_rows=resolved,
        universe_source="force",
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
    """Run VCP Agent 2 (context enrichment) and Agent 3 (final rating)."""
    load_dotenv()

    enriched = enrich_with_vcp_context(stocks, on_ticker=on_ticker)
    enriched_payload = VcpEnrichedBucket(
        count=len(enriched), stocks=enriched,
    ).model_dump(mode="json")

    rated: list[VcpRatedStock] = []
    for structural, context in zip(stocks, enriched):
        if isinstance(structural, dict):
            from stock_analyze.models.vcp import VcpStructuralRating
            structural_model = VcpStructuralRating(**structural)
        else:
            structural_model = structural
        rated_stock = build_rated_stock(structural_model, context)
        rated.append(rated_stock)

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


def execute_bo_enrichment(
    stocks: Sequence[Any],
    *,
    on_ticker: Optional[TickerFn] = None,
) -> dict[str, Any]:
    """Run BO Agent 2 (context enrichment) and Agent 3 (final rating)."""
    load_dotenv()

    enriched = enrich_with_vcp_context(stocks, on_ticker=on_ticker)
    enriched_payload = BoEnrichedBucket(
        count=len(enriched), stocks=enriched,
    ).model_dump(mode="json")

    rated: list[BoRatedStock] = []
    for setup, context in zip(stocks, enriched):
        if isinstance(setup, dict):
            from stock_analyze.models.bo import BoSetupRating
            setup_model = BoSetupRating(**setup)
        else:
            setup_model = setup
        rated_stock = build_bo_rated_stock(setup_model, context)
        rated.append(rated_stock)

    rated.sort(key=lambda r: (-r.final_rating, r.symbol))

    rated_payload = BoRatedBucket(
        count=len(rated), stocks=rated,
    ).model_dump(mode="json")

    return {
        "agent2": enriched_payload,
        "agent3": rated_payload,
        "rated_stocks": rated,
    }


def format_bo_rating_table(stocks: list[BoRatedStock], *, min_rating: int = 4) -> str:
    visible = [s for s in stocks if s.final_rating >= min_rating]
    if not visible:
        return "(no names at this min-rating)"
    lines = ["stars  symbol   variant      sector       cap?  rationale"]
    for s in visible:
        cap = "Y" if s.cap_applied else "N"
        lines.append(
            f"{s.final_rating}★     {s.symbol:<8} {s.variant:<12} {s.sector:<12} {cap:<5} "
            f"{s.industry_group_strength_flag}"
        )
    return "\n".join(lines)


def format_bo_near_miss_table(near_miss: list[dict[str, Any]]) -> str:
    """Plain-text near-miss watchlist table for the no-4-5★ short-circuit."""
    if not near_miss:
        return "(no near-miss stocks)"
    lines = ["symbol   variant      failed  rs    surge"]
    for n in near_miss:
        rs = n.get("rs_rating")
        rs_str = f"{rs:.0f}" if rs is not None else "—"
        lines.append(
            f"{n.get('symbol',''):<8} {n.get('variant',''):<12} "
            f"{','.join(n.get('failed_essentials',[])):<20} {rs_str:<4} "
            f"{n.get('surge_pct',0):.0f}%"
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
        t0 = time.perf_counter()
        agent1_raw = execute_vcp_scan(
            force_keys=force_keys or None,
            limit=config.limit,
            use_screener=False,
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
        agent1_done_msg += f" — {time.perf_counter() - t0:.0f}s"
        reporter.stage_done(agent1_done_msg)
        if failed_force:
            reporter.console.print(
                "\n[bold yellow]Force-include symbols could not be resolved via Polygon:[/bold yellow]"
            )
            for f in failed_force:
                reporter.console.print(
                    f"  • [red]{f['symbol']}[/red]"
                )

        ratings = agent1.get("ratings") or agent1.get("stocks") or []
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
        t1 = time.perf_counter()

        enrichment_result = execute_vcp_enrichment(passing, on_ticker=reporter.ticker)
        reporter.end_ticker()

        agent2 = enrichment_result["agent2"]
        agent3 = enrichment_result["agent3"]
        rated = enrichment_result["rated_stocks"]

        agent2_path = run_dir / f"{name}_agent2.json"
        _write_json(agent2_path, agent2)
        steps.append("agent2")
        _write_meta(run_dir, {**meta, "steps_completed": list(steps)})
        reporter.stage_done(
            f"VCP Context done (count={agent2.get('count')}) — {time.perf_counter() - t1:.0f}s"
        )
        t2 = time.perf_counter()

        agent3_path = run_dir / f"{name}_agent3.json"
        _write_json(agent3_path, agent3)
        steps.append("agent3")
        matches_5 = sum(1 for s in rated if s.final_rating >= 5)
        matches_4 = sum(1 for s in rated if s.final_rating >= 4)
        reporter.stage_done(
            f"VCP Final Rating done "
            f"(count={agent3.get('count')}, 5★={matches_5}, 4★={matches_4}) "
            f"— {time.perf_counter() - t2:.0f}s"
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


def _run_daily_bo(
    *,
    config: RunConfig,
    name: str,
    run_dir: Path,
    force_keys: list[SymbolKey],
    meta: dict[str, Any],
    steps: list[str],
    reporter: RunProgress,
) -> RunResult:
    """Run the BO pipeline: Agent 1 (scan) → Agent 2 (enrichment) → Agent 3 (final)."""
    try:
        t0 = time.perf_counter()
        agent1_raw = execute_bo_scan(
            force_keys=force_keys or None,
            limit=config.limit,
            use_screener=False,
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
        agent1_done_msg += f" — {time.perf_counter() - t0:.0f}s"
        reporter.stage_done(agent1_done_msg)
        if failed_force:
            reporter.console.print(
                "\n[bold yellow]Force-include symbols could not be resolved via Polygon:[/bold yellow]"
            )
            for f in failed_force:
                reporter.console.print(
                    f"  • [red]{f['symbol']}[/red]"
                )

        ratings = agent1.get("ratings") or agent1.get("stocks") or []
        profile = getattr(config, "bo_profile", "best")

        # Run the funnel gate on the Agent 1 ratings
        funnel = apply_funnel(ratings, profile)
        reporter.console.print(
            f"\n[bold]Funnel gate ({profile}):[/bold] "
            f"{funnel.gate['passed']['g1_impulse'] + funnel.gate['failed']['g1_impulse']}→"
            f"[green]{funnel.gate['passed']['g2_adv']}[/green]/"
            f"[green]{funnel.gate['passed']['g3_ema10']}[/green]/"
            f"[green]{funnel.gate['passed']['g4_base']}[/green] "
            f"G2/G3/G4 pass → [bold green]{len(funnel.survivors)} survivors[/bold green]"
        )

        passing = funnel.survivors
        if not passing:
            meta.update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                steps_completed=list(steps),
            )
            _write_meta(run_dir, meta)
            reporter.stage_done(f"BO Daily Run complete (no funnel survivors): {run_dir}")
            return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

        # Stamp funnel stars on the rating dicts for the enrichment / final report
        survivor_symbols = {s["symbol"] for s in passing}
        for r in ratings:
            if r.get("symbol") in survivor_symbols:
                match = next(s for s in passing if s["symbol"] == r["symbol"])
                r["funnel_stars"] = match["stars"]
                r["q_base"] = match["q_base"]

        if not config.run_catalyst:
            meta.update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                steps_completed=list(steps),
            )
            _write_meta(run_dir, meta)
            reporter.stage_done(f"BO Daily Run complete: {run_dir}")
            return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

        surviving_ratings = [r for r in ratings if r.get("symbol") in survivor_symbols]
        reporter.stage(f"BO Enrichment — researching ({len(surviving_ratings)} symbols)")
        reporter.begin_ticker(len(surviving_ratings), "BO Context")
        t1 = time.perf_counter()

        enrichment_result = execute_bo_enrichment(surviving_ratings, on_ticker=reporter.ticker)
        reporter.end_ticker()

        agent2 = enrichment_result["agent2"]
        agent3 = enrichment_result["agent3"]
        rated = enrichment_result["rated_stocks"]

        agent2_path = run_dir / f"{name}_agent2.json"
        _write_json(agent2_path, agent2)
        steps.append("agent2")
        _write_meta(run_dir, {**meta, "steps_completed": list(steps)})
        reporter.stage_done(
            f"BO Context done (count={agent2.get('count')}) — {time.perf_counter() - t1:.0f}s"
        )
        t2 = time.perf_counter()

        agent3_path = run_dir / f"{name}_agent3.json"
        _write_json(agent3_path, agent3)
        steps.append("agent3")
        matches_5 = sum(1 for s in rated if s.final_rating >= 5)
        matches_4 = sum(1 for s in rated if s.final_rating >= 4)
        reporter.stage_done(
            f"BO Final Rating done "
            f"(count={agent3.get('count')}, 5★={matches_5}, 4★={matches_4}) "
            f"— {time.perf_counter() - t2:.0f}s"
        )

        bo_table = format_bo_rating_table(rated, min_rating=config.min_rating)
        reporter.console.print(bo_table)

        meta.update(
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            steps_completed=list(steps),
            run_dir=str(run_dir),
        )
        _write_meta(run_dir, meta)
        reporter.stage_done(f"BO Daily Run complete: {run_dir}")
        return RunResult(exit_code=0, run_dir=run_dir, steps_completed=list(steps))

    except Exception as exc:
        reporter.end_ticker()
        logger.error("BO Daily Run failed: %s", exc)
        meta.update(
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            steps_completed=list(steps),
            error=str(exc),
            run_dir=str(run_dir),
        )
        _write_meta(run_dir, meta)
        reporter.fail(f"BO Daily Run failed after {steps}; artifacts in {run_dir}")
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
        if not force_keys:
            raise ValueError("Paste-only pipeline requires non-empty force_keys")
        stamped = RunConfig(
            name=name,
            select=config.select,
            run_catalyst=config.run_catalyst,
            analysis_method=config.analysis_method,
            limit=config.limit,
            force_keys=force_keys or None,
            use_screener=False,
            apply_gates=config.apply_gates,
            output_root=config.output_root,
            min_rating=config.min_rating,
            pipeline_type=config.pipeline_type,
            bo_profile=getattr(config, "bo_profile", "best"),
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
        "use_screener": False,
        "apply_gates": config.apply_gates,
        "force_include_count": len(force_keys),
        "started_at": started,
        "status": "started",
        "steps_completed": steps,
    }
    _write_meta(run_dir, meta)

    with _run_log(run_dir):
        logger.info("Daily Run started — %s (pipeline=%s, force=%d, gates=%s)",
            name, config.pipeline_type, len(force_keys), config.apply_gates)
        try:
            reporter.stage(f"Daily Run started — {name}")

            # ── BO Pipeline Branch ────────────────────────────────────
            if config.pipeline_type == "daily_bo_scan":
                return _run_daily_bo(
                    config=stamped,
                    name=name,
                    run_dir=run_dir,
                    force_keys=force_keys,
                    meta=meta,
                    steps=steps,
                    reporter=reporter,
                )

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

            # ── EP Pipeline ─────────────────────────────────────────
            t0 = time.perf_counter()
            agent1_raw = execute_ep_scan(
                force_keys=force_keys or None,
                select=config.select,
                limit=config.limit,
                use_screener=False,
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
                f"(baseline={counts.get('baseline', '?')}, strict={counts.get('strict', '?')})"
            )
            if failed_force:
                agent1_done_msg += f" [red]⚠ {len(failed_force)} force-include failed[/red]"
            agent1_done_msg += f" — {time.perf_counter() - t0:.0f}s"
            reporter.stage_done(agent1_done_msg)
            if failed_force:
                reporter.console.print(
                    "\n[bold yellow]Force-include symbols could not be resolved via Polygon:[/bold yellow]"
                )
                for f in failed_force:
                    reporter.console.print(
                        f"  • [red]{f['symbol']}[/red]"
                    )
                reporter.console.print(
                    "\n[italic]To resolve: check the ticker, correct it, "
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
            t1 = time.perf_counter()
            agent2 = execute_catalyst_enrich(stocks, on_ticker=reporter.ticker)
            reporter.end_ticker()
            agent2_path = run_dir / f"{name}_agent2.json"
            _write_json(agent2_path, agent2)
            steps.append("agent2")
            _write_meta(run_dir, {**meta, "steps_completed": list(steps)})
            found = sum(1 for s in agent2.get("stocks") or [] if s.get("catalyst_found"))
            reporter.stage_done(
                f"Catalyst done (count={agent2.get('count')}, catalyst_found={found}) "
                f"— {time.perf_counter() - t1:.0f}s"
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
            t2 = time.perf_counter()
            agent3, rated = execute_ep_rating(rated_stocks_in, on_ticker=reporter.ticker)
            reporter.end_ticker()
            agent3_path = run_dir / f"{name}_agent3.json"
            _write_json(agent3_path, agent3)
            steps.append("agent3")
            matches = sum(1 for s in rated if s.ep_catalyst_match)
            reporter.stage_done(
                f"EP Rating done (count={agent3.get('count')}, ep_catalyst_match={matches}) "
                f"— {time.perf_counter() - t2:.0f}s"
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
