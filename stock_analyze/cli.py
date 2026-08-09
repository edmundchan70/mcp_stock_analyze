"""CLI: python -m stock_analyze [ep|catalyst|rate|vcp|vcp-scan|vcp-enrich] ...  (no args → interactive wizard)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Literal, Optional

from stock_analyze.agents.catalyst import load_stocks_from_input
from stock_analyze.agents.enrichment import load_vcp_stocks_from_input
from stock_analyze.pipeline import (
    execute_catalyst_enrich,
    execute_ep_rating,
    execute_ep_scan,
    execute_vcp_enrichment,
    execute_vcp_scan,
    format_rating_table,
    format_vcp_rating_table,
    strip_internal_keys,
)

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock analyze scanners")
    sub = parser.add_subparsers(dest="command", required=False)

    ep = sub.add_parser("ep", help="Episodic Pivot Agent 1 technical filter")
    ep.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    ep.add_argument(
        "--select",
        choices=("baseline", "strict", "both"),
        default="both",
        help="Which bucket(s) to include in output JSON (both computed always)",
    )
    ep.add_argument("--limit", type=int, default=300, help="Max screener rows")
    ep.add_argument("-v", "--verbose", action="store_true")

    cat = sub.add_parser("catalyst", help="Agent 2 catalyst intelligence (Tavily + OpenRouter)")
    cat.add_argument("--in", dest="in_path", required=True, help="Agent 1 JSON or bare stock list")
    cat.add_argument("--out", type=str, default=None, help="Write enriched JSON to this path")
    cat.add_argument(
        "--select",
        choices=("baseline", "strict", "both"),
        default="strict",
        help="Which Agent 1 bucket to enrich (default: strict)",
    )
    cat.add_argument("-v", "--verbose", action="store_true")

    rate = sub.add_parser("rate", help="Agent 3 EP Rating (re-fetch news + rate 1-5)")
    rate.add_argument("--in", dest="in_path", required=True, help="Agent 2 catalyst JSON or stock list")
    rate.add_argument("--out", type=str, default=None, help="Write full rated JSON to this path")
    rate.add_argument(
        "--select",
        choices=("baseline", "strict", "both"),
        default="strict",
        help="Which bucket to read when input is Agent 1-shaped (default: strict)",
    )
    rate.add_argument(
        "--min-rating",
        type=int,
        default=4,
        choices=(1, 2, 3, 4, 5),
        help="Minimum stars to print on console (default: 4). --out always has all ratings.",
    )
    rate.add_argument("-v", "--verbose", action="store_true")

    # VCP pipeline subcommands
    vcp = sub.add_parser("vcp", help="VCP full pipeline (scan + enrich + rate)")
    vcp.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    vcp.add_argument("--limit", type=int, default=300, help="Max screener rows")
    vcp.add_argument("--no-gates", action="store_true", help="Skip Stage 2 + VCP gate filtering")
    vcp.add_argument("-v", "--verbose", action="store_true")

    vcp_scan = sub.add_parser("vcp-scan", help="VCP Agent 1 structural scan only")
    vcp_scan.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    vcp_scan.add_argument("--limit", type=int, default=300, help="Max screener rows")
    vcp_scan.add_argument("--no-gates", action="store_true", help="Skip gate filtering")
    vcp_scan.add_argument("-v", "--verbose", action="store_true")

    vcp_enrich = sub.add_parser("vcp-enrich", help="VCP Agent 2-3 context enrichment")
    vcp_enrich.add_argument("--in", dest="in_path", required=True, help="Agent 1 VCP scan JSON")
    vcp_enrich.add_argument("--out", type=str, default=None, help="Write final rated JSON to this path")
    vcp_enrich.add_argument(
        "--min-rating",
        type=int,
        default=4,
        choices=(1, 2, 3, 4, 5),
        help="Minimum stars to print (default: 4)",
    )
    vcp_enrich.add_argument("-v", "--verbose", action="store_true")

    return parser


def run_ep_command(
    *,
    out_path: Optional[str],
    select: Literal["baseline", "strict", "both"],
    limit: int,
) -> int:
    raw = execute_ep_scan(select=select, limit=limit)
    counts = raw.get("_counts") or {}
    payload = strip_internal_keys(raw)
    text = json.dumps(payload, indent=2)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(
            f"Wrote {out_path} "
            f"(baseline={counts.get('baseline', '?')}, strict={counts.get('strict', '?')})"
        )
    else:
        print(text)
    return 0


def run_catalyst_command(
    *,
    in_path: str,
    out_path: Optional[str],
    select: Literal["baseline", "strict", "both"],
) -> int:
    payload = json.loads(Path(in_path).read_text(encoding="utf-8"))
    stocks = load_stocks_from_input(payload, select=select)
    bucket = execute_catalyst_enrich(stocks)
    text = json.dumps(bucket, indent=2)

    found = sum(1 for s in bucket.get("stocks") or [] if s.get("catalyst_found"))
    unknown = len(bucket.get("stocks") or []) - found
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"Wrote {out_path} (count={bucket.get('count')}, catalyst_found={found}, unknown={unknown})")
    else:
        print(text)
    return 0


def run_rate_command(
    *,
    in_path: str,
    out_path: Optional[str],
    min_rating: int,
    select: Literal["baseline", "strict", "both"] = "strict",
) -> int:
    payload = json.loads(Path(in_path).read_text(encoding="utf-8"))
    stocks = load_stocks_from_input(payload, select=select)
    bucket, rated = execute_ep_rating(stocks)
    text = json.dumps(bucket, indent=2)

    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        matches = sum(1 for s in rated if s.ep_catalyst_match)
        print(f"Wrote {out_path} (count={bucket.get('count')}, ep_catalyst_match={matches})")

    print(format_rating_table(rated, min_rating=min_rating))
    return 0


def run_vcp_command(
    *,
    out_path: Optional[str],
    limit: int,
    apply_gates: bool = True,
) -> int:
    """Run full VCP pipeline: scan + enrichment."""
    raw = execute_vcp_scan(limit=limit, apply_gates=apply_gates)
    counts = raw.get("_counts") or {}
    payload = strip_internal_keys(raw)
    text = json.dumps(payload, indent=2)

    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(
            f"Wrote {out_path} "
            f"(5★={counts.get('5', '?')}, 4★={counts.get('4', '?')}, 3★={counts.get('3', '?')})"
        )
    else:
        print(text)

    # Also run enrichment on passing stocks
    ratings = payload.get("ratings") or []
    passing = [r for r in ratings if r.get("structural_rating", 0) >= 4]
    if passing:
        print(f"\nRunning enrichment on {len(passing)} passing stocks...")
        result = execute_vcp_enrichment(passing)
        rated = result["rated_stocks"]
        print(format_vcp_rating_table(rated, min_rating=3))

    return 0


def run_vcp_scan_command(
    *,
    out_path: Optional[str],
    limit: int,
    apply_gates: bool = True,
) -> int:
    """Run VCP Agent 1 structural scan only."""
    raw = execute_vcp_scan(limit=limit, apply_gates=apply_gates)
    counts = raw.get("_counts") or {}
    payload = strip_internal_keys(raw)
    text = json.dumps(payload, indent=2)

    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(
            f"Wrote {out_path} "
            f"(5★={counts.get('5', '?')}, 4★={counts.get('4', '?')}, 3★={counts.get('3', '?')})"
        )
    else:
        print(text)
    return 0


def run_vcp_enrich_command(
    *,
    in_path: str,
    out_path: Optional[str],
    min_rating: int,
) -> int:
    """Run VCP Agent 2-3 context enrichment from Agent 1 JSON."""
    payload = json.loads(Path(in_path).read_text(encoding="utf-8"))
    stocks = load_vcp_stocks_from_input(payload)
    result = execute_vcp_enrichment(stocks)
    rated = result["rated_stocks"]
    text = json.dumps(result["agent3"], indent=2)

    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        matches = sum(1 for s in rated if s.final_rating >= 4)
        print(f"Wrote {out_path} (count={len(rated)}, 4★+={matches})")

    print(format_vcp_rating_table(rated, min_rating=min_rating))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    for _name in ("httpx", "httpcore", "openai", "urllib3", "tavily"):
        if not getattr(args, "verbose", False):
            logging.getLogger(_name).setLevel(logging.WARNING)

    if not args.command:
        from stock_analyze.interactive import run_interactive

        return run_interactive()

    if args.command == "ep":
        try:
            return run_ep_command(
                out_path=args.out,
                select=args.select,
                limit=args.limit,
            )
        except Exception as exc:
            logger.error("EP scan failed: %s", exc)
            return 1
    if args.command == "catalyst":
        try:
            return run_catalyst_command(
                in_path=args.in_path,
                out_path=args.out,
                select=args.select,
            )
        except Exception as exc:
            logger.error("Catalyst enrich failed: %s", exc)
            return 1
    if args.command == "rate":
        try:
            return run_rate_command(
                in_path=args.in_path,
                out_path=args.out,
                min_rating=args.min_rating,
                select=args.select,
            )
        except Exception as exc:
            logger.error("EP rating failed: %s", exc)
            return 1

    if args.command == "vcp":
        try:
            return run_vcp_command(
                out_path=args.out,
                limit=args.limit,
                apply_gates=not getattr(args, "no_gates", False),
            )
        except Exception as exc:
            logger.error("VCP pipeline failed: %s", exc)
            return 1

    if args.command == "vcp-scan":
        try:
            return run_vcp_scan_command(
                out_path=args.out,
                limit=args.limit,
                apply_gates=not getattr(args, "no_gates", False),
            )
        except Exception as exc:
            logger.error("VCP scan failed: %s", exc)
            return 1

    if args.command == "vcp-enrich":
        try:
            return run_vcp_enrich_command(
                in_path=args.in_path,
                out_path=args.out,
                min_rating=args.min_rating,
            )
        except Exception as exc:
            logger.error("VCP enrich failed: %s", exc)
            return 1

    parser.error(f"Unknown command: {args.command}")
    return 2
