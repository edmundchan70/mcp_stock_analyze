"""Interactive Daily Run wizard (arrow-key menus via questionary)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import questionary
from questionary import Choice, Style
from dotenv import load_dotenv

from stock_analyze.data.symbols import SymbolKey
from stock_analyze.force_include import parse_force_include_text
from stock_analyze.pipeline import AnalysisMethod, GateSelect, RunConfig, run_daily

logger = logging.getLogger(__name__)

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


def _ask_repaste_or_skip(message: str) -> Optional[str]:
    """Return 'repaste', 'skip', or None (cancelled)."""
    return _select(
        message,
        [
            Choice("Re-paste", value="repaste"),
            Choice("Skip Force Include", value="skip"),
        ],
        default="repaste",
    )


def _prompt_force_include() -> tuple[Optional[list[SymbolKey]], bool]:
    """Return (force_keys, cancelled). Skip → ([], False); cancel → (None, True)."""
    value = _select(
        "Force Include (optional)",
        [
            Choice("Skip", value="skip"),
            Choice("Paste symbols…", value="paste"),
        ],
        default="skip",
    )
    if value is None:
        return None, True
    if value == "skip":
        return [], False

    while True:
        raw = _text(
            "Paste tickers (e.g. ( JHX, KGC, LUNR, MB, ) — messy lists OK)",
            default="",
        )
        if raw is None:
            return None, True
        if not raw.strip():
            questionary.print("Empty paste — try again or choose Skip.", style="bold fg:yellow")
            again = _ask_repaste_or_skip("What next?")
            if again is None:
                return None, True
            if again == "skip":
                return [], False
            continue

        load_dotenv()
        result = parse_force_include_text(raw)

        if result.errors:
            questionary.print("Force Include parse errors:", style="bold fg:red")
            for err in result.errors:
                questionary.print(f"  • {err}", style="fg:red")
            questionary.print(
                "Fix the key / paste, or choose Skip.",
                style="bold fg:yellow",
            )
            again = _ask_repaste_or_skip("What next?")
            if again is None:
                return None, True
            if again == "skip":
                return [], False
            continue

        if result.symbols:
            questionary.print(
                f"Accepted ({len(result.symbols)}): {_format_keys(result.symbols)}",
                style="bold fg:green",
            )
        else:
            questionary.print("Accepted: (none)", style="bold fg:yellow")

        if result.rejected:
            questionary.print(
                f"Rejected / not parsed ({len(result.rejected)}): "
                + ", ".join(result.rejected),
                style="bold fg:yellow",
            )

        if not result.symbols:
            again = _ask_repaste_or_skip("Nothing usable parsed. What next?")
            if again is None:
                return None, True
            if again == "skip":
                return [], False
            continue

        confirm = _select(
            "Use this Force Include list?",
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
        # No → stay in paste loop (re-prompt text)


def _prompt_apply_gate_or_run_all() -> Optional[bool]:
    """Manual paste path: Apply Gate filter vs Run all pasted.

    Returns True = Apply Gate filter, False = Run all pasted, None = cancelled.
    """
    value = _select(
        "Apply Gate filter or Run all pasted?",
        [
            Choice(
                "Apply Gate filter — Fetch metrics, apply Baseline/Strict, only survivors continue",
                value="apply",
            ),
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
        ],
        default="daily_ep_scan",
    )
    if pipeline is None:
        return 2

    force_keys, cancelled = _prompt_force_include()
    if cancelled:
        return 2

    pasted = bool(force_keys)
    use_screener = not pasted
    apply_gates = True

    is_vcp = pipeline == "daily_vcp_scan"

    if not is_vcp:
        select = _prompt_gate()
        if select is None:
            return 2

    name = _prompt_run_name()
    if name is None:
        return 2

    cfg = RunConfig(
        name=name,
        select="strict" if is_vcp else select,  # type: ignore[arg-type]
        run_catalyst=True,
        analysis_method="ep_rating" if not is_vcp else None,
        force_keys=force_keys or None,
        use_screener=use_screener,
        apply_gates=apply_gates,
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
        ],
        default="daily_ep_scan",
    )
    if pipeline is None:
        return 2

    is_vcp = pipeline == "daily_vcp_scan"

    force_keys, cancelled = _prompt_force_include()
    if cancelled:
        return 2

    pasted = bool(force_keys)
    use_screener = not pasted
    apply_gates = True
    select: Optional[GateSelect]

    if pasted:
        apply_gates_choice = _prompt_apply_gate_or_run_all()
        if apply_gates_choice is None:
            return 2
        apply_gates = apply_gates_choice
        if apply_gates and not is_vcp:
            select = _prompt_gate()
            if select is None:
                return 2
        else:
            select = "both"
    else:
        if not is_vcp:
            select = _prompt_gate()
            if select is None:
                return 2
        else:
            select = "strict"

    run_catalyst: Optional[bool]
    analysis_method: Optional[AnalysisMethod]
    cancelled_run: bool

    if is_vcp:
        # VCP Manual: Apply Gate / Run all pasted already chosen above
        enrichment = _select(
            "Run VCP context enrichment (Agent 2-3)?",
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
            use_screener=use_screener,
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
            Choice("Auto Run — Daily EP scan pipeline", value="auto"),
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
