# stock_analyze

Local stock scanners. **Agent 1** is an Episodic Pivot (EP) technical filter (TradingView → Baseline / Strict JSON). **Agent 2** enriches candidates with Tavily news + an OpenRouter LLM catalyst summary. **Agent 3** re-fetches news and assigns an **EP Rating** (1–5); you chart the 4–5★ shortlist manually. Pivot/base auto-detect is **v2** (see glossary).

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

## Daily Run (Phase 4 — recommended)

Interactive wizard (arrow keys + Enter). Chains Agent 1 → 2 → 3 and stamps **Run Artifacts**.

```bash
# Windows
.\run.ps1

# macOS / Linux
./run.sh

# Or directly
python -m stock_analyze
```

**Auto Run:** Pipeline Type (**Daily EP scan**) → Force Include (**Skip** / **Paste symbols…**) → Gate (**Strict (recommended)** / Baseline / Both) → run name → full chain. Paste confirmed → screener off; Agent 1 runs only on pasted names and **always** applies Gate (no “Run all”).

**Manual Run:** Force Include first. **Skip** → Gate → Catalyst yes/no (no ⇒ Agent 1 only; EP Rating does not run) → Analysis Method (**EP Rating**) → run name. **Paste confirmed** → choose **Apply Gate filter** (then Gate select) or **Run all pasted** (skip gates; no Gate select) → Catalyst / Analysis → run name.

**Force Include paste:** free-text list (e.g. `( JHX, KGC, LUNR, MB, )`) → cheap OpenRouter LLM cleans to tickers → shows accepted + rejected/errors → confirm → Universe is paste-only (screener off). Skip leaves today’s screener → Gate → Agent 1 path. Needs `OPENROUTER_API_KEY` only when pasting (Skip does not).

Outputs land under:

```
output/<YYYY-MM-DD>/<HHMMSS>_<name>/
  <name>_agent1.json
  <name>_agent2.json   # if Catalyst ran
  <name>_agent3.json   # if EP Rating ran
  run_meta.json
```

Legacy one-shot commands (`ep` / `catalyst` / `rate`) remain for debugging. Scheduling can later call `run_daily(RunConfig(...))` from `stock_analyze.pipeline` (no scheduler wired yet).

## EP scan (Agent 1)

Legacy / debug entry. Prefer the Daily Run wizard above for the after-close habit.

```bash
# Both buckets → file
python -m stock_analyze ep --out ep_scan.json

# Strict only in the file (Strict is always computed; --select controls output)
python -m stock_analyze ep --select strict --out ep_strict.json

# Baseline only in the file
python -m stock_analyze ep --select baseline --out ep_baseline.json

# Cap screener rows / verbose logs
python -m stock_analyze ep --select strict --out ep_strict.json --limit 300 -v
```

Force Include paste lives on the Daily Run wizard (not on legacy `ep`).

### CLI flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--out PATH` | stdout | Write JSON to file |
| `--select` | `both` | Which top-level bucket(s) to include: `baseline`, `strict`, or `both` |
| `--limit N` | `300` | Max screener rows fetched |
| `-v` | off | Debug logging |

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
| `CATALYST_LLM_MODEL` | no | `deepseek/deepseek-v4-flash-0731` |
| `EP_RATING_LLM_MODEL` | no | `deepseek/deepseek-v4-pro` |
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
from stock_analyze.agents import enrich_with_catalysts, rate_ep_catalysts

enriched = enrich_with_catalysts(strict_stocks)
rated = rate_ep_catalysts(enriched)
```

## EP Rating (Agent 3)

Takes Agent 2 JSON, re-fetches news via Tavily, rates each name 1–5 for EP-catalyst fit (DeepSeek V4 Pro by default), applies hard caps, and sorts best→worst. **Console defaults to 4–5★ only**; `--out` always writes the full 1–5 list. Chart review is manual in v1 (see [glossary.md](glossary.md) EP Rating rubric).

```bash
# After catalyst enrich
python -m stock_analyze rate --in ep_catalyst.json --out ep_rated.json

# Print all ratings on console
python -m stock_analyze rate --in ep_catalyst.json --out ep_rated.json --min-rating 1
```

### Daily chain (legacy three-command path)

Prefer `python -m stock_analyze` (wizard). Manual equivalent:

```bash
python -m stock_analyze ep --select strict --out ep_strict.json
python -m stock_analyze catalyst --in ep_strict.json --out ep_catalyst.json
python -m stock_analyze rate --in ep_catalyst.json --out ep_rated.json
# Chart the printed 4–5★ names yourself
```

## Layout

```
stock_analyze/
  agents/         # Agent 2 catalyst + Agent 3 EP rating
  data/           # TradingView screener + OHLCV helpers
  models/         # EP + catalyst + rating JSON schemas
  scanners/
    ep/           # gates, metrics, runner
  pipeline.py     # Daily Run (stamped Agent 1→2→3)
  interactive.py  # arrow-key wizard
  cli.py
run.ps1 / run.sh  # launch wizard
output/           # stamped Run Artifacts (gitignored)
tests/
```

VCP scripts (`vcp_scan.py`, `vcp_analyzer.py`, …) remain at the repo root; they are separate from the EP scanner.

## Tests

```bash
python -m pytest tests/ -v
```

## Schedule

Not wired yet. When you add Task Scheduler / cron after the US cash close, prefer a future non-interactive entry such as `python -m stock_analyze run --auto --select strict --name daily` (not implemented), which should call the same pipeline core (`stock_analyze.pipeline.run_daily`). Keep the wizard for desk use.
