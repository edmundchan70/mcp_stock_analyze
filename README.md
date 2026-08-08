# stock_analyze

Local stock scanners. Phase 1 ships an **Episodic Pivot (EP)** technical filter: pull US listed names from TradingView, apply Baseline / Strict gates in Python, write JSON. No LLM. No raw OHLC in the output.

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

## Layout

```
stock_analyze/
  data/           # TradingView screener + OHLCV helpers
  models/         # EP JSON schemas
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
