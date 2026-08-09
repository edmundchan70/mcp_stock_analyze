"""Agent 2 — Catalyst Intelligence: Tavily news + OpenRouter compression."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from typing import Any, Callable, Optional, Sequence, Union

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from stock_analyze.models.catalyst import CatalystEnrichedStock, CatalystSummary
from stock_analyze.models.ep import EpStock

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_CATALYST_LLM_MODEL = "deepseek/deepseek-v4-flash-0731"

SYSTEM_PROMPT = (
    "You are a financial news compressor. Summarize the fundamental driver behind "
    "the recent stock move into 1-2 short bullet points (max 30 words total). Focus "
    "strictly on EPS/revenue beats, guidance raises, contract wins, or FDA news. "
    "If no clear news exists, set catalyst_found=False and catalyst_type='UNKNOWN'. "
    "Respond with JSON only matching keys: ticker, catalyst_found, catalyst_type, summary. "
    "catalyst_type must be one of: EARNINGS, GUIDANCE, CONTRACT, FDA, PR, UNKNOWN."
)

SearchNewsFn = Callable[[str], list[dict[str, str]]]
SummarizeFn = Callable[[str, list[dict[str, str]]], dict[str, Any]]


def load_stocks_from_input(
    payload: Union[dict[str, Any], list[Any]],
    *,
    select: str = "strict",
) -> list[dict[str, Any]]:
    """Extract stock dicts from Agent 1 JSON or a bare list."""
    if isinstance(payload, list):
        return [dict(s) if not isinstance(s, dict) else s for s in payload]

    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object or list of stocks")

    if "stocks" in payload and isinstance(payload["stocks"], list) and select not in payload:
        return list(payload["stocks"])

    if select in ("baseline", "strict") and select in payload:
        bucket = payload[select] or {}
        stocks = bucket.get("stocks") if isinstance(bucket, dict) else None
        if stocks is None:
            raise ValueError(f"Missing '{select}.stocks' in Agent 1 payload")
        return list(stocks)

    if select == "both" and ("baseline" in payload or "strict" in payload):
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key in ("strict", "baseline"):
            bucket = payload.get(key) or {}
            for s in bucket.get("stocks") or []:
                sym = str(s.get("symbol", "")).upper()
                if sym and sym not in seen:
                    seen.add(sym)
                    out.append(s)
        return out

    raise ValueError(
        "Could not find stocks in input. Expected Agent 1 buckets "
        f"(select={select!r}) or a bare list / {{'stocks': [...]}}."
    )


def enrich_with_catalysts(
    stocks: Sequence[Union[EpStock, dict[str, Any]]],
    *,
    tavily_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
    model: Optional[str] = None,
    search_news: Optional[SearchNewsFn] = None,
    summarize_catalyst: Optional[SummarizeFn] = None,
) -> list[CatalystEnrichedStock]:
    """Enrich Agent 1 stocks with catalyst fields. Soft-fails per symbol."""
    if search_news is None or summarize_catalyst is None:
        load_dotenv()

    search = search_news or _make_tavily_search(tavily_api_key)
    summarize = summarize_catalyst or _make_openrouter_summarizer(
        openrouter_api_key, model=model
    )

    enriched: list[CatalystEnrichedStock] = []
    for raw in stocks:
        base = _as_stock_dict(raw)
        symbol = str(base.get("symbol") or "").upper()
        try:
            snippets = _with_retry(lambda: search(symbol), label="Tavily")

            def _summarize_and_validate() -> CatalystSummary:
                return CatalystSummary.model_validate(summarize(symbol, snippets))

            parsed = _with_retry(_summarize_and_validate, label="LLM")
            enriched.append(_merge(base, parsed))
        except Exception as exc:
            logger.warning("Catalyst enrich failed for %s: %s", symbol or "?", exc)
            enriched.append(_soft_fail(base, str(exc)))
    return enriched


def _as_stock_dict(raw: Union[EpStock, dict[str, Any]]) -> dict[str, Any]:
    if isinstance(raw, EpStock):
        return raw.model_dump(mode="json")
    if isinstance(raw, dict):
        return dict(raw)
    raise TypeError(f"Expected EpStock or dict, got {type(raw)!r}")


def _coerce_as_of(data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("as_of"), str):
        data["as_of"] = date.fromisoformat(data["as_of"])
    return data


def _merge(base: dict[str, Any], summary: CatalystSummary) -> CatalystEnrichedStock:
    data = _coerce_as_of(dict(base))
    data["symbol"] = str(data.get("symbol") or summary.ticker).upper()
    data["catalyst_found"] = summary.catalyst_found
    data["catalyst_type"] = summary.catalyst_type
    data["catalyst_summary"] = summary.summary
    return CatalystEnrichedStock.model_validate(data)


def _soft_fail(base: dict[str, Any], message: str) -> CatalystEnrichedStock:
    data = _coerce_as_of(dict(base))
    # Preserve existing error prefix if _with_retry already labeled it
    summary = message if message.startswith(("Tavily error:", "LLM error:")) else f"Error: {message}"
    data["catalyst_found"] = False
    data["catalyst_type"] = "UNKNOWN"
    data["catalyst_summary"] = summary[:300]
    return CatalystEnrichedStock.model_validate(data)


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
            max_results=3,
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


def _make_openrouter_summarizer(
    api_key: Optional[str],
    *,
    model: Optional[str] = None,
) -> SummarizeFn:
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY is required (or pass openrouter_api_key=...)")

    base_url = os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL
    model_id = model or os.getenv("CATALYST_LLM_MODEL") or DEFAULT_CATALYST_LLM_MODEL
    client = OpenAI(api_key=key, base_url=base_url)

    def summarize(symbol: str, snippets: list[dict[str, str]]) -> dict[str, Any]:
        user = (
            f"Symbol: {symbol}\n\nNews snippets:\n"
            + json.dumps(snippets, ensure_ascii=False)
            + "\n\nReturn JSON only."
        )
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        return _parse_llm_json(content, symbol=symbol)

    return summarize


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
        return CatalystSummary.model_validate(data).model_dump()
    except ValidationError as exc:
        raise ValueError(f"LLM JSON failed schema: {exc}") from exc
