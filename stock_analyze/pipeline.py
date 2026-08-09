"""Daily Run pipeline — stamped Agent 1→2→3 chain (scheduler-ready)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence

from dotenv import load_dotenv

from stock_analyze.agents.catalyst import enrich_with_catalysts, load_stocks_from_input
from stock_analyze.agents.rating import rate_ep_catalysts
from stock_analyze.data.screener import fetch_symbols, fetch_us_ep_universe
from stock_analyze.data.symbols import SymbolKey, row_symbol_key
from stock_analyze.data.tradingview import enrich_from_ohlcv
from stock_analyze.models.catalyst import CatalystBucket
from stock_analyze.models.rating import EpRatedStock, RatedBucket
from stock_analyze.progress import RunProgress, build_rating_table
from stock_analyze.scanners.ep.gates import BASELINE
from stock_analyze.scanners.ep.runner import merge_force_rows, run_ep_scan

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
        screener_rows = fetch_us_ep_universe(
            min_price=BASELINE.min_price,
            min_gap_pct=BASELINE.min_gap_pct,
            min_rvol10=BASELINE.min_rvol10,
            limit=limit,
        )
    else:
        screener_rows = []

    force_rows: list = []
    if force_key_list:
        if on_stage is not None:
            on_stage("fetching force symbols")
        force_rows = fetch_symbols(force_key_list)
        found_keys = {row_symbol_key(r) for r in force_rows}
        for sym, exch in force_key_list:
            if (sym, exch) not in found_keys:
                try:
                    force_rows.append(enrich_from_ohlcv(sym, exch))
                except Exception as exc:
                    logger.warning("Force-include enrich failed for %s:%s: %s", exch, sym, exc)

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
        reporter.stage_done(
            f"Agent 1 done "
            f"(baseline={counts.get('baseline', '?')}, strict={counts.get('strict', '?')})"
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
