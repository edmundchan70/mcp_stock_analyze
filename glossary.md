# Glossary

Domain terms for the stock analyze scanners. Prefer these names in code, JSON keys' conceptual meaning, and docs.

| Term | Meaning |
|------|---------|
| **Episodic Pivot** | Gap-up momentum setup (Stockbee / Kullamägi) driven by a shock and abnormal volume. |
| **Baseline Gate** | Looser technical thresholds (price ≥ $1, gap ≥ 4%, RVOL10 ≥ 1.5×). |
| **Strict Gate** | Institutional thresholds (price ≥ $10, mcap $300M–$10B, 50d ADV$ ≥ $5M, gap ≥ 8%, RVOL10 ≥ 3×, event-day $ vol ≥ $20M). |
| **Gap %** | `(open − prior close) / prior close` for the regular session. |
| **RVOL10** | `volume / 10-day average volume`. |
| **Event Day Dollar Volume** | Dollars traded on the gap day. |
| **Average Daily Dollar Volume** | Typical daily dollars traded over ~50 days (pre-gap liquidity). Screener uses TradingView `AvgValue.Traded_60d` as the nearest bulk field. |
| **Force Include** | Pasted symbol (LLM-cleaned). On confirm may be the sole Universe (screener skipped); Skip leaves screener workflow unchanged. |
| **Universe** | Symbols in one scan: screener-only, paste-only (`universe_source=force`), or hybrid. |
| **Apply Gate filter** | Fetch metrics, apply Baseline/Strict; only survivors continue. Auto always; Manual choice after paste. |
| **Run all pasted** | Manual-only: fetch metrics for all pasted names, skip gates, continue all to Catalyst. |
| **Catalyst** | News-backed fundamental driver behind the gap; absence recorded as `catalyst_found=false`. |
| **Catalyst Type** | `EARNINGS \| GUIDANCE \| CONTRACT \| FDA \| PR \| UNKNOWN` (`PR` = residual material company news). |
| **EP Rating** | 1–5 how well news matches a textbook EP. See rubric below. |
| **EP Catalyst Match** | `ep_rating >= 4` — default names to chart manually. |
| **Trade Opportunity Auto-Detect** | **v2 (deferred):** OHLCV pivot/base setup detection. Not in v1. |
| **Daily Run** | One stamped execution of the configured agent chain. |
| **Auto Run** | Wizard: Pipeline → Force Include → Gate → name. Paste skips screener and always applies Gate. |
| **Manual Run** | Wizard: Force Include first; paste offers Apply Gate vs Run all, then Catalyst / Analysis / name. |
| **Pipeline Type** | Scan family for a Daily Run; v1 only `daily_ep_scan`. |
| **Analysis Method** | Post-Catalyst scoring; v1 only EP Rating. |
| **Run Artifact** | Stamped `{name}_agentN.json` under `output/<date>/<time>_<name>/`. |

### EP Rating rubric (v1)

| Stars | Label | Meaning |
|------:|--------|---------|
| 5 | `textbook` | Must look — clear **EARNINGS/GUIDANCE** shock + strong volume (`rvol10` typically ≫ 3×). |
| 4 | `acceptable` | Worth charting if setup looks great — real fundamental catalyst (earnings/guidance/strong contract/FDA). |
| 3 | `better_not` | Catalyst exists but weak/vague for a classic EP (e.g. thin PR). |
| 2 | `no` | News does not support an EP. |
| 1 | `bs` | No credible catalyst / garbage / soft-fail. |

**Hard caps (code, down-only):** `UNKNOWN`/`catalyst_found=false` → max 2; `rvol10 < 3` → max 4; `PR` → max 3; `CONTRACT`/`FDA` → max 4; soft-fail → 1. **5★ reserved for EARNINGS/GUIDANCE.**

See [CONTEXT.md](CONTEXT.md) for full definitions and avoided synonyms.
