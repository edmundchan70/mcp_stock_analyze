# BO Pre-Market Watchlist — Validation Spike Report

**Date:** 2026-08-11  
**Universe:** 57 symbols from `output/2026-08-10/134135_daily_deepvue_qullamaggie_6month/` (daily_bo_scan Agent 1 artifact)  
**Spike script:** `spike_watchlist.py`
**Distribution analysis:** `spike_distributions.py`

---

## Executive Summary

**Verdict: HALT — the 5-gatekeeper funnel is too narrow.** With plan-default thresholds, only **1 candidate** (ACHV, 3★ Q_base=71) survives. Even with all thresholds relaxed to their maximums, only **2 candidates** pass. The core promise of 5–15 nightly candidates is not met.

## Funnel Results

### Gatekeeper pass/fail (57 symbols, plan defaults)

| # | Gatekeeper | Pass | Fail | Pass % |
|---|---|---|---|---|
| G1 | Prior Impulse ≥ 30% | 57 | 0 | 100% |
| G2 | 20d ADV$ ≥ $50M | 35 | 22 | 61.4% |
| G3 | |Close-EMA10| ≤ 3.5% + EMA10 rising | 15 | 42 | 26.3% |
| G4 | Valid Base 5–30d | 25 | 32 | 43.9% |
| G5 | Vol[T-1] ≤ 0.5 × SMA20(vol) | 5 | 52 | 8.8% |
| **ALL 5 PASS** | | **1** | — | **1.8%** |

### Tuning attempts (all configs ≤ 2 candidates)

| Config | ADV$ | EMA10 | Dryup | Base | ALL pass |
|---|---|---|---|---|---|
| STRICT (plan defaults) | $50M | 3.5% | 0.50x | 30d | **1** |
| TUNED A: EMA10=4% | $50M | 4.0% | 0.50x | 30d | 1 |
| TUNED B: Dryup=0.6x | $50M | 3.5% | 0.60x | 30d | **2** |
| TUNED C: ADV=$30M | $30M | 3.5% | 0.50x | 30d | 1 |
| TUNED D: Base=40d | $50M | 3.5% | 0.50x | 40d | 1 |
| TUNED E: EMA10=4% + Dryup=0.6x | $50M | 4.0% | 0.60x | 30d | **2** |
| TUNED F: All relaxed | $30M | 4.0% | 0.60x | 40d | **2** |

Only 2 candidates ever pass: **ACHV** (Q_base=71, 3★) and **PENG** (Q_base=51, 0★).

## Root Cause: Metric Distributions

### G5 — Volume Dry-Up (CRITICAL bottleneck)

| Metric | Min | Median | Max |
|---|---|---|---|
| Vol[T-1] / SMA20(vol) | 0.17x | **0.91x** | 31.6x |

| Threshold | Passing | % |
|---|---|---|
| ≤ 0.30x | 2 | 4% |
| ≤ 0.40x | 3 | 5% |
| ≤ 0.50x | 5 | 9% |
| ≤ 0.60x | 6 | 11% |
| ≤ 0.75x | 17 | 30% |
| ≤ 1.00x | 34 | 60% |

**Finding:** The median stock in this universe trades at **91% of its 20-day average volume** on the last bar. Only 9% are below 50%. A 0.50x dry-up threshold is incompatible with the natural volume distribution of momentum stocks, which typically have elevated volume near breakouts (the original `daily_bo_scan` already confirmed these had volume surges).

### G3 — EMA10 Proximity (MAJOR bottleneck)

| Metric | Min | Median | Max |
|---|---|---|---|
| |Close-EMA10|% | 0.19% | **4.99%** | 39.15% |

| Threshold | Passing | % |
|---|---|---|
| ≤ 1.5% | 9 | 16% |
| ≤ 2.5% | 15 | 26% |
| ≤ 3.5% | 19 | 33% |
| ≤ 5.0% | 29 | 51% |
| ≤ 8.0% (current) | 38 | 67% |

**Finding:** The median stock is 5% away from its EMA10. The 3.5% threshold eliminates 67% of the universe. Compared to the existing 8% surfing threshold in `daily_bo_scan`, this is 2.3x stricter.

### G2 — 20d ADV$ (moderate)

| Metric | Min | Median | Max |
|---|---|---|---|
| 20d ADV$ | $3.2M | **$76.2M** | $14.9B |

| Threshold | Passing | % |
|---|---|---|
| ≥ $10M (current) | 53 | 93% |
| ≥ $30M | 42 | 74% |
| ≥ $50M | 35 | 61% |

**Finding:** $50M floor is aggressive for a watchlist but workable. Existing $10M floor passes 93%.

### G4 — Base Duration (threshold-adjustable)

| Metric | Min | Median | Max |
|---|---|---|---|
| Base days | 0d | **32d** | 40d |

| Threshold | Passing | % |
|---|---|---|
| ≤ 30d | 28 | 49% |
| ≤ 40d (current) | 57 | 100% |

**Finding:** 30d cap cuts the universe in half. The existing 40d threshold passes everyone because `detect_bases` already enforces ≤ 40d.

---

## Proposed Relaxation Strategies

### Strategy A: Keep volume dry-up as scoring only (recommended)

The plan already says "volume-surge check moves from pre-market filter to execution event." Extend this philosophy to dry-up: make it a Q_base scoring component (10 pts in the rubric) but NOT a hard reject. This alone would take the funnel from 1 → ~6-8 candidates.

**Changes:**
- Drop G5 as a hard reject gatekeeper
- Keep dry-up as a 10-point scoring component in Q_base (already designed)
- Volume[T-1] still influences score and ranking

**Impact:** Approx 6-10 candidates (G1=57 × G2=35 × G3=19-29 × G4=28-57 / 57 = varies)

### Strategy B: Relax EMA10 to 5.0% envelope

The 3.5% threshold is too tight. The median stock is at 5%. Moving to 5% doubles the G3 pass rate from ~19 to ~29.

**Changes:**
- EMA10 proximity: 3.5% → **5.0%**
- Keep EMA10 rising requirement
- Keep absolute-value check (below EMA10 is also rejected — deliberate for pre-breakout bases)

### Strategy C: Use existing 8% surfing threshold

Reuse the existing `SURFING_MAX_PCT = 8.0` from `metrics.py` instead of the new 3.5%. This is consistent with the existing BO scanner and passes 67% of the universe.

### Strategy D: Relax base to 40d (reuse existing)

The 30d cap is arbitrary — `detect_bases` already limits to 40d. Using the existing 40d limit would pass 100% of bases detected.

### Strategy E: Multi-tier gatekeeper CLI (user-driven tuning)

Instead of hard-coded thresholds, expose a CLI that lets users choose their risk tolerance profile:

```
python -m stock_analyze bo-watchlist --profile conservative|moderate|aggressive
```

| Parameter | Conservative | Moderate | Aggressive |
|---|---|---|---|
| ADV$ floor | $50M | $30M | $10M |
| EMA10 proximity | 3.5% | 5.0% | 8.0% |
| Base max duration | 30d | 40d | 40d |
| Dry-up hard reject | Yes (0.50x) | Scoring only | Scoring only |

---

## Recommended Path Forward

1. **Drop G5 (volume dry-up) as a hard reject** — keep it as a 10-point Q_base scoring component. The plan already says volume-surge is an execution event, not a pre-market filter. Same logic applies to dry-up.

2. **Relax G3 (EMA10) to 5.0%** — matches the median stock. The current 3.5% is 2.3x stricter than the existing surfing threshold.

3. **Relax G4 (base) to 40d** — `detect_bases` already enforces this limit.

4. **Keep G2 (ADV$) at $50M** — acceptable 61% pass rate, filters micro-caps.

5. **Expose a `--profile` CLI flag** for user-driven tuning in a follow-up feature plan.

**Expected funnel with these changes:** ~8–12 candidates, meeting the 5–15 target.

### Verified: Moderate Profile Results

Running `python spike_watchlist.py --profile moderate` (ADV=$50M, EMA=5.0%, Dryup=OFF, Base=40d) on the 57-symbol universe:

| Gatekeeper | Pass | Fail | % |
|---|---|---|---|
| G1: Impulse >= 30% | 57 | 0 | 100% |
| G2: ADV$ >= $50M | 35 | 22 | 61.4% |
| G3: EMA10 <= 5% + rising | 19 | 38 | 33.3% |
| G4: Base 5-40d | 54 | 3 | 94.7% |
| G5: Dry-up | — | — | *disabled* |
| **ALL PASS** | **11** | — | **19.3%** |

**Candidates after 3-star floor:** 5 tradable (ACHV=65, DELL=65, FBRX=65, BB=63, MANE=60). Meets the 5-15 target.

---

## Spike Scripts (kept for future use)

- `spike_watchlist.py` — gatekeeper funnel tool with `--profile` (conservative/moderate/aggressive) and individual `--adv --ema --dryup --base` args
- `spike_watchlist_result.json` — last run results
