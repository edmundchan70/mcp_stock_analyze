# stock_analyze

Local stock scanners. **Agent 1** is an Episodic Pivot (EP) technical filter (TradingView → Baseline / Strict JSON). **Agent 2** enriches those candidates with Tavily news + an OpenRouter LLM catalyst summary.

Domain terms: [glossary.md](glossary.md), [CONTEXT.md](CONTEXT.md).

## Setup

```bash
cd mcp_stock_analyze
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Needs network access to TradingView’s screener API. No API key for the EP scan.

## EP scan (Agent 1)

Run from `mcp_stock_analyze` after the cash open (RTH gap).

```bash
# Both buckets → file
python -m stock_analyze ep --out ep_scan.json

# Strict only in the file (Strict is always computed; --select controls output)
python -m stock_analyze ep --select strict --out ep_strict.json

# Baseline only in the file
python -m stock_analyze ep --select baseline --out ep_baseline.json

# Force-include tickers from CSV, write Strict bucket
python -m stock_analyze ep --csv force.csv --select strict --out ep_strict.json

# Cap screener rows / verbose logs
python -m stock_analyze ep --select strict --out ep_strict.json --limit 300 -v
```

### CLI flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--out PATH` | stdout | Write JSON to file |
| `--select` | `both` | Which top-level bucket(s) to include: `baseline`, `strict`, or `both` |
| `--csv PATH` | none | Force-include CSV (`symbol,exchange`) |
| `--limit N` | `300` | Max screener rows fetched |
| `-v` | off | Debug logging |

### Force-include CSV

```csv
symbol,exchange
AAPL,NASDAQ
TSLA,NASDAQ
```

Missing `exchange` defaults to `NASDAQ`. Symbols are merged with the screener universe and evaluated even if they did not appear in the screen.

## Gates

Both gates run every scan. `--select` only changes what is written.

| Metric | Baseline | Strict |
|--------|----------|--------|
| Price | ≥ $1 | ≥ $10 |
| Gap % | ≥ 4% | ≥ 8% |
| RVOL10 | ≥ 1.5× | ≥ 3.0× |
| Market cap | — | $300M – $10B |
| Avg daily $ volume (~50d) | — | ≥ $5M |
| Event-day $ volume | — | ≥ $20M |

- **Gap %** = `(open − prior close) / prior close` (RTH). TradingView `gap` used when open/prior close are absent.
- **RVOL10** = today’s volume / 10-day average volume.
- **Avg $ volume**: screener uses TradingView `AvgValue.Traded_60d` (nearest bulk field).
- Universe: US listed (NYSE / NASDAQ / AMEX, etc.). OTC excluded.

## Output JSON

```json
{
  "as_of": "2026-08-08T09:57:40.610352Z",
  "universe_source": "screener",
  "session": "rth",
  "gates": { "baseline": { "...": "..." }, "strict": { "...": "..." } },
  "baseline": { "count": 23, "stocks": [ /* ... */ ] },
  "strict": { "count": 7, "stocks": [ /* ... */ ] }
}
```

Each stock:

```json
{
  "symbol": "DOCS",
  "exchange": "NYSE",
  "price": 27.39,
  "market_cap": 4923449517.58,
  "avg_dollar_volume_50d": 150693568.40,
  "gap_pct": 88.12,
  "rvol10": 12.29,
  "event_dollar_volume": 1788996803.88,
  "force_included": false,
  "as_of": "2026-08-08"
}
```

Pick Strict for downstream work: read `strict.stocks` (or run with `--select strict`).

## Catalyst enrich (Agent 2)

Takes Agent 1 JSON (or a bare stock list), searches recent news via Tavily, compresses with an OpenRouter chat model, and writes enriched JSON. Always emits every input stock; missing/unclear news or API errors set `catalyst_found=false` and `catalyst_type=UNKNOWN` with a clear `catalyst_summary`.

### Env

| Variable | Required | Default |
|----------|----------|---------|
| `TAVILY_API_KEY` | yes | — |
| `OPENROUTER_API_KEY` | yes | — |
| `CATALYST_LLM_MODEL` | no | `openai/gpt-4o-mini` |
| `OPENROUTER_BASE_URL` | no | `https://openrouter.ai/api/v1` |

Put keys in `.env` (loaded automatically by the CLI) or the environment.

```bash
# Enrich Strict bucket from an Agent 1 file
python -m stock_analyze catalyst --in ep_strict.json --out ep_catalyst.json

# Enrich Baseline instead
python -m stock_analyze catalyst --in ep_scan.json --select baseline --out ep_catalyst.json
```

### Output

```json
{
  "count": 1,
  "stocks": [
    {
      "symbol": "NVDA",
      "exchange": "NASDAQ",
      "price": 125.0,
      "gap_pct": 11.2,
      "rvol10": 4.5,
      "event_dollar_volume": 150000000.0,
      "catalyst_found": true,
      "catalyst_type": "EARNINGS",
      "catalyst_summary": "Q2 EPS +45% YoY. FY guidance raised 15%."
    }
  ]
}
```

Library API for agents:

```python
from stock_analyze.agents import enrich_with_catalysts

enriched = enrich_with_catalysts(strict_stocks)
```

## Layout

```
stock_analyze/
  agents/         # Agent 2 catalyst enricher
  data/           # TradingView screener + OHLCV helpers
  models/         # EP + catalyst JSON schemas
  scanners/
    ep/           # gates, metrics, runner
  cli.py
tests/
```

VCP scripts (`vcp_scan.py`, `vcp_analyzer.py`, …) remain at the repo root; they are separate from the EP scanner.

## Tests

```bash
python -m pytest tests/ -v
```

## Schedule

Point Task Scheduler / cron at the CLI after the US cash open, e.g.:

```bash
python -m stock_analyze ep --select strict --out /path/to/ep_strict.json
```
