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
| **Force Include** | CSV-supplied symbol always evaluated alongside the screener universe. |
| **Universe** | Screener symbols merged with force includes for one scan. |
| **Catalyst** | News-backed fundamental driver behind the gap; absence recorded as `catalyst_found=false`. |
| **Catalyst Type** | `EARNINGS \| GUIDANCE \| CONTRACT \| FDA \| PR \| UNKNOWN` (`PR` = residual material company news). |

See [CONTEXT.md](CONTEXT.md) for full definitions and avoided synonyms.
