# PA Agent — External Reference Project

- **Repository**: https://github.com/rosemarycox5334-debug/PA_Agent
- **Stars**: ~1.8k, **Forks**: ~720, **License**: AGPL-3.0-or-later
- **Purpose**: Desktop (PyQt6) AI K-line analysis tool — two-stage LLM pipeline: market diagnosis → trade decision
- **Key entry points**: `pa_agent/main.py:»main()` → `pa_agent/app_context.py:»AppContext.bootstrap()`
- **Depends on**: `PyQt6`, `pyqtgraph`, `numpy`, `pandas`, `openai`, `pydantic`, `tvdatafeed`, `akshare`, `cryptography`
- **Python**: >=3.11, managed via `uv` with `uv.lock`

---

## Architecture Overview

```
                    ┌─────────────────────────────┐
                    │       pa_agent/main.py       │  ← PyQt6 QApplication entry
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │  AppContext.bootstrap()      │  ← DI wiring: settings, data source,
                    │  app_context.py              │     AI client, validator, router,
                    └─────────────┬───────────────┘     assembler, ledger, pending_writer
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
   ┌──────▼──────┐        ┌──────▼──────┐        ┌──────▼──────┐
   │  Data Layer │        │  AI Layer   │        │ GUI Layer   │
   │             │        │             │        │             │
   │ MT5Source   │        │ DeepSeek    │        │ MainWindow  │
   │ TV Source   │        │ Client      │        │ KlineChart  │
   │ AkShare     │        │ Router      │        │ DecisionFlow│
   │ EastMoney   │        │ Validator   │        │ Settings UI │
   │ TuShare     │        │ Assembler   │        │ Chat Panel  │
   └─────────────┘        │ Ledger      │        └─────────────┘
                          │ PatternRoute│
                          └─────────────┘
```

### Two-Stage Analysis Pipeline

```
[K-line data fetched] → Stage 1: Market Diagnosis → Stage 2: Trade Decision
                              │                           │
                        JSON output:                 JSON output:
                        cycle_position,              trade_signal,
                        direction, patterns,         entry_price, stop_loss,
                        trend_context,               take_profit, confidence,
                        bar_by_bar_features          order_type (limit/breakout/market)
```

Stage 1→Stage 2 routing is deterministic: `route_strategy_files()` maps `cycle_position` + `detected_patterns` → subset of 28 `.txt` strategy files loaded as Stage 2 system prompt.

---

## Package Structure & File Roles

### Entry & Wiring

| File | Role |
|------|------|
| `run.py` | Runner script — detects IPython/Jupyter kernel, launches detached subprocess if inside Spyder |
| `pa_agent/main.py` | `main()` — crash diagnostics → QApplication → `AppContext.bootstrap()` → `MainWindow` |
| `pa_agent/app_context.py` | `AppContext` dataclass with `bootstrap()` — wires all components via DI (no globals) |
| `Makefile` | `run`, `test`, `lint`, `uv-run`, `uv-test`, `uv-lint`, `setup-secrets` targets |

### Config Layer (`pa_agent/config/`)

| File | Role |
|------|------|
| `settings.py` | Pydantic v2 `Settings` model: `AIProviderSettings`, `GeneralSettings`, `PromptSettings`, `ValidationSettings`, `FeishuSettings`. Includes migration logic, `load_settings()` / `save_settings()` persistence |
| `paths.py` | `SETTINGS_JSON_PATH`, `RECORDS_PENDING_DIR`, `EXPERIENCE_DIR`, `PROMPT_DIR` path constants |
| `config/README.md` | Full settings.json field documentation in Chinese |

### Data Layer (`pa_agent/data/`)

| File | Role |
|------|------|
| `base.py` | `DataSource` ABC, `KlineBar`, `KlineFrame`, `DataSourceTransientError` |
| `factory.py` | `create_data_source(kind)` — returns `MT5Source`, `TradingViewSource`, `AkShareSource`, etc. by kind string |
| `tradingview.py` | `TradingViewSource(DataSource)` — full implementation with socket cleanup, exchange auto-probe, thread mutex (see "TradingView Adapter" section below) |
| `mt5.py` | `MT5Source` — Windows-only, MetaTrader5 integration |
| `akshare_source.py` | `AkShareSource` — A-share data via akshare |
| `eastmoney_source.py` | `EastMoneySource` — 东方财富 |
| `eastmoney_futures_source.py` | `EastMoneyFuturesSource` — 东方财富期货 |
| `tushare_source.py` | `TushareSource` — Tushare Pro |
| `yfinance_source.py` | `YFinanceSource` — yfinance fallback |
| `market_defaults.py` | Symbol defaults, exchange probing plans, timeframe mappings |
| `tv_symbol_lookup.py` | TradingView symbol name resolution with user-aliases |
| `tradingview_errors.py` | `format_tradingview_fetch_error()` — human-readable error messages |
| `kline_adjust.py` | `apply_kline_adjust_from_settings()` — A-share qfq/hfq adjustment |
| `datetime_ts.py` | `datetime_to_ts_ms()` helper |
| `bar_close_wait.py` | `seconds_until_bar_closes()` — determine if bar is still forming |

**Key: `data/factory.py:»create_data_source()`**
- `kind="tradingview"` → `TradingViewSource()`
- `kind="mt5"` → `MT5Source()`
- `kind="akshare"` → `AkShareSource()`
- `kind="eastmoney"` → `EastMoneySource()`
- `kind="eastmoney_futures"` → `EastMoneyFuturesSource()`
- `kind="tushare"` → `TushareSource(settings=...)`
- `kind="yfinance"` → `YFinanceSource()`
- Data source is created once at bootstrap, never swapped at runtime.

### AI Layer (`pa_agent/ai/`)

| File | Lines | Role |
|------|-------|------|
| `client_factory.py` | ~30 | `create_ai_client(settings, logger)` — routes to `DeepSeekClient` or `CursorSdkClient` based on model name prefix |
| `deepseek_client.py` | 782 | `DeepSeekClient` — OpenAI-compatible streaming client with reasoning_content handling, retry, MiMo adapter |
| `cursor_sdk_client.py` | — | `CursorSdkClient` — Cursor SDK integration |
| `prompt_assembler.py` | 1942 | `PromptAssembler` — builds Stage 1 & 2 system/user prompts from K-line data, strategy files, experience |
| `json_validator.py` | 1148 | `JsonValidator` — jsonschema validation, truncation repair, coherence checks, semantic checks, structured retry feedback (see "Validation Layer" section) |
| `router.py` | — | `route_strategy_files(stage1_json)` — deterministic strategy-to-file mapping |
| `session_ledger.py` | — | `SessionTokenLedger(QObject)` — accumulated token tracking with threshold warnings (80%/95%) |
| `pattern_routing.py` | — | `merge_detected_patterns(stage1_json)` — normalizes pattern tags from Stage 1 output |
| `qclaw_connector.py` | — | Syncs Qclaw agent provider settings |
| `workbuddy_connector.py` | — | Syncs Workbuddy provider settings |
| `cursor_connector.py` | — | `is_openclaw_cs_model(model)` — detects Cursor SDK model prefix |

### Records & Experience (`pa_agent/records/`)

| File | Role |
|------|------|
| `schema.py` | Pydantic models: `RecordMeta`, `AnalysisRecord`, `FollowupTurn`, `AlarmPayload`, `ValidationError`, `ExperienceEntry` |
| `pending_writer.py` | `PendingWriter` — saves `AnalysisRecord` as `{ts}_{symbol}_{tf}.json`, appends followups to `.followups.jsonl`, sanitizes API keys |
| `experience_reader.py` | `ExperienceReader` — reads top-5 experience cases by `cycle_position`, scored by direction/pattern match for Stage 2 |

### GUI Layer (`pa_agent/gui/`)

Not explored in detail, but key files: `main_window.py`, `theme.py`, `kline_chart.py`, `decision_flow.py`, `chat_panel.py`.

---

## TradingView Adapter — Critical Patterns

**File**: `pa_agent/data/tradingview.py`

### Socket Cleanup After Every Fetch

```
pat_design—NOT code copy:

After every tvDatafeed.get_hist() call:
  1. Get tv.ws (the WebSocket stored on the tvDatafeed instance)
  2. Call ws.close()
  3. Set tv.ws = None

This fixes tvDatafeed's socket leak where each get_hist()
opens a new socket without closing the old one.
```

### Thread Safety via Mutex

```
pat_design:

TradingViewSource._snapshot_lock = threading.Lock()

latest_snapshot(n):
    with self._snapshot_lock:
        return self._latest_snapshot_inner(n)

Rationale: tvDatafeed is NOT thread-safe — get_hist()
writes to self.ws on each call. Concurrent calls clobber
the same socket and cause C++ segfaults.
```

### Exchange Auto-Probe

```
pat_design:

_fetch_tv_auto_probe(symbol, plan, interval, n_bars):
    For each (exchange, code) in plan:
        Try get_hist(symbol=code, exchange=exchange, ...)
        If data returned → success, return (df, exchange)
        If empty/timeout → continue to next exchange
    If all fail → raise DataSourceTransientError

Pre-defined exchange probe order:
    OANDA, PEPPERSTONE, FOREXCOM, FX, TVC, CAPITALCOM,
    SSE, SZSE, HKEX, SP, NYSE, NASDAQ, CBOT, CME_MINI
```

### Retry Strategy

```
pat_design:

_TV_FETCH_RETRIES = 1  (not 3 — only retry once per exchange)
_TV_FETCH_RETRY_SLEEP_S = 0.5
_TV_WS_TIMEOUT_S = 10.0  (overrides tvDatafeed's hardcoded 15s)

One attempt per fetch cycle. Socket close is in a finally
block so it always runs even on exception.
```

---

## Validation Layer — `json_validator.py`

1148 lines. Categorized validation with structured retry feedback.

### Error Categories

| Category | Name | Description |
|----------|------|-------------|
| `a` | Format/Syntax | JSON decode error, truncated streaming tail |
| `b` | Schema | Missing required fields, field type mismatch per jsonschema |
| `c` | Semantic | Cross-field conflicts (direction vs signal), coherence violations |
| `d` | Downgrade | Non-critical warnings that don't block flow |

### Truncation Repair

```
pat_design:

Before JSON parsing:
  1. Try raw parse
  2. If JSONDecodeError with "Unterminated string":
     - Find last complete "key": "value" pair
     - Append synthetic closing brackets/braces to rebalance
     - Retry parse
  3. If still failing → category 'a' error with retry feedback
```

Configurable via `validation.disable_truncation_repair` (default: `false` = enabled).

### Retry with Structured Feedback

```
pat_design:

On validation failure (category 'a' or 'b'):
  1. Build structured feedback JSON containing:
     - Earlier error: the missing_fields / invalid_fields
     - Earlier raw_text: the failing LLM output
     - Suggestion: what to fix
  2. Inject feedback into the NEXT LLM call as part of the prompt
  3. LLM sees "Previous attempt failed: ... Fix: ..."
  4. Retry up to retry_max (3) for format errors, retry_max_semantic (1) for semantic

Failure count resets per new analysis request (not cumulative across sessions).
```

### Re-raise Logic

```
If all retries exhausted → raise with "Final Validation Failure (N retries)"
→ PendingWriter.save_partial() with _partial_reason
→ GUI shows AlarmPayload to user
```

---

## Prompt Assembly — `prompt_assembler.py`

1942 lines. Builds both Stage 1 and Stage 2 prompts.

### Stage 1 Prompt Structure

```
System:
  人物设定 (persona) → 市场诊断框架 (diagnosis framework) → pattern判定表 + 速查brief

User:
  symbol, timeframe, bar_count meta
  K-line data formatted as structured text (open/high/low/close/volume per bar)
  bar-by-bar sequence
```

### Stage 2 Prompt Structure

```
System:
  策略文件 (strategy files selected by router)
  交易规则 (trading rules)
  decision_stance override (conservative/balanced/aggressive/extreme_aggressive)

User:
  Stage 1 diagnosis JSON
  K-line data (same as Stage 1)
  experience_loaded (top-N cases from experience library)
```

### Experience Injection

```
pat_design:

prompt.experience_max_entries (default: 3, range: 0–10)
prompt.experience_max_chars_per_entry (default: 400, range: 100–4000)

ExperienceReader.read_top5(cycle_position) returns up to 5 entries
PromptAssembler truncates each to max_chars_per_entry
Injected into Stage 2 user prompt as reference cases
```

### Pattern Briefs Injection

```
pat_design:

prompt.stage1_inject_pattern_briefs (default: true)

When enabled, Stage 1 prompt includes:
  - 模式判定表 (pattern recognition table)
  - 速查brief (quick-reference summaries)

Reduces "missed tags" — LLM is more likely to correctly label
wedge, MTR, final_flag, H1/H2, etc. when the definitions
are in-prompt.
```

---

## Settings System — `config/settings.py`

### Settings Hierarchy

```
Settings (root)
├── AIProviderSettings  — model, base_url, api_key, thinking, reasoning_effort, context_window
├── GeneralSettings     — symbol, timeframe, bar_count, data_source, refresh_interval, keep_analysis, decision_stance
├── PromptSettings      — stage2_full_library, experience_max_entries, stage1_inject_pattern_briefs
├── ValidationSettings  — normalization_mode, coherence_checks, retry_enabled, retry_max, truncation_repair
├── FeishuSettings      — 飞书 bot: webhook_url, secret, app_id, notify_on_order_only
├── PushPlusSettings    — PushPlus notification: enabled, token
└── TushareSettings     — Tushare Pro: token
```

### Persistence & Migration

```
pat_design:

load_settings(path):
  1. If path doesn't exist → save Settings() defaults, return defaults
  2. Read JSON, handle decode errors → return defaults on failure
  3. Migrate legacy field names (cost_warning → context_warning, default_bar_count → analysis_bar_count)
  4. Migrate legacy feishu.json → settings.feishu section
  5. Validate with Pydantic, save back if migration dirtied the file
  6. Return validated Settings instance

save_settings(settings, path):
  1. mkdir parent
  2. model_dump() → json.dumps(indent=2, ensure_ascii=False)
  3. Write to disk
```

### API Key Handling

- `api_key` is stored in memory only (never persisted to settings.json)
- `api_key_encrypted` is persisted (encrypted via `cryptography` library)
- GUI Save encrypts the key and writes only `api_key_encrypted`
- `PendingWriter._sanitize()` replaces all occurrences of the raw API key with masked version in saved records
- `provider_api_key_configured()` checks if a non-empty key is loaded

---

## Strategy Router — `ai/router.py`

### Routing Table

```
cycle_position → base strategy files:

micro_channel     → channel files (bullish/bearish) ± spike files if active/ending
tight_channel     → channel files (bullish/bearish)
normal_channel    → channel files (bullish/bearish)
broad_channel     → channel files (bullish/bearish)
spike             → spike files + (if ending: channel files)
trading_range     → range files
trending_tr       → range files
extreme_tr        → NO files (do not trade)
unknown           → NO files (do not trade)
```

### Pattern Overlays

Additional strategy files are appended based on `detected_patterns`:
- `wedge` → `文件14-楔形形态分析交易.txt`
- `mtr` → `文件25-主要趋势反转MTR.txt` + `文件15-二次入场机会.txt`
- `final_flag` → `文件24-最终旗形与趋势末端.txt` + `文件15-二次入场机会.txt`
- `h1`, `h2`, `l1`, `l2` → `文件19-H1H2-L1L2计数.txt`
- `breakout_failure` → `文件18-突破失败与突破测试.txt`
- `always_in`, `ais`, `ail`, `20gb` → `文件20-AlwaysIn与20GB.txt`
- `barbwire`, `wire` → `文件21-铁丝网与无交易环境.txt`
- `failed_signal`, `magnet` → `文件22-信号失败后的磁力位.txt`
- `ascending_triangle`, `descending_triangle`, etc. → `文件27-三角形与收敛形态.txt`
- `double_top_bottom` → `文件28-双重顶底与微型结构.txt`

### Alternative Cycle Position

If `alternative_cycle_position` differs from `cycle_position`, both sets of base files are loaded. Dual-diagnosis support for borderline cases.

---

## Token Ledger — `ai/session_ledger.py`

```
pat_design:

SessionTokenLedger(QObject):
  Signals:
    threshold_crossed(str, dict)  — "yellow" at 80%, "red" at 95%
    updated(dict)                 — after every add()

  add(usage): accum input+cached+output, fire threshold signals
  reset(): zero counters, reset fired flags
  breakdown(): return {total_input, total_cached_input, total_output, context_used, context_window, context_pct}
```

Thresholds fire once per session (not repeatedly). Reset on symbol/timeframe switch.

---

## Experience Library — `records/experience_reader.py`

### Storage Layout

```
EXPERIENCE_DIR/
  micro_channel/
    success_cases/    ← {YYYY-MM-DD_HH-mm-ss}_{symbol}_{tf}.json
    failure_cases/    ← same filename convention
  trading_range/
    success_cases/
    failure_cases/
  ...
```

### Read Path

```
read_top5(cycle_position):
  1. Scan success_cases/ + failure_cases/ under cycle_position/
  2. Parse timestamp from filename via regex
  3. Sort by timestamp DESC (newest first)
  4. Return top 5 as list[ExperienceEntry]

read_for_stage2(cycle_position, direction, patterns):
  1. read_top5(cycle_position)
  2. Score by direction match (+2) + pattern overlap (+1 per pattern)
  3. Sort by score DESC then timestamp DESC
  4. Cap at max_entries (default 3)
```

---

## Event Bus — `util/event_bus.py`

```
pat_design:

EventBus(QObject):
  Signals:
    data_frame(KlineFrame)   — emitted by RefreshLoop on new bar
    status(str)              — status bar text
    exception(AlarmPayload)  — validation alarm
    token_update(dict)       — token usage update

  Convenience methods: emit_status(), emit_exception(), emit_data_frame(), emit_token_update()
```

Single instance wired through `AppContext`, shared across GUI and orchestrator.

---

## Record Persistence — `records/pending_writer.py`

### File Naming

```
{YYYY-MM-DD_HH-mm-ss}_{symbol}_{timeframe}.json           — full analysis record
{YYYY-MM-DD_HH-mm-ss}_{symbol}_{timeframe}.followups.jsonl — chat followup turns
```

### Key Behaviors

- `save_full(record)` → writes complete `AnalysisRecord` with API key sanitization
- `save_partial(record, reason)` → writes with `_partial_reason` injected into dict; used on validation failure / exception
- `append_followup(record_id, turn)` → JSONL append (one line per turn)
- `_sanitize(data, api_key)` → recursive string replacement of API key with masked value
- All disk errors caught and logged — never propagated to caller

---

## Key Patterns Worth Adopting (Architecture Only — No Code Copy)

### 1. Socket Cleanup After Every tvDatafeed Fetch

Our `stock_analyze/data/tradingview.py` calls `tvDatafeed.get_hist()` but never closes the underlying WebSocket. PA_Agent closes `tv.ws` after every fetch in a `finally` block. This is the root cause of cascading timeouts.

### 2. Exchange Auto-Detection for US Equities

Instead of trusting the screener's exchange (which maps many NYSE stocks to NASDAQ), probe each exchange sequentially with a single attempt: NASDAQ → NYSE → AMEX → BATS. Abort on first success.

### 3. Single-Attempt Per Exchange, Not 3 Retries on Wrong Exchange

Our current code retries the same (wrong) exchange 3 times before falling back. PA_Agent does 1 attempt per exchange. This would cut enrichment time from ~19s/symbol to ~1-3s for the common case.

### 4. Pydantic v2 Settings Model

Instead of scattered `os.getenv()` + `dataclass` defaults, a single `Settings` model with typed sub-models, validation, migration, and persistence.

### 5. Truncation Repair for Streaming LLM JSON

When the LLM response is cut off mid-stream (common with reasoning_content models), attempt to repair the JSON tail before rejecting. Configurable on/off.

### 6. Structured Retry Feedback

Instead of blind retry, inject the exact validation error (missing fields, invalid values) back into the retry prompt so the LLM can self-correct.

### 7. Thread Mutex for tvDatafeed

tvDatafeed is not thread-safe. Concurrent `get_hist()` calls clobber the shared `ws` attribute. A `threading.Lock` serializes access.

---

## Differences From Our EP Pipeline

| Dimension | PA_Agent | Our EP Pipeline |
|-----------|----------|-----------------|
| **Scope** | Single-symbol deep analysis (Price Action) | Multi-symbol daily scan (EP catalyst screening) |
| **Analysis depth** | Two stages per symbol, 28 strategy files, experience library | One LLM call per symbol (compression or rating) |
| **Data source** | Live desktop with PyQt6 GUI, manual symbol selection | Batch CLI, no GUI, automated screener pull |
| **TradingView usage** | OHLCV fetch only (no screener) | Screener first, OHLCV as fallback |
| **Validation** | 1148-line multi-category validator with retry feedback | Bare `json.loads()` try/except + one blind retry |
| **Config** | Pydantic Settings with migration + persistence | `.env` file + `os.getenv()` + dataclass defaults |
| **tvDatafeed handling** | Socket cleanup after every fetch, thread mutex | No socket cleanup, no mutex |
| **Exchange resolution** | Auto-probe with ordered fallback | Blind trust of screener exchange + multi-retry |
| **License** | AGPL-3.0 | Unknown |

---

## Files NOT Accessible

These files are in the repo but could not be fetched via raw GitHub URLs (likely directory structure mismatch):

- `tests/` — all test files (flat directory, not under `tests/pa_agent/`)
- `pa_agent/gui/` — all GUI files (main_window, kline_chart, decision_flow, chat_panel, settings_ui, theme)
- `pa_agent/ai/pattern_routing.py` — full content not fetched
- `pa_agent/data/mt5.py` — full content not fetched
- `pa_agent/data/base.py` — full content not fetched
- `prompt_engineering/` — strategy `.txt` files (28 files)
- `scripts/`, `tools/`, `.githooks/` — dev tooling

---

## Source Files Fetched (for Reference)

| File | Fetched | Key Content |
|------|---------|-------------|
| `pyproject.toml` | Yes | Dependencies, build config, tool settings |
| `run.py` | Yes | IPython detection, subprocess launcher |
| `Makefile` | Yes | uv targets |
| `pa_agent/__init__.py` | Yes | Version 0.1.0 |
| `pa_agent/main.py` | Yes | Entry point, crash diagnostics, QApplication |
| `pa_agent/app_context.py` | Yes | DI bootstrap — all components wired |
| `pa_agent/config/settings.py` | Yes | Pydantic Settings, migration, persistence |
| `config/README.md` | Yes | Full settings.json field documentation |
| `pa_agent/data/tradingview.py` | Yes | TV adapter: socket cleanup, auto-probe, mutex |
| `pa_agent/data/factory.py` | Yes | Data source factory with all kinds |
| `pa_agent/ai/client_factory.py` | Yes | AI client routing (DeepSeek vs Cursor SDK) |
| `pa_agent/ai/deepseek_client.py` | Yes | 782-line OpenAI-compatible streaming client |
| `pa_agent/ai/prompt_assembler.py` | Yes | 1942-line prompt builder (Stage 1+2) |
| `pa_agent/ai/json_validator.py` | Yes | 1148-line validation with truncation repair |
| `pa_agent/ai/router.py` | Yes | Strategy file routing table |
| `pa_agent/ai/session_ledger.py` | Yes | Token tracking with Qt signals |
| `pa_agent/records/schema.py` | Yes | All Pydantic record models |
| `pa_agent/records/pending_writer.py` | Yes | Record persistence with API key sanitization |
| `pa_agent/records/experience_reader.py` | Yes | Experience library reader with scoring |
| `pa_agent/util/event_bus.py` | Yes | Qt signal hub |
