# Polygon premarket data verification (research, RESOLVED)

Status: **RESOLVED**. Unblocks: 05-premarket-build-task universe default; 04-zhao-build-task realtime data path.

## Question
Does the Polygon snapshot `day` bar include premarket activity? What is the real cost of a market-wide premarket grep?

## Findings (from Polygon.io docs + API semantics)

1. **Snapshot `day` bar includes premarket.** Polygon's aggregate `day` bar accumulates from 4:00 AM ET (extended-hours-open). During premarket hours, `day.c`/`day.v` already reflect premarket trading, and `todaysChangePerc` (snapshot `todaysChangePerc` field) is computed vs the prior regular-session close. Therefore **during premarket, `todaysChangePerc` ≈ premarket % change** and `day.v` ≈ premarket cumulative volume.
2. **One call covers the whole market.** `GET /v2/snapshot/locale/us/markets/stocks/tickers` (with `include_otc=false`, `apiKey`) returns all ~10k listed stocks in one call. Cost of a market-wide premarket grep = **1 snapshot call + optional 20d ADV for the volume flag**.
3. **No separate premarket endpoint is needed.** The `/v2/aggs` `premarket` timespan/`session` params exist but are unnecessary for a current-moment sweep. A `previousClose` is present on the snapshot for change% reference.

## Implications locked in

- Universe default for premarket = **sweep-first + paste + survivor cap** (snapshot → change%-prefilter → cap `premarket_cap` → union pasted symbols). This is both accurate (day bar includes premarket) and cheap (1 call).
- `change_pct` in `stock_analyze/data/polygon.py` `fetch_market_snapshot` (`:274`) can be used directly as premarket % change intraday.
- Zhao realtime uses the same snapshot's `change_pct` as "stock today%" (banner + rule).

## Caveats
- Timing: the semantic "premarket % change" only holds while premarket is the most recent session (≈4:00–9:30 ET). If a run happens after open, the filter is just today's change — acceptable, user runs premarket ~9:00–9:15.
- 20d ADV requires a second batched OHLCV call for flagged survivors only (cap ≤ 300 → cheap).
