"""CLI: python -m stock_analyze [ep|catalyst|rate|vcp|vcp-scan|vcp-enrich|bo|bo-scan|bo-enrich] ...  (no args → interactive wizard)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Literal, Optional

import questionary

from stock_analyze.agents.catalyst import load_stocks_from_input
from stock_analyze.agents.enrichment import load_vcp_stocks_from_input
from stock_analyze.data.symbols import SymbolKey
from stock_analyze.force_include import parse_force_include_text
from stock_analyze.pipeline import (
    execute_bo_enrichment,
    execute_bo_scan,
    execute_catalyst_enrich,
    execute_ep_rating,
    execute_ep_scan,
    execute_vcp_enrichment,
    execute_vcp_scan,
    format_bo_rating_table,
    format_rating_table,
    format_vcp_rating_table,
    strip_internal_keys,
)

logger = logging.getLogger(__name__)

_QUESTIONARY_STYLE = questionary.Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
    ]
)


def _prompt_force_keys() -> Optional[list[SymbolKey]]:
    """Prompt user to paste a symbol list; parse via force_include."""
    from dotenv import load_dotenv

    while True:
        raw = questionary.text(
            "Paste tickers (e.g. AAPL, MSFT, TSLA — messy lists OK)",
            style=_QUESTIONARY_STYLE,
        ).ask()
        if raw is None:
            return None
        if not raw.strip():
            questionary.print("Empty paste — please enter tickers.", style="bold fg:yellow")
            continue

        load_dotenv()
        result = parse_force_include_text(raw)

        if result.errors:
            questionary.print("Parse errors:", style="bold fg:red")
            for err in result.errors:
                questionary.print(f"  • {err}", style="fg:red")
            continue

        if not result.symbols:
            questionary.print("No symbols parsed. Try again.", style="bold fg:yellow")
            continue

        questionary.print(
            f"Parsed {len(result.symbols)} symbols.", style="bold fg:green",
        )
        confirm = questionary.select(
            "Use this list?",
            choices=[
                questionary.Choice("Yes", value="yes"),
                questionary.Choice("Re-paste", value="no"),
            ],
            default="yes",
            style=_QUESTIONARY_STYLE,
        ).ask()
        if confirm == "yes":
            return result.symbols


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock analyze scanners (Polygon.io)")
    sub = parser.add_subparsers(dest="command", required=False)

    ep = sub.add_parser("ep", help="Episodic Pivot Agent 1 technical filter")
    ep.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    ep.add_argument(
        "--select",
        choices=("baseline", "strict", "both"),
        default="both",
        help="Which bucket(s) to include in output JSON (both computed always)",
    )
    ep.add_argument("--limit", type=int, default=300, help="Max rows (historic compat)")
    ep.add_argument(
        "--force", type=str, default=None,
        help="Comma-separated symbols (e.g. AAPL,MSFT). Prompted if omitted.",
    )
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
    vcp.add_argument("--limit", type=int, default=300, help="Max screener rows (historic compat)")
    vcp.add_argument(
        "--force", type=str, default=None,
        help="Comma-separated symbols. Prompted if omitted.",
    )
    vcp.add_argument("--no-gates", action="store_true", help="Skip Stage 2 + VCP gate filtering")
    vcp.add_argument("-v", "--verbose", action="store_true")

    vcp_scan = sub.add_parser("vcp-scan", help="VCP Agent 1 structural scan only")
    vcp_scan.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    vcp_scan.add_argument("--limit", type=int, default=300, help="Max screener rows (historic compat)")
    vcp_scan.add_argument(
        "--force", type=str, default=None,
        help="Comma-separated symbols. Prompted if omitted.",
    )
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

    # BO pipeline subcommands
    bo = sub.add_parser("bo", help="Qullamaggie BO (Classic) — full pipeline (scan + funnel + enrich)")
    bo.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    bo.add_argument("--limit", type=int, default=300, help="Max screener rows (historic compat)")
    bo.add_argument(
        "--force", type=str, default=None,
        help="Comma-separated symbols. Prompted if omitted.",
    )
    bo.add_argument("--no-gates", action="store_true", help="Skip funnel gate filtering")
    bo.add_argument(
        "--profile",
        choices=["best", "moderate-lose", "widen"],
        default=None,
        help="Funnel profile (skip prompt). Default: best (headless) or prompt (TTY).",
    )
    bo.add_argument("-v", "--verbose", action="store_true")

    bo_scan = sub.add_parser("bo-scan", help="BO Agent 1 structural scan only (raw, no funnel)")
    bo_scan.add_argument("--out", type=str, default=None, help="Write JSON to this path")
    bo_scan.add_argument("--limit", type=int, default=300, help="Max screener rows (historic compat)")
    bo_scan.add_argument(
        "--force", type=str, default=None,
        help="Comma-separated symbols. Prompted if omitted.",
    )
    bo_scan.add_argument("--no-gates", action="store_true", help="Skip gate filtering")
    bo_scan.add_argument("-v", "--verbose", action="store_true")

    bo_enrich = sub.add_parser("bo-enrich", help="BO Agent 2-3 context enrichment")
    bo_enrich.add_argument("--in", dest="in_path", required=True, help="Agent 1 BO scan JSON")
    bo_enrich.add_argument("--out", type=str, default=None, help="Write final rated JSON to this path")
    bo_enrich.add_argument(
        "--min-rating",
        type=int,
        default=4,
        choices=(1, 2, 3, 4, 5),
        help="Minimum stars to print (default: 4)",
    )
    bo_enrich.add_argument("-v", "--verbose", action="store_true")

    return parser


def _parse_force_arg(force_arg: Optional[str]) -> Optional[list[SymbolKey]]:
    """Parse --force comma-separated string into SymbolKeys, or prompt."""
    if force_arg and force_arg.strip():
        from dotenv import load_dotenv
        load_dotenv()
        result = parse_force_include_text(force_arg)
        return result.symbols
    return _prompt_force_keys()


def _prompt_bo_profile(ratings: list) -> Optional[str]:
    """Prompt user to select a funnel profile (TTY mode)."""
    from stock_analyze.scanners.bo.watchlist import WATCHLIST_PROFILES, apply_funnel

    # Show best profile first
    funnel = apply_funnel(ratings, "best")
    survivors = funnel.survivors
    by_star = {}
    for c in survivors:
        s = c["stars"]
        by_star[s] = by_star.get(s, 0) + 1
    print(f"\nDefault profile (best): {len(survivors)} survivors")
    if survivors:
        for s in [5, 4, 3]:
            if s in by_star:
                print(f"  {s}★: {by_star[s]}")
    else:
        print("  No survivors — consider loosening the funnel.")

    profile = questionary.select(
        "Choose a funnel profile (or skip prompt with --profile):",
        choices=[
            questionary.Choice(
                f"Best (default) — ADV $50M / EMA 5% / Base 40d / Dry-up scoring-only",
                value="best",
            ),
            questionary.Choice(
                f"Moderate lose — ADV $50M / EMA 8% / Base 40d / Dry-up scoring-only (loosen EMA)",
                value="moderate-lose",
            ),
            questionary.Choice(
                f"Widen — ADV $30M / EMA 8% / Base 40d / Dry-up scoring-only (also lower liquidity floor)",
                value="widen",
            ),
        ],
        default="best",
        style=_QUESTIONARY_STYLE,
    ).ask()
    return profile  # type: ignore[return-value]


def run_ep_command(
    *,
    out_path: Optional[str],
    select: Literal["baseline", "strict", "both"],
    limit: int,
    force_arg: Optional[str] = None,
) -> int:
    force_keys = _parse_force_arg(force_arg)
    if force_keys is None:
        print("Cancelled.")
        return 2
    raw = execute_ep_scan(force_keys=force_keys, select=select, limit=limit)
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
    force_arg: Optional[str] = None,
) -> int:
    """Run full VCP pipeline: scan + enrichment."""
    force_keys = _parse_force_arg(force_arg)
    if force_keys is None:
        print("Cancelled.")
        return 2
    raw = execute_vcp_scan(force_keys=force_keys, limit=limit, apply_gates=apply_gates)
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
    force_arg: Optional[str] = None,
) -> int:
    """Run VCP Agent 1 structural scan only."""
    force_keys = _parse_force_arg(force_arg)
    if force_keys is None:
        print("Cancelled.")
        return 2
    raw = execute_vcp_scan(force_keys=force_keys, limit=limit, apply_gates=apply_gates)
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


def run_bo_command(
    *,
    out_path: Optional[str],
    limit: int,
    apply_gates: bool = True,
    force_arg: Optional[str] = None,
    profile: Optional[str] = None,
) -> int:
    """Run full BO pipeline: scan + funnel gate + enrichment."""
    force_keys = _parse_force_arg(force_arg)
    if force_keys is None:
        print("Cancelled.")
        return 2
    raw = execute_bo_scan(force_keys=force_keys, limit=limit, apply_gates=apply_gates)
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

    ratings = payload.get("ratings") or []

    if not apply_gates:
        # Run all pasted — no funnel, all ratings go to enrichment
        print(f"\nRunning enrichment on {len(ratings)} stocks (no funnel gate)...")
        result = execute_bo_enrichment(ratings)
        rated = result["rated_stocks"]
        print(format_bo_rating_table(rated, min_rating=3))
        return 0

    # Determine profile: --profile > prompt (TTY) > "best" (headless)
    from stock_analyze.scanners.bo.watchlist import apply_funnel, tradable_count

    if profile is not None:
        current_profile = profile
    elif force_arg is not None or not sys.stdin.isatty():
        # Headless / non-TTY — default to best
        current_profile = "best"
    else:
        # Interactive TTY — prompt for profile
        current_profile = _prompt_bo_profile(ratings)

    if current_profile is None:
        print("Cancelled.")
        return 2

    funnel = apply_funnel(ratings, current_profile)
    survivors = funnel.survivors
    print(f"\nFunnel gate ({current_profile}): {len(survivors)} survivors (3★+)")

    if survivors:
        # Show survivors table
        by_star = {}
        for c in survivors:
            s = c["stars"]
            by_star[s] = by_star.get(s, 0) + 1
        parts = [f"{s}★={by_star.get(s, 0)}" for s in [5, 4, 3]]
        print(f"  Stars breakdown: {', '.join(parts)}")
        sorted_surv = sorted(survivors, key=lambda c: c["q_base"], reverse=True)
        for i, c in enumerate(sorted_surv[:15]):
            print(
                f"  {i+1:>2}. {c['symbol']:<8} {c['stars']}★ Q={c['q_base']} "
                f"Imp={c['prior_impulse_pct']:.1f}% ADV=${c['adv_20d']:,.0f} "
                f"EMA={c['ema10_dist_pct']:.2f}% Base={c['base_duration']}d"
            )

    if not survivors:
        print("No funnel survivors.")
        return 0

    # Stamp funnel stars on ratings
    survivor_symbols = {s["symbol"] for s in survivors}
    for r in ratings:
        if r.get("symbol") in survivor_symbols:
            match = next(s for s in survivors if s["symbol"] == r["symbol"])
            r["funnel_stars"] = match["stars"]
            r["q_base"] = match["q_base"]

    passing = [r for r in ratings if r.get("symbol") in survivor_symbols]
    print(f"\nRunning enrichment on {len(passing)} funnel survivors...")
    result = execute_bo_enrichment(passing)
    rated = result["rated_stocks"]
    print(format_bo_rating_table(rated, min_rating=3))

    return 0


def run_bo_scan_command(
    *,
    out_path: Optional[str],
    limit: int,
    apply_gates: bool = True,
    force_arg: Optional[str] = None,
) -> int:
    """Run BO Agent 1 structural scan only."""
    force_keys = _parse_force_arg(force_arg)
    if force_keys is None:
        print("Cancelled.")
        return 2
    raw = execute_bo_scan(force_keys=force_keys, limit=limit, apply_gates=apply_gates)
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


def run_bo_enrich_command(
    *,
    in_path: str,
    out_path: Optional[str],
    min_rating: int,
) -> int:
    """Run BO Agent 2-3 context enrichment from Agent 1 JSON."""
    payload = json.loads(Path(in_path).read_text(encoding="utf-8"))
    stocks = load_vcp_stocks_from_input(payload)
    result = execute_bo_enrichment(stocks)
    rated = result["rated_stocks"]
    text = json.dumps(result["agent3"], indent=2)

    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        matches = sum(1 for s in rated if s.final_rating >= 4)
        print(f"Wrote {out_path} (count={len(rated)}, 4★+={matches})")

    print(format_bo_rating_table(rated, min_rating=min_rating))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    for _name in ("httpx", "httpcore", "openai", "urllib3", "tavily", "polygon"):
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
                force_arg=getattr(args, "force", None),
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
                force_arg=getattr(args, "force", None),
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
                force_arg=getattr(args, "force", None),
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

    if args.command == "bo":
        try:
            return run_bo_command(
                out_path=args.out,
                limit=args.limit,
                apply_gates=not getattr(args, "no_gates", False),
                force_arg=getattr(args, "force", None),
                profile=getattr(args, "profile", None),
            )
        except Exception as exc:
            logger.error("BO pipeline failed: %s", exc)
            return 1

    if args.command == "bo-scan":
        try:
            return run_bo_scan_command(
                out_path=args.out,
                limit=args.limit,
                apply_gates=not getattr(args, "no_gates", False),
                force_arg=getattr(args, "force", None),
            )
        except Exception as exc:
            logger.error("BO scan failed: %s", exc)
            return 1

    if args.command == "bo-enrich":
        try:
            return run_bo_enrich_command(
                in_path=args.in_path,
                out_path=args.out,
                min_rating=args.min_rating,
            )
        except Exception as exc:
            logger.error("BO enrich failed: %s", exc)
            return 1

    parser.error(f"Unknown command: {args.command}")
    return 2
