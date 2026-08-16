Type: research
Status: resolved

## Question

Inventory every hardcoded threshold, gate, profile, and cap across the EP, VCP, and BO pipelines — plus every `RunConfig` field — that must surface as an editable inspector variable on a Phase. For each: canonical name, current default value, the `file:line` where it is defined, and which Phase(s) own it. Include the EP Baseline/Strict `GateThresholds`, VCP/BO liquidity + market-cap gates, VCP structural rubric parameters, BO funnel profiles and the `Q_base` floor, and the down-only cap rules.

## Answer

All paths relative to `mcp_stock_analyze/`. This is the canonical list of inspector variables; an editor must expose each as an editable field on the owning Phase.

### Run-level / RunConfig (`stock_analyze/pipeline.py:89-102`)

| Variable | Default | Defined at | Owned by |
|---|---|---|---|
| `name` | required | `pipeline.py:91` | Run |
| `select` | `"strict"` (`baseline\|strict\|both`) | `pipeline.py:92` | EP Scan |
| `run_catalyst` | `True` | `pipeline.py:93` | Enrich (skip when False) |
| `analysis_method` | `"ep_rating"` | `pipeline.py:94` | EP Rating/Report |
| `limit` | `300` | `pipeline.py:95` | Scan (universe cap) |
| `force_keys` | `None` | `pipeline.py:96` | Scan (paste universe) |
| `use_screener` | `False` | `pipeline.py:97` | BO Scan (True = snapshot sweep) |
| `apply_gates` | `True` | `pipeline.py:98` | Scan |
| `output_root` | `Path("output")` | `pipeline.py:99` | Run |
| `min_rating` | `4` | `pipeline.py:100` | Rating/Report |
| `pipeline_type` | `"daily_ep_scan"` | `pipeline.py:101` | Run dispatch |
| `bo_profile` | `"best"` | `pipeline.py:102` | BO Scan (funnel profile) |

### EP Scan — Baseline/Strict gates (`scanners/ep/gates.py`, schema `models/ep.py:24-33`)

| Variable | Default | Defined at |
|---|---|---|
| `BASELINE.min_price` | `1.0` | `ep/gates.py:6` |
| `BASELINE.min_gap_pct` | `4.0` | `ep/gates.py:7` |
| `BASELINE.min_rvol10` | `1.5` | `ep/gates.py:8` |
| `STRICT.min_price` | `10.0` | `ep/gates.py:12` |
| `STRICT.min_gap_pct` | `8.0` | `ep/gates.py:13` |
| `STRICT.min_rvol10` | `3.0` | `ep/gates.py:14` |
| `STRICT.min_market_cap` | `$300M` | `ep/gates.py:15` |
| `STRICT.max_market_cap` | `$10B` | `ep/gates.py:16` |
| `STRICT.min_avg_dollar_volume_50d` | `$5M` | `ep/gates.py:17` |
| `STRICT.min_event_dollar_volume` | `$20M` | `ep/gates.py:18` |

### EP Catalyst / Rating (Agents 2–3)

| Variable | Default | Defined at |
|---|---|---|
| Catalyst Tavily `max_results` | `3` | `agents/catalyst.py:185` |
| Rating Tavily `max_results` (re-fetch) | `5` | `agents/rating.py:194` |
| Hard cap: no catalyst/`UNKNOWN` | `2` | `rating.py:61-62` |
| Hard cap: `PR` | `3` | `rating.py:63-64` |
| Hard cap: `CONTRACT`/`FDA` | `4` | `rating.py:65-66` |
| Hard cap: `rvol10 < 3.0` | `4` | `rating.py:67-68` |
| EP catalyst match threshold | `>= 4` | `rating.py:146` |

### VCP Scan — gates + structural rubric (`scanners/vcp/gates.py`, `scanners/vcp/metrics.py`)

| Variable | Default | Defined at |
|---|---|---|
| `MIN_ADV_DOLLAR` (liquidity) | `$10M` | `vcp/gates.py:7` |
| ADV$ window | `60` | `vcp/gates.py:17,32` |
| `MIN_MARKET_CAP` | `$300M` | `vcp/gates.py:55` |
| Stage 2 RS floor | `70.0` | `vcp/gates.py:45`, `metrics.py:80` |
| Structural gate floor | `>= 4` | `vcp/gates.py:50` |
| RS ≥85 + proximity ≥90 → 5★ | `85.0`, `90.0` | `metrics.py:251` |
| RS ≥70 + proximity ≥80 → 4★ | `70.0`, `80.0` | `metrics.py:253` |
| SMA windows | `50/150/200/252` | `metrics.py:62-66` |
| Contraction count k 5★/4★ | `3..4` / `2 or 5` | `metrics.py:262,264` |
| Trough higher-low factor | `1.001` | `metrics.py:286` |
| Descending-triangle ratio | `0.95` | `metrics.py:309` |
| Minor-slope ratio | `0.99` | `metrics.py:311` |
| Dollar-range shrink | `0.75` | `metrics.py:332` |
| Depth shrink | `0.75` | `metrics.py:353` |
| Tight-closes days | `4` | `metrics.py:216` |
| Tight span/CV 5★ / 4★ | `1.25/0.8` / `2.0/1.5` | `metrics.py:367,369` |
| Volume decay/wave | `15.0%` | `metrics.py:389` |
| Pivot vol vs SMA20 window | `20` | `metrics.py:394-396` |
| Time-contraction ratio | `1.2` | `metrics.py:417` |
| Eternal-base factor | `3` | `metrics.py:421` |
| Min bars / SPY min bars | `200` / `50` | `metrics.py:446,448` |
| Swing-point window | `10` | `metrics.py:100` |
| ≥5 params at 4+ → 4★ | `5` | `metrics.py:492` |
| ≥6 × 5★ → 5★; ≥3×5★ or ≥5×4★ → 4★ | `6`, `3`, `5` | `metrics.py:496,498` |

### VCP/BO Report — down-only caps (`vcp/gates.py:77-115`, reused `bo/gates.py:38`)

5★ → 4★ if not leader or `DECLINING_GROUP`; 4★ → 3★ if `DECLINING_GROUP`; 3★ stays 3★.

### BO Scan (`scanners/bo/metrics.py`, `scanners/bo/gates.py`)

| Variable | Default | Defined at |
|---|---|---|
| `MIN_IMPULSE_PCT` | `30.0` | `bo/metrics.py:29` |
| `ADR_LO` / `ADR_HI` | `4.0` / `12.0` | `bo/metrics.py:30`; dup `bo/gates.py:14-15` |
| `BASE_MIN_DAYS` / `BASE_MAX_DAYS` | `5` / `40` | `bo/metrics.py:31` |
| `VCI_MAX` | `0.65` | `bo/metrics.py:32` |
| `SURFING_MAX_PCT` | `8.0` | `bo/metrics.py:33` |
| `SURGE_MIN` / `SURGE_STRONG` / `SURGE_TEXTBOOK` | `1.5` / `2.0` / `3.0` | `bo/metrics.py:34-37` |
| `DRYUP_MAX` | `0.5` | `bo/metrics.py:35` |
| `MIN_BARS` | `90` | `bo/metrics.py:38` |
| Prior-impulse window | `(20, 63)` | `bo/metrics.py:52` |
| Narrow 3-day factor | `0.6` × ADR20 | `bo/metrics.py:119` |
| KDE bandwidth / upper-quartile | `0.03` / `0.75` | `bo/metrics.py:170,198` |
| Higher-lows min `S_HL` | `1` | `bo/metrics.py:315,481` |
| RS boost threshold | `85.0` | `bo/metrics.py:510` |
| Extension clamp | surfing > `8.0` | `bo/metrics.py:478` |
| Legacy `passes_bo_gate` | `>= 4` | `bo/gates.py:25` |
| Near-miss threshold | `7` | `bo/metrics.py:568` |
| Sweep prefilter price / dollar-vol / mcap | `$10` / `$10M` / `$300M` | `data/polygon.py:326,327,351` |

### BO Funnel (`scanners/bo/watchlist.py`)

| Variable | Default | Defined at |
|---|---|---|
| `best` profile | `adv=50M, ema=5, base=40` | `watchlist.py:23` |
| `moderate-lose` profile | `adv=50M, ema=8, base=40` | `watchlist.py:24` |
| `widen` profile | `adv=30M, ema=8, base=40` | `watchlist.py:25` |
| Q_base 5★/4★/3★ floors | `90` / `75` / `60` | `watchlist.py:62,64,66` |
| Gap-options prompt threshold | tradable `< 5` | `interactive.py:171` |

### VCP/BO Enrich (`agents/enrichment.py`)

Tavily Query 1 (taxonomy) `max_results=5` (`enrichment.py:82`); Query 2 (leadership) `max_results=5` (`enrichment.py:95`).

### Gotchas for the editor

- `MIN_ADV_DOLLAR` and `MIN_MARKET_CAP` are single shared constants re-exported by BO and used by the Polygon sweep — editing affects VCP and BO together.
- `ADR_LO`/`ADR_HI` duplicated in `bo/gates.py` and `bo/metrics.py`.
- `DRYUP_MAX=0.5` is a hard essential; the funnel `dryup` profile value is `0.0` (scoring-only in all three profiles).
- `bo_profile` is the only `RunConfig` field mapping 1:1 to a `WATCHLIST_PROFILES` key.
- `min_rating=4` is the default report filter across all three families.
