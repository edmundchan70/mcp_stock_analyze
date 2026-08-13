"""Interactive Daily Run wizard (arrow-key menus via questionary) — Paste-only Polygon.io."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import questionary
from questionary import Choice, Style
from dotenv import load_dotenv

from stock_analyze.data.symbols import SymbolKey
from stock_analyze.force_include import parse_force_include_text
from stock_analyze.pipeline import (
    AnalysisMethod,
    GateSelect,
    RunConfig,
    execute_bo_enrichment,
    execute_bo_scan,
    format_bo_rating_table,
    run_daily,
)
from stock_analyze.scanners.bo.watchlist import WATCHLIST_PROFILES, apply_funnel, tradable_count

logger = logging.getLogger(__name__)


def _print_funnel_table(funnel_result, profile: str) -> None:
    """Print the funnel gate table to the console."""
    g = funnel_result.gate
    total = sum(v for k in g for v in g[k].values()) // 5
    questionary.print(f"\n{'─' * 70}", style="")
    questionary.print(f"  Funnel gate: {profile}  ({total} symbols rated)", style="bold")
    questionary.print(f"{'─' * 70}", style="")
    questionary.print(f"{'Gate':<32} {'Pass':>8} {'Fail':>8}", style="bold")
    gates = [
        ("G1: Prior Impulse ≥ 30%", "g1_impulse"),
        ("G2: 20d ADV$ ≥ floor", "g2_adv"),
        ("G3: |Close-EMA10| ≤ limit + rising", "g3_ema10"),
        ("G4: Valid Base 5-Nd", "g4_base"),
        ("G5: Vol Dry-up [scoring only]", "g5_dryup"),
    ]
    for glabel, gkey in gates:
        p = g["passed"][gkey]
        f = g["failed"][gkey]
        questionary.print(f"  {glabel:<30} {p:>8} {f:>8}")
    surv = funnel_result.survivors
    questionary.print(f"\n  Survivors (3★+): {len(surv)}")
    if surv:
        by_star = {}
        for c in surv:
            s = c["stars"]
            by_star[s] = by_star.get(s, 0) + 1
        parts = [f"{s}★={by_star.get(s, 0)}" for s in [5, 4, 3]]
        questionary.print(f"  Stars: {', '.join(parts)}")
        sorted_surv = sorted(surv, key=lambda c: c["q_base"], reverse=True)
        questionary.print(
            f"  {'#':>3} {'Symbol':<8} {'★':>3} {'Q':>5} {'Imp%':>7} "
            f"{'ADV$':>12} {'EMA%':>7} {'Base':>5} {'Dryup':>8} {'VCI':>7} {'HL':>3}"
        )
        for i, c in enumerate(sorted_surv[:15]):
            questionary.print(
                f"  {i+1:>3} {c['symbol']:<8} {c['stars']:>3} {c['q_base']:>5} "
                f"{c['prior_impulse_pct']:>6.1f}% {c['adv_20d']:>11,.0f} "
                f"{c['ema10_dist_pct']:>6.2f}% {c['base_duration']:>4}d "
                f"{c['dryup_vol_ratio']:>8.3f} {c['vci']:>7.4f} {c['higher_lows']:>3}"
            )


def _prompt_gap_options(current_survivors: int) -> Optional[str]:
    """Show the grouped gap-options prompt when tradable survivors < 5."""
    profiles = WATCHLIST_PROFILES
    best_ema = profiles["best"]["ema"]
    best_base = profiles["best"]["base"]
    best_adv = profiles["best"]["adv"]

    mod_ema = profiles["moderate-lose"]["ema"]
    mod_base = profiles["moderate-lose"]["base"]
    mod_adv = profiles["moderate-lose"]["adv"]

    widen_ema = profiles["widen"]["ema"]
    widen_base = profiles["widen"]["base"]
    shorten_adv = profiles["widen"]["adv"]

    questionary.print(
        f"\n[bold yellow]Only {current_survivors} tradable stocks (Q_base ≥ 60). "
        "Consider loosening the funnel.[/bold yellow]"
    )

    choice_labels = [
        Choice(
            f"Best (default) — ADV ${best_adv/1e6:.0f}M / EMA {best_ema}% / Base {best_base}d / Dry-up scoring-only",
            value="best",
        ),
        Choice(
            f"Moderate lose — ADV ${mod_adv/1e6:.0f}M / EMA {mod_ema}% / Base {mod_base}d / Dry-up scoring-only (loosen EMA)",
            value="moderate-lose",
        ),
        Choice(
            f"Widen — ADV ${shorten_adv/1e6:.0f}M / EMA {widen_ema}% / Base {widen_base}d / Dry-up scoring-only (also lower liquidity floor)",
            value="widen",
        ),
        Choice("Keep what I have — proceed with current survivors", value="keep"),
    ]

    return _select(
        "Choose a funnel profile (free loop — pick any, any number of times):",
        choice_labels,
        default="keep",
    )


def _run_bo_interactive(
    force_keys: Optional[list[SymbolKey]],
    *,
    apply_gates: bool = True,
    auto: bool = False,
) -> int:
    """Run the BO pipeline with interactive funnel gate and gap-options prompt.

    If ``apply_gates`` is False (Manual "Run all pasted"), the funnel is
    skipped and all ratings go straight to enrichment.
    """
    if not apply_gates:
        name = _prompt_run_name()
        if name is None:
            return 2
        cfg = RunConfig(
            name=name,
            select="strict",
            run_catalyst=True,
            analysis_method=None,
            force_keys=force_keys or None,
            use_screener=False,
            apply_gates=False,
            pipeline_type="daily_bo_scan",
            output_root=Path("output"),
        )
        result = run_daily(cfg)
        return result.exit_code

    name = _prompt_run_name()
    if name is None:
        return 2

    # Step 1: Run Agent 1 (structural scan)
    questionary.print("\nRunning BO structural scan (Agent 1)...", style="bold")
    agent1_raw = execute_bo_scan(
        force_keys=force_keys or None,
        limit=300,
        use_screener=False,
        apply_gates=apply_gates,
    )
    ratings = agent1_raw.get("ratings") or []
    questionary.print(
        f"Agent 1 done: {len(ratings)} stocks rated "
        f"(5★={agent1_raw.get('counts', {}).get('5', 0)}, "
        f"4★={agent1_raw.get('counts', {}).get('4', 0)}, "
        f"3★={agent1_raw.get('counts', {}).get('3', 0)})",
        style="bold fg:green",
    )

    # Step 2: Funnel gate with free profile loop
    current_profile = "best"
    while True:
        funnel = apply_funnel(ratings, current_profile)
        _print_funnel_table(funnel, current_profile)
        t_count = tradable_count(funnel.survivors)

        if t_count >= 5:
            questionary.print(
                f"\n{len(funnel.survivors)} tradable survivors — proceeding.",
                style="bold fg:green",
            )
            # Stamp funnel stars on ratings
            survivor_symbols = {s["symbol"] for s in funnel.survivors}
            for r in ratings:
                if r.get("symbol") in survivor_symbols:
                    match = next(s for s in funnel.survivors if s["symbol"] == r["symbol"])
                    r["funnel_stars"] = match["stars"]
                    r["q_base"] = match["q_base"]
            break

        choice = _prompt_gap_options(len(funnel.survivors))
        if choice is None or choice == "keep":
            # Stamp funnel stars on ratings
            survivor_symbols = {s["symbol"] for s in funnel.survivors}
            for r in ratings:
                if r.get("symbol") in survivor_symbols:
                    match = next(s for s in funnel.survivors if s["symbol"] == r["symbol"])
                    r["funnel_stars"] = match["stars"]
                    r["q_base"] = match["q_base"]
            break

        current_profile = choice

    # Step 3: Proceed with survivors to enrichment
    survivor_symbols = {s["symbol"] for s in funnel.survivors}
    passing = [r for r in ratings if r.get("symbol") in survivor_symbols]
    if not passing:
        questionary.print("No survivors after funnel gate.", style="bold fg:red")
        return 0

    questionary.print(
        f"\nRunning BO context enrichment on {len(passing)} survivors...",
        style="bold",
    )
    enrichment_result = execute_bo_enrichment(passing)
    rated = enrichment_result["rated_stocks"]

    questionary.print(
        f"BO Final Rating done "
        f"(count={len(rated)}, "
        f"5★={sum(1 for s in rated if s.final_rating >= 5)}, "
        f"4★={sum(1 for s in rated if s.final_rating >= 4)})",
        style="bold fg:green",
    )
    questionary.print(format_bo_rating_table(rated, min_rating=3))

    return 0


_STYLE = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
    ]
)


def _select(message: str, choices: list[Choice], *, default: Optional[str] = None) -> Optional[str]:
    return questionary.select(
        message,
        choices=choices,
        default=default,
        style=_STYLE,
        instruction="(Use arrow keys, Enter to confirm)",
    ).ask()


def _text(message: str, *, default: str = "") -> Optional[str]:
    return questionary.text(message, default=default, style=_STYLE).ask()


def _prompt_gate() -> Optional[GateSelect]:
    value = _select(
        "Gate select (Phase 1)",
        [
            Choice("Strict (recommended)", value="strict"),
            Choice("Baseline", value="baseline"),
            Choice("Both", value="both"),
        ],
        default="strict",
    )
    return value  # type: ignore[return-value]


def _format_keys(keys: list[SymbolKey]) -> str:
    return ", ".join(f"{exch}:{sym}" for sym, exch in keys)


def _prompt_force_include() -> tuple[Optional[list[SymbolKey]], bool]:
    """Return (force_keys, cancelled). Paste is mandatory post-migration."""
    while True:
        raw = _text(
            "Paste tickers (e.g. AAPL, MSFT, TSLA — messy lists OK)",
            default="",
        )
        if raw is None:
            return None, True
        if not raw.strip():
            questionary.print("Empty paste — please enter tickers.", style="bold fg:yellow")
            continue

        load_dotenv()
        result = parse_force_include_text(raw)

        if result.errors:
            questionary.print("Force Include parse errors:", style="bold fg:red")
            for err in result.errors:
                questionary.print(f"  • {err}", style="fg:red")
            questionary.print(
                "Fix the key / paste and try again.",
                style="bold fg:yellow",
            )
            continue

        if result.symbols:
            questionary.print(
                f"Accepted ({len(result.symbols)}): {_format_keys(result.symbols)}",
                style="bold fg:green",
            )
        else:
            questionary.print("No symbols parsed — please try again.", style="bold fg:yellow")
            continue

        if result.rejected:
            questionary.print(
                f"Rejected / not parsed ({len(result.rejected)}): "
                + ", ".join(result.rejected),
                style="bold fg:yellow",
            )

        confirm = _select(
            "Use this symbol list?",
            [
                Choice("Yes — continue", value="yes"),
                Choice("No — re-paste", value="no"),
            ],
            default="yes",
        )
        if confirm is None:
            return None, True
        if confirm == "yes":
            return result.symbols, False


def _prompt_apply_gate_or_run_all(*, structural: bool = False) -> Optional[bool]:
    """Manual paste path: Apply Gate filter vs Run all pasted.

    Returns True = Apply Gate filter, False = Run all pasted, None = cancelled.

    When ``structural=True`` (BO/VCP pipelines), the apply label says
    "structural gate (rating >= 4)"; EP keeps "Baseline/Strict".
    """
    if structural:
        apply_label = (
            "Apply Gate filter — Fetch metrics, apply funnel gate (ADV / EMA10 / base / dry-up), "
            "only survivors continue"
        )
    else:
        apply_label = (
            "Apply Gate filter — Fetch metrics, apply Baseline/Strict, "
            "only survivors continue"
        )
    value = _select(
        "Apply Gate filter or Run all pasted?",
        [
            Choice(apply_label, value="apply"),
            Choice(
                "Run all pasted — Fetch metrics for all pasted names, skip gates, continue all to Catalyst",
                value="run_all",
            ),
        ],
        default="apply",
    )
    if value is None:
        return None
    return value == "apply"


def _prompt_catalyst_and_method() -> tuple[Optional[bool], Optional[AnalysisMethod], bool]:
    """Return (run_catalyst, analysis_method, cancelled)."""
    catalyst = _select(
        "Run Catalyst search (Agent 2)?",
        [
            Choice("Yes — search news / compress catalyst", value="yes"),
            Choice("No — Agent 1 only (EP Rating will not run)", value="no"),
        ],
        default="yes",
    )
    if catalyst is None:
        return None, None, True

    run_catalyst = catalyst == "yes"
    analysis_method: Optional[AnalysisMethod] = None

    if run_catalyst:
        method = _select(
            "Analysis Method",
            [Choice("EP Rating", value="ep_rating")],
            default="ep_rating",
        )
        if method is None:
            return None, None, True
        analysis_method = method  # type: ignore[assignment]
    else:
        questionary.print(
            "Catalyst skipped → EP Rating will not run. Writing Agent 1 Run Artifact only.",
            style="bold fg:yellow",
        )

    return run_catalyst, analysis_method, False


def _prompt_run_name() -> Optional[str]:
    return _text("Run name (used in output folder / file names)", default="daily")


def _run_auto() -> int:
    pipeline = _select(
        "Pipeline Type",
        [
            Choice("Daily EP scan", value="daily_ep_scan"),
            Choice("Daily VCP scan", value="daily_vcp_scan"),
            Choice("Qullamaggie BO (Classic)", value="daily_bo_scan"),
        ],
        default="daily_ep_scan",
    )
    if pipeline is None:
        return 2

    force_keys, cancelled = _prompt_force_include()
    if cancelled:
        return 2

    is_vcp = pipeline == "daily_vcp_scan"
    is_bo = pipeline == "daily_bo_scan"
    skips_ep_gate = is_vcp or is_bo

    if is_bo:
        return _run_bo_interactive(force_keys, apply_gates=True, auto=True)

    if not skips_ep_gate:
        select = _prompt_gate()
        if select is None:
            return 2

    name = _prompt_run_name()
    if name is None:
        return 2

    cfg = RunConfig(
        name=name,
        select="strict" if skips_ep_gate else select,  # type: ignore[arg-type]
        run_catalyst=True,
        analysis_method="ep_rating" if not skips_ep_gate else None,
        force_keys=force_keys or None,
        use_screener=False,
        apply_gates=True,
        pipeline_type=pipeline,
        output_root=Path("output"),
    )
    result = run_daily(cfg)
    return result.exit_code


def _run_manual() -> int:
    pipeline = _select(
        "Pipeline Type",
        [
            Choice("Daily EP scan", value="daily_ep_scan"),
            Choice("Daily VCP scan", value="daily_vcp_scan"),
            Choice("Qullamaggie BO (Classic)", value="daily_bo_scan"),
        ],
        default="daily_ep_scan",
    )
    if pipeline is None:
        return 2

    is_vcp = pipeline == "daily_vcp_scan"
    is_bo = pipeline == "daily_bo_scan"
    skips_ep_gate = is_vcp or is_bo

    force_keys, cancelled = _prompt_force_include()
    if cancelled:
        return 2

    apply_gates = True
    select: Optional[GateSelect]

    apply_gates_choice = _prompt_apply_gate_or_run_all(structural=skips_ep_gate)
    if apply_gates_choice is None:
        return 2
    apply_gates = apply_gates_choice
    if apply_gates and not skips_ep_gate:
        select = _prompt_gate()
        if select is None:
            return 2
    else:
        select = "both"

    run_catalyst: Optional[bool]
    analysis_method: Optional[AnalysisMethod]
    cancelled_run: bool

    if is_bo and apply_gates:
        return _run_bo_interactive(force_keys, apply_gates=True, auto=False)

    if skips_ep_gate:
        label = "VCP" if is_vcp else "BO"
        enrichment = _select(
            f"Run {label} context enrichment (Agent 2-3)?",
            [
                Choice("Yes — Tavily dual-query + final rating", value="yes"),
                Choice("No — Agent 1 only (structural scan)", value="no"),
            ],
            default="yes",
        )
        if enrichment is None:
            return 2
        run_catalyst = enrichment == "yes"
        analysis_method = None
    else:
        run_catalyst, analysis_method, cancelled_run = _prompt_catalyst_and_method()
        if cancelled_run:
            return 2

    name = _prompt_run_name()
    if name is None:
        return 2

    result = run_daily(
        RunConfig(
            name=name,
            select=select,  # type: ignore[arg-type]
            run_catalyst=run_catalyst,  # type: ignore[arg-type]
            analysis_method=analysis_method,
            force_keys=force_keys or None,
            use_screener=False,
            apply_gates=apply_gates,
            pipeline_type=pipeline,
            output_root=Path("output"),
        )
    )
    return result.exit_code


def run_interactive() -> int:
    mode = _select(
        "How do you want to run?",
        [
            Choice("Auto Run — Paste-only pipeline", value="auto"),
            Choice("Manual Run — choose each step", value="manual"),
        ],
        default="auto",
    )
    if mode is None:
        print("Cancelled.")
        return 2
    if mode == "auto":
        return _run_auto()
    return _run_manual()
