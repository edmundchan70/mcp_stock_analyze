"""CLI: python -m stock_analyze ep [--csv PATH] [--out PATH] [--select baseline|strict|both]"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from stock_analyze.data.screener import fetch_symbols, fetch_us_ep_universe
from stock_analyze.data.tradingview import enrich_from_ohlcv
from stock_analyze.scanners.ep.gates import BASELINE
from stock_analyze.scanners.ep.runner import load_force_csv, merge_force_rows, run_ep_scan

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock analyze scanners")
    sub = parser.add_subparsers(dest="command", required=True)

    ep = sub.add_parser("ep", help="Episodic Pivot Agent 1 technical filter")
    ep.add_argument("--csv", type=str, default=None, help="Force-include CSV (symbol,exchange)")
    ep.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    ep.add_argument(
        "--select",
        choices=("baseline", "strict", "both"),
        default="both",
        help="Which bucket(s) to include in output JSON (both computed always)",
    )
    ep.add_argument("--limit", type=int, default=300, help="Max screener rows")
    ep.add_argument("-v", "--verbose", action="store_true")
    return parser


def run_ep_command(
    *,
    csv_path: Optional[str],
    out_path: Optional[str],
    select: Literal["baseline", "strict", "both"],
    limit: int,
) -> int:
    force_keys = load_force_csv(csv_path) if csv_path else []
    screener_rows = fetch_us_ep_universe(
        min_price=BASELINE.min_price,
        min_gap_pct=BASELINE.min_gap_pct,
        min_rvol10=BASELINE.min_rvol10,
        limit=limit,
    )

    force_rows: list = []
    if force_keys:
        force_rows = fetch_symbols(force_keys)
        found_keys = set()
        for r in force_rows:
            name = str(r.get("name") or "")
            if ":" in name:
                exch, sym = name.split(":", 1)
                found_keys.add((sym.upper(), exch.upper()))
        for sym, exch in force_keys:
            if (sym, exch) not in found_keys:
                try:
                    force_rows.append(enrich_from_ohlcv(sym, exch))
                except Exception as exc:
                    logger.warning("Force-include enrich failed for %s:%s: %s", exch, sym, exc)

    rows, force_set, source = merge_force_rows(screener_rows, force_keys, force_rows)
    result = run_ep_scan(
        rows=rows,
        as_of=date.today(),
        force_symbols=force_set,
        universe_source=source,
    )
    payload = result.model_dump_selected(select)
    text = json.dumps(payload, indent=2)

    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"Wrote {out_path} (baseline={result.baseline.count}, strict={result.strict.count})")
    else:
        print(text)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if args.command == "ep":
        try:
            return run_ep_command(
                csv_path=args.csv,
                out_path=args.out,
                select=args.select,
                limit=args.limit,
            )
        except Exception as exc:
            logger.error("EP scan failed: %s", exc)
            return 1
    parser.error(f"Unknown command: {args.command}")
    return 2
