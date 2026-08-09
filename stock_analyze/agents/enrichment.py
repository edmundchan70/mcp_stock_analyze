"""Agent 2 — VCP Context Enrichment: Tavily dual-query + OpenRouter LLM parse.

Mirrors EP's ``agents/catalyst.py`` pattern but with VCP-specific dual-query
(taxonomy + leadership) and down-only caps applied at parsing stage.

Only runs on 4-5★ VCP structural survivors (or all pasted if Run All).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Callable, Optional, Sequence, Union

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from stock_analyze.models.vcp import (
    IndustryGroupStrengthFlag,
    VcpContextEnrichment,
    VcpStructuralRating,
)

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_ENRICHMENT_LLM_MODEL = "deepseek/deepseek-v4-flash-0731"

SYSTEM_PROMPT = (
    "You classify a stock's sector/industry positioning and market leadership. "
    "Given search results, determine:\n"
    "- sector: broad sector (e.g. Technology, Healthcare, Financial)\n"
    "- industry: specific sub-industry\n"
    "- top_competitors: top 3-5 competitors by ticker/name\n"
    '- industry_group_strength_flag: "HOT_SECTOR" if strong momentum/rotation, '
    '"DECLINING_GROUP" if weak/out-of-favor, otherwise "NEUTRAL"\n'
    "- is_category_leader: true if top 1-3 in market share, revenue growth, "
    "or tech leadership in its specific sub-industry\n"
    "- market_leadership_context: 1-2 sentences summarizing market position\n"
    "- growth_catalysts: key growth drivers/catalysts\n"
    "- thematic_momentum: broader thematic/industry tailwinds helping this stock\n\n"
    "Respond with JSON only."
)

TickerFn = Callable[[int, int, str, str], None]

SearchTaxonomyFn = Callable[[str, str], list[dict[str, str]]]
SearchLeadershipFn = Callable[[str, str], list[dict[str, str]]]
ParseContextFn = Callable[
    [str, str, list[dict[str, str]]],
    dict[str, Any],
]


def _make_tavily_search(api_key: Optional[str]) -> tuple[
    SearchTaxonomyFn, SearchLeadershipFn
]:
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        raise ValueError("TAVILY_API_KEY is required (or pass tavily_api_key=...)")

    from tavily import TavilyClient

    client = TavilyClient(api_key=key)

    def search_taxonomy(symbol: str, company_name: str) -> list[dict[str, str]]:
        query = (
            f"{symbol} {company_name} stock sector industry classification "
            f"top competitors"
        )
        resp = client.search(
            query=query,
            topic="finance",
            search_depth="basic",
            max_results=5,
        )
        return _extract_snippets(resp)

    def search_leadership(symbol: str, company_name: str) -> list[dict[str, str]]:
        query = (
            f"{symbol} {company_name} market leader competitors "
            f"market share growth drivers key catalysts"
        )
        resp = client.search(
            query=query,
            topic="news",
            search_depth="advanced",
            max_results=5,
            time_range="month",
        )
        return _extract_snippets(resp)

    return search_taxonomy, search_leadership


def _extract_snippets(resp: Any) -> list[dict[str, str]]:
    results = resp.get("results") if isinstance(resp, dict) else None
    if results is None and hasattr(resp, "get"):
        results = resp.get("results")
    snippets: list[dict[str, str]] = []
    for item in results or []:
        if isinstance(item, dict):
            snippets.append({
                "title": str(item.get("title") or ""),
                "content": str(item.get("content") or ""),
                "url": str(item.get("url") or ""),
            })
    return snippets


def _make_openrouter_parser(
    api_key: Optional[str],
    *,
    model: Optional[str] = None,
) -> ParseContextFn:
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY is required (or pass openrouter_api_key=...)")

    base_url = os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL
    model_id = model or os.getenv("VCP_ENRICH_LLM_MODEL") or DEFAULT_ENRICHMENT_LLM_MODEL
    client = OpenAI(api_key=key, base_url=base_url)

    def parse(
        symbol: str,
        company_name: str,
        merged_snippets: list[dict[str, str]],
    ) -> dict[str, Any]:
        user = (
            f"Symbol: {symbol}\n"
            f"Company: {company_name}\n\n"
            f"Search results:\n"
            + json.dumps(merged_snippets, ensure_ascii=False)
            + "\n\nReturn JSON only."
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
        logger.debug("LLM VCP enrich — %s: %.1fs", symbol, elapsed_s)
        return result

    return parse


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
    data.setdefault("symbol", symbol)
    try:
        return VcpContextEnrichment.model_validate(data).model_dump()
    except ValidationError as exc:
        raise ValueError(f"LLM JSON failed schema: {exc}") from exc


def _dedup_urls(snippets_a: list[dict[str, str]], snippets_b: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge two snippet lists, deduplicating by URL."""
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for s in snippets_a + snippets_b:
        url = str(s.get("url", ""))
        if url and url in seen:
            continue
        seen.add(url)
        merged.append({k: v for k, v in s.items() if k != "url"})
    return merged


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


def _get_company_name(
    stock: Union[VcpStructuralRating, dict[str, Any]],
) -> str:
    """Extract company name from stock data. Falls back to symbol."""
    if isinstance(stock, dict):
        company = stock.get("company_name") or stock.get("name") or stock.get("symbol") or ""
        # Strip EXCHANGE: prefix if present
        if ":" in str(company) and not company.startswith(("HOT", "NEUTRAL", "DECLINING")):
            company = str(company).split(":", 1)[-1]
        return str(company)
    return stock.symbol


def enrich_with_vcp_context(
    stocks: Sequence[Union[VcpStructuralRating, dict[str, Any]]],
    *,
    tavily_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
    model: Optional[str] = None,
    search_taxonomy: Optional[SearchTaxonomyFn] = None,
    search_leadership: Optional[SearchLeadershipFn] = None,
    parse_context: Optional[ParseContextFn] = None,
    on_ticker: Optional[TickerFn] = None,
    max_concurrent: int = 5,
) -> list[VcpContextEnrichment]:
    """Enrich VCP structural ratings with context via Tavily dual-query.

    Per stock: two parallel Tavily calls (taxonomy + leadership) → dedup →
    LLM parse → VcpContextEnrichment. Soft-fails per symbol.

    Args:
        stocks: VcpStructuralRating models or dicts with symbol/exchange.
        tavily_api_key: Tavily API key (env fallback: TAVILY_API_KEY).
        openrouter_api_key: OpenRouter API key (env fallback: OPENROUTER_API_KEY).
        model: LLM model (env fallback: VCP_ENRICH_LLM_MODEL).
        search_taxonomy: Mockable taxonomy search function.
        search_leadership: Mockable leadership search function.
        parse_context: Mockable context parser function.
        on_ticker: Progress callback: (index, total, symbol, action).
        max_concurrent: Max concurrent stocks (Tavily rate limit).

    Returns:
        List of VcpContextEnrichment (soft-fail entries have error field set).
    """
    if search_taxonomy is None or search_leadership is None or parse_context is None:
        load_dotenv()

    tax_search, leader_search = (
        (search_taxonomy, search_leadership)
        if search_taxonomy is not None and search_leadership is not None
        else _make_tavily_search(tavily_api_key)
    )
    parser = parse_context or _make_openrouter_parser(openrouter_api_key, model=model)

    # Run sequentially with semaphore for rate limiting
    sem = asyncio.Semaphore(max_concurrent)

    async def _enrich_one(
        index: int,
        stock: Union[VcpStructuralRating, dict[str, Any]],
    ) -> VcpContextEnrichment:
        async with sem:
            if isinstance(stock, dict):
                symbol = str(stock.get("symbol") or "").upper()
                exchange = str(stock.get("exchange") or "NASDAQ").upper()
            else:
                symbol = stock.symbol.upper()
                exchange = stock.exchange.upper()

            company_name = _get_company_name(stock)

            try:
                if on_ticker is not None:
                    on_ticker(index, len(stocks), symbol, "searching sector")

                # Parallel Tavily calls
                loop = asyncio.get_running_loop()

                tax_future = loop.run_in_executor(
                    None,
                    lambda: _with_retry(
                        lambda: tax_search(symbol, company_name), label="Tavily taxonomy"
                    ),
                )
                leader_future = loop.run_in_executor(
                    None,
                    lambda: _with_retry(
                        lambda: leader_search(symbol, company_name), label="Tavily leadership"
                    ),
                )

                tax_snippets, leader_snippets = await asyncio.gather(
                    tax_future, leader_future, return_exceptions=True,
                )

                if isinstance(tax_snippets, Exception):
                    raise RuntimeError(f"Tavily taxonomy error: {tax_snippets}")
                if isinstance(leader_snippets, Exception):
                    raise RuntimeError(f"Tavily leadership error: {leader_snippets}")

                # Dedup
                merged = _dedup_urls(tax_snippets, leader_snippets)

                if on_ticker is not None:
                    on_ticker(index, len(stocks), symbol, "parsing context")

                # LLM parse
                parsed = await loop.run_in_executor(
                    None,
                    lambda: _with_retry(
                        lambda: parser(symbol, company_name, merged), label="LLM parse"
                    ),
                )

                context = VcpContextEnrichment.model_validate(parsed)
                context.symbol = symbol
                context.exchange = exchange
                return context

            except Exception as exc:
                logger.warning("VCP enrich failed for %s: %s", symbol, exc)
                return VcpContextEnrichment(
                    symbol=symbol,
                    exchange=exchange,
                    error=str(exc),
                )

    async def _run_all() -> list[VcpContextEnrichment]:
        tasks = [_enrich_one(i + 1, s) for i, s in enumerate(stocks)]
        return await asyncio.gather(*tasks)

    # Run async
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(_run_all())
        return loop.run_until_complete(_run_all())
    except RuntimeError:
        return asyncio.run(_run_all())


def load_vcp_stocks_from_input(
    payload: Union[dict[str, Any], list[Any]],
) -> list[dict[str, Any]]:
    """Extract VCP stock dicts from Agent 1 VCP bucket JSON.

    Handles:
    - Bare list of dicts
    - {"stocks": [...]}
    - {"five_star": [...], "four_star": [...], ...}
    - {"ratings": [...]} (VcpScanBucket style)
    """
    if isinstance(payload, list):
        return [dict(s) if not isinstance(s, dict) else s for s in payload]

    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object or list")

    if "stocks" in payload and isinstance(payload["stocks"], list):
        return list(payload["stocks"])

    # VcpScanBucket style: combine 5★ + 4★ (only passing stocks get enrichment)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("five_star", "four_star"):
        items = payload.get(key) or []
        for s in items:
            sym = str(s.get("symbol", "")).upper()
            if sym and sym not in seen:
                seen.add(sym)
                out.append(s)
    return out
