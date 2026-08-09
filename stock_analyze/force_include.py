"""Force Include paste parsing — messy free text → SymbolKeys via cheap LLM."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from openai import OpenAI

from stock_analyze.data.symbols import SymbolKey

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_FORCE_INCLUDE_LLM_MODEL = "deepseek/deepseek-v4-flash-0731"

ParseFn = Callable[[str], dict[str, Any]]

SYSTEM_PROMPT = """\
You extract US equity tickers from messy user paste (comma lists, parentheses, notes).
Return JSON only:
{"symbols":[{"symbol":"AAPL","exchange":"NASDAQ"},...],"rejected":["token that is not a ticker",...]}
Rules:
- symbol: uppercase ticker only (letters/digits/. allowed); no exchange prefix in symbol
- exchange: NYSE, NASDAQ, AMEX, or ARCA when known; else NASDAQ
- Put non-tickers, garbage, and unparseable tokens in rejected (as original snippets)
- Deduplicate symbols; ignore empty tokens
"""


@dataclass
class ForceIncludeParseResult:
    symbols: list[SymbolKey] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_force_include_text(
    raw: str,
    *,
    parse_fn: Optional[ParseFn] = None,
) -> ForceIncludeParseResult:
    """Parse pasted Force Include text into SymbolKeys; surface rejected + errors."""
    text = (raw or "").strip()
    if not text:
        return ForceIncludeParseResult()

    fn = parse_fn or _make_openrouter_parser()
    try:
        payload = fn(text)
    except Exception as exc:
        return ForceIncludeParseResult(errors=[str(exc)])

    return _normalize_payload(payload)


def _normalize_payload(payload: Any) -> ForceIncludeParseResult:
    if not isinstance(payload, dict):
        return ForceIncludeParseResult(errors=["LLM JSON must be an object"])

    symbols_raw = payload.get("symbols") or []
    rejected_raw = payload.get("rejected") or []
    if not isinstance(symbols_raw, list):
        return ForceIncludeParseResult(errors=["LLM 'symbols' must be a list"])
    if not isinstance(rejected_raw, list):
        rejected_raw = []

    seen: set[SymbolKey] = set()
    symbols: list[SymbolKey] = []
    for item in symbols_raw:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        exchange = str(item.get("exchange") or "NASDAQ").strip().upper() or "NASDAQ"
        key = (symbol, exchange)
        if key in seen:
            continue
        seen.add(key)
        symbols.append(key)

    rejected: list[str] = []
    for token in rejected_raw:
        s = str(token).strip()
        if s:
            rejected.append(s)

    return ForceIncludeParseResult(symbols=symbols, rejected=rejected)


def _make_openrouter_parser() -> ParseFn:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError(
            "OPENROUTER_API_KEY is required to paste Force Include "
            "(or choose Skip)"
        )

    base_url = os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL
    model_id = os.getenv("FORCE_INCLUDE_LLM_MODEL") or DEFAULT_FORCE_INCLUDE_LLM_MODEL
    client = OpenAI(api_key=key, base_url=base_url)

    def parse(raw: str) -> dict[str, Any]:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Paste:\n{raw}\n\nReturn JSON only."},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        return _parse_llm_json(content)

    return parse


def _parse_llm_json(content: str) -> dict[str, Any]:
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
    return data
