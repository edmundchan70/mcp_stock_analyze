# Premarket grep — Feature Definitions (grilling, RESOLVED)

Status: **RESOLVED** (grilling rounds 1–3, user confirmed; universe default contingent on research 03, now resolved). Blocks: 05-premarket-build-task.

## Confirmed decisions

- **Family**: `premarket`. No variant.
- **Timing**: manual-triggered from the flow UI (~9:00–9:15 ET); no server scheduler.
- **Single-call**: one full-market Polygon snapshot at run time.
- **Filter**: current premarket % change vs prior close ≥ `premarket_min_change_pct` (default 5.0, editable).
- **Universe default** (research-resolved): **sweep-first + paste + survivor cap** — snapshot → change%-prefilter → cap survivors to `premarket_cap` (default 300, ranked by change% desc) → plus pasted symbols. Paste-only is NOT used because the snapshot day bar includes premarket from 4am ET, so a 1-call sweep is both accurate and cheap.
- **Optional must-notice volume flag**: `premarket_min_vol_adv` × 20d ADV (0 = off). Survivors with `premarket_volume ≥ min × ADV` are flagged; flag is informational.
- **Columns**: symbol, name, premarket % change, price, premarket volume, sector (`sic_description`), strength tier (5 ≥ +10%, 4 ≥ +7.5%, 3 ≥ +5%).
- **AI Search**: omitted. Flow stepper 1→2→3→5; Report runs `Universe → Scanner → Report`.

## Out of scope
- Premarket tracked-window (8:45–9:00) semantics — single-call snapshot only.
- Server-side scheduling.
- Sector via anything other than Polygon `sic_description`.
