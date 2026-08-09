"""Run Progress — styled live timeline for the Daily Run (Rich).

Persistent stage lines (Agent 1 / Catalyst / EP Rating) stay on screen; the
per-symbol ticker redraws in place while a stage runs and disappears when it
finishes. Piped / non-TTY output degrades to stage lines only.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from stock_analyze.models.rating import EpRatedStock


def _ensure_utf8_stdout() -> None:
    """Windows Python defaults stdout to cp1252, which crashes on the Unicode
    glyphs used below. Reconfigure to UTF-8 when possible (no-op when detached,
    e.g. under pytest capture)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


_TICKER_COLUMNS = (
    TextColumn("[bold cyan]{task.description}", justify="left"),
    SpinnerColumn(),
    BarColumn(bar_width=None),
    MofNCompleteColumn(),
    "·",
    TimeElapsedColumn(),
    TimeRemainingColumn(),
)


class RunProgress:
    """Emit a run timeline: persistent stages plus a live per-symbol ticker."""

    def __init__(self, console: Optional[Console] = None) -> None:
        _ensure_utf8_stdout()
        self.console = console or Console()
        self.progress = Progress(*_TICKER_COLUMNS, console=self.console, transient=True)
        self._task_id: Optional[int] = None

    def stage(self, text: str) -> None:
        """Persistent 'currently doing X' line."""
        self._stop_ticker()
        self.console.print(f"[bold cyan]▸ {text}[/bold cyan]")

    def stage_done(self, text: str) -> None:
        """Persistent completion line."""
        self._stop_ticker()
        self.console.print(f"[bold green]✔ {text}[/bold green]")

    def fail(self, text: str) -> None:
        """Persistent failure line."""
        self._stop_ticker()
        self.console.print(f"[bold red]✘ {text}[/bold red]")

    def begin_ticker(self, total: int, description: str) -> None:
        """Start the live ticker for a per-symbol stage."""
        self._stop_ticker()
        self._task_id = self.progress.add_task(description, total=total)
        self.progress.start()

    def ticker(self, index: int, total: int, symbol: str, action: str) -> None:
        """Update the live ticker with the symbol currently being worked on."""
        if self._task_id is None:
            return
        self.progress.update(
            self._task_id,
            completed=index,
            description=f"{index}/{total} {symbol} — {action} · {total - index} left",
        )

    def end_ticker(self) -> None:
        """Stop and remove the live ticker (safe to call at any time)."""
        self._stop_ticker()

    def _stop_ticker(self) -> None:
        if self._task_id is not None:
            self.progress.stop()
            self.progress.remove_task(self._task_id)
            self._task_id = None


def build_rating_table(
    stocks: Sequence[EpRatedStock], *, min_rating: int = 4
) -> Optional[Table]:
    """Rich Table of the EP Rating shortlist; None when nothing qualifies."""
    visible = [s for s in stocks if s.ep_rating >= min_rating]
    if not visible:
        return None
    table = Table(title="EP Rating shortlist", header_style="bold cyan")
    table.add_column("Stars", justify="right", style="bold yellow")
    table.add_column("Symbol", style="bold")
    table.add_column("Type")
    table.add_column("Rationale")
    for s in visible:
        table.add_row("★" * s.ep_rating, s.symbol, s.catalyst_type or "", s.ep_rationale or "")
    return table


__all__ = [
    "RunProgress",
    "build_rating_table",
]
