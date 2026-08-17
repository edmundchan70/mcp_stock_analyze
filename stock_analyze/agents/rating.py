"""Agent 3 — EP Rating: re-fetch news, judge EP catalyst substance, hard caps."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date
from typing import Any, Callable, Optional, Sequence, Union, cast

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from stock_analyze.models.catalyst import CatalystEnrichedStock, CatalystType
from stock_analyze.models.rating import (
    RATING_LABELS,
    EpRatedStock,
    EpRating,
    EpRatingProposal,
)

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_EP_RATING_LLM_MODEL = "deepseek/deepseek-v4-pro"

SYSTEM_PROMPT = (
    "You are an expert momentum trader evaluating an Episodic Pivot (EP). "
    "Judge whether the news is a real massive EPS/fundamental change to the business "
    "that matches a textbook EP catalyst. Do NOT invent chart base tightness. "
    "Use technical JSON (gap_pct, rvol10) only as caps/nudges — never boost a weak "
    "catalyst because volume or gap looks large. "
    "Rubric: 5=textbook (must look: clear earnings shock or guidance raise + strong volume); "
    "4=acceptable (real fundamental catalyst; chart later); "
    "3=better_not (weak/vague catalyst); 2=no (news does not support EP); "
    "1=bs (no credible catalyst). "
    "5 is reserved for EARNINGS/GUIDANCE shocks. "
    "Respond with JSON only matching keys: ticker, ep_rating (1-5 int), ep_rationale "
    "(max ~40 words)."
)

SearchNewsFn = Callable[[str], list[dict[str, str]]]
RateFn = Callable[[str, dict[str, Any], list[dict[str, str]]], dict[str, Any]]
TickerFn = Callable[[int, int, str, str], None]


def apply_rating_caps(
    proposed: int,
    *,
    catalyst_found: bool,
    catalyst_type: CatalystType | str,
    rvol10: float,
) -> EpRating:
    """Down-only clamps after LLM propose. Never boosts."""
    rating = max(1, min(5, int(proposed)))
    ctype = str(catalyst_type)

    if not catalyst_found or ctype == "UNKNOWN":
        rating = min(rating, 2)
    if ctype == "PR":
        rating = min(rating, 3)
    if ctype in ("CONTRACT", "FDA"):
        rating = min(rating, 4)
    if rvol10 < 3.0:
        rating = min(rating, 4)

    return cast(EpRating, rating)


def rate_ep_catalysts(
    stocks: Sequence[Union[CatalystEnrichedStock, dict[str, Any]]],
    *,
    tavily_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
    model: Optional[str] = None,
    search_news: Optional[SearchNewsFn] = None,
    rate_catalyst: Optional[RateFn] = None,
    on_ticker: Optional[TickerFn] = None,
    checkpoint: Optional[Callable[[], None]] = None,
) -> list[EpRatedStock]:
    """Rate Agent 2 stocks for EP catalyst fit. Soft-fails per symbol. Sorted best→worst.

    When ``on_ticker`` is given, it is called as
    ``on_ticker(index, total, symbol, action)`` before each network call so a
    Run Progress reporter can show which symbol is being worked on.
    ``checkpoint``, when given, is called at the top of each symbol loop to
    pause/cancel the run (raises ``RunCancelled`` on cancel).
    """
    if search_news is None or rate_catalyst is None:
        load_dotenv()

    search = search_news or _make_tavily_search(tavily_api_key)
    rate = rate_catalyst or _make_openrouter_rater(openrouter_api_key, model=model)

    rated: list[EpRatedStock] = []
    total = len(stocks)
    for index, raw in enumerate(stocks, start=1):
        if checkpoint is not None:
            checkpoint()
        base = _as_stock_dict(raw)
        symbol = str(base.get("symbol") or "").upper()
        try:
            if on_ticker is not None:
                on_ticker(index, total, symbol, "searching news")
            snippets = _with_retry(lambda: search(symbol), label="Tavily")

            def _rate_and_validate() -> EpRatingProposal:
                return EpRatingProposal.model_validate(rate(symbol, base, snippets))

            if on_ticker is not None:
                on_ticker(index, total, symbol, "rating")
            proposal = _with_retry(_rate_and_validate, label="LLM")
            rated.append(_merge(base, proposal))
        except Exception as exc:
            logger.warning("EP rating failed for %s: %s", symbol or "?", exc)
            rated.append(_soft_fail(base, str(exc)))

    rated.sort(key=lambda r: (-r.ep_rating, -r.rvol10, r.symbol))
    return rated


def _as_stock_dict(raw: Union[CatalystEnrichedStock, dict[str, Any]]) -> dict[str, Any]:
    if isinstance(raw, CatalystEnrichedStock):
        return raw.model_dump(mode="json")
    if isinstance(raw, dict):
        return dict(raw)
    raise TypeError(f"Expected CatalystEnrichedStock or dict, got {type(raw)!r}")


def _coerce_as_of(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("as_of"), str):
        data["as_of"] = date.fromisoformat(data["as_of"])
    return data


def _merge(base: dict[str, Any], proposal: EpRatingProposal) -> EpRatedStock:
    data = _coerce_as_of(dict(base))
    data["symbol"] = str(data.get("symbol") or proposal.ticker).upper()
    clamped = apply_rating_caps(
        proposal.ep_rating,
        catalyst_found=bool(data.get("catalyst_found")),
        catalyst_type=str(data.get("catalyst_type") or "UNKNOWN"),
        rvol10=float(data.get("rvol10") or 0.0),
    )
    data["ep_rating"] = clamped
    data["ep_rating_label"] = RATING_LABELS[clamped]
    data["ep_rationale"] = proposal.ep_rationale[:300]
    data["ep_catalyst_match"] = clamped >= 4
    return EpRatedStock.model_validate(data)


def _soft_fail(base: dict[str, Any], message: str) -> EpRatedStock:
    data = _coerce_as_of(dict(base))
    rationale = (
        message
        if message.startswith(("Tavily error:", "LLM error:"))
        else f"Error: {message}"
    )
    data["ep_rating"] = 1
    data["ep_rating_label"] = RATING_LABELS[1]
    data["ep_rationale"] = rationale[:300]
    data["ep_catalyst_match"] = False
    # Ensure catalyst fields exist if somehow missing
    data.setdefault("catalyst_found", False)
    data.setdefault("catalyst_type", "UNKNOWN")
    data.setdefault("catalyst_summary", "")
    return EpRatedStock.model_validate(data)


def _with_retry(fn: Callable[[], Any], *, label: str, attempts: int = 2) -> Any:
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            logger.debug("%s attempt %s failed: %s", label, i + 1, exc)
    assert last is not None
    raise RuntimeError(f"{label} error: {last}") from last


def _make_tavily_search(api_key: Optional[str]) -> SearchNewsFn:
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        raise ValueError("TAVILY_API_KEY is required (or pass tavily_api_key=...)")

    from tavily import TavilyClient

    client = TavilyClient(api_key=key)

    def search(symbol: str) -> list[dict[str, str]]:
        query = f"{symbol} earnings revenue beat surprise guidance FDA contract news"
        resp = client.search(
            query=query,
            topic="news",
            max_results=5,
            search_depth="basic",
        )
        results = resp.get("results") if isinstance(resp, dict) else None
        if results is None and hasattr(resp, "get"):
            results = resp.get("results")
        snippets: list[dict[str, str]] = []
        for item in results or []:
            if isinstance(item, dict):
                snippets.append(
                    {
                        "title": str(item.get("title") or ""),
                        "content": str(item.get("content") or ""),
                    }
                )
        return snippets

    return search


def _make_openrouter_rater(
    api_key: Optional[str],
    *,
    model: Optional[str] = None,
) -> RateFn:
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY is required (or pass openrouter_api_key=...)")

    base_url = os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL
    model_id = model or os.getenv("EP_RATING_LLM_MODEL") or DEFAULT_EP_RATING_LLM_MODEL
    client = OpenAI(api_key=key, base_url=base_url)

    def rate(symbol: str, stock: dict[str, Any], snippets: list[dict[str, str]]) -> dict[str, Any]:
        tech = {
            "symbol": symbol,
            "gap_pct": stock.get("gap_pct"),
            "rvol10": stock.get("rvol10"),
            "catalyst_found": stock.get("catalyst_found"),
            "catalyst_type": stock.get("catalyst_type"),
            "catalyst_summary": stock.get("catalyst_summary"),
            "price": stock.get("price"),
            "event_dollar_volume": stock.get("event_dollar_volume"),
        }
        user = (
            f"Technical/catalyst JSON:\n{json.dumps(tech, ensure_ascii=False)}\n\n"
            f"News snippets:\n{json.dumps(snippets, ensure_ascii=False)}\n\n"
            "Return JSON only."
        )
        t0 = time.perf_counter()
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        elapsed_s = time.perf_counter() - t0
        content = resp.choices[0].message.content or ""
        result = _parse_llm_json(content, symbol=symbol)
        logger.debug("LLM rating — %s: %.1fs", symbol, elapsed_s)
        if elapsed_s > 10:
            logger.warning("LLM rating — %s took %.1fs", symbol, elapsed_s)
        return result

    return rate


def _parse_llm_json(content: str, *, symbol: str) -> dict[str, Any]:
    text = content.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"LLM returned non-JSON: {text[:200]}")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM JSON must be an object")
    data.setdefault("ticker", symbol)
    try:
        return EpRatingProposal.model_validate(data).model_dump()
    except ValidationError as exc:
        raise ValueError(f"LLM JSON failed schema: {exc}") from exc
