# EP Technical Test + Scanner UI — Spec Map

## Destination

A spec-plus-build for the **EP Technical Setup Test** — the v2 of the glossary's deferred "Trade Opportunity Auto-Detect". The EP scanner gets a pure-math technical layer (no LLM) computing 5 boolean setup features from OHLCV; with the feature-toggle active, a stock survives when ≥1 **enabled** feature holds, and the Baseline/Strict gates become informational-only. The scanner results table is redesigned TradingView-screener-style (sortable feature columns, filter-rail toggles, K/M/B number formatting everywhere).

## Notes

- Domain: the `stock_analyze` EP pipeline (`scanners/ep/`, `models/ep.py`, `pipeline.py:163`), the tool registry (`tools/variables.py`, `tools/builtins.py`), and the guided flow Scanner phase (`web/components/flow/ScannerPhase.tsx`).
- Skills: `/grilling` (ticket 01), `/research`, `/task`, `frontend-design`.
- Tracker: local markdown (`.scratch/ep-scan-enhancement/`), matching the `.scratch/pipeline-graph-editor/` precedent.
- Already-settled decisions (grilling rounds 1–3, user confirmed):
  - **Gate semantics**: toggle ON → EP survivors = stocks with ≥1 enabled feature held; Baseline/Strict still computed and displayed but never filter.
  - **Toggle UX**: Scanner filter rail gets a dedicated **EP Technical Test** section — master on/off at the section header + 5 per-feature toggles, each independently toggleable, each with editable thresholds inline.
  - **All-features-off**: section active but every feature off → fall back to Baseline/Strict gates (today's behavior).
  - **Event window**: scan backward — event day = highest-RVOL10 bar in the last 63 bars; features score the post-event setup.
  - **VWAP anchor**: anchored VWAP from the event day first; if no support shown there, fall back to a higher-high pivot anchor; display whichever shows support.
  - **Base structure**: pivot (base highest high) + ascending swing highs with higher low + volume contrast (pullback ≤ 0.5× event volume, up-leg ≥ 1.5× pullback avg), base 5–40d after event.
  - **Master toggle default**: ON for EP.
  - **Thresholds**: editable scanner vars (spike ×, pullback vol ratio, EMA touch %, VWAP touch %, base min/max days).
  - **Formatting scope**: global K/M/B across every numeric column.

## Frontier (open tickets)

- [Feature definitions + thresholds (grilling)](issues/01-feature-definitions-grilling.md) — the proposed per-feature math for user confirmation.
- [score_ep_setup + EpSetupFeatures (task)](issues/02-ep-setup-detection-task.md) — pure-math feature layer + model + unit tests.
- [Scan wiring + scanner vars (task)](issues/03-scan-wiring-task.md) — OHLCV pass-through, keep-if-any, SCANNER_VARS, scanner callable.
- [Scanner UI redesign + M/K formatting (task)](issues/04-scanner-ui-task.md) — filter primitives, EP Technical Test section, run button, dense table, fmtCompact.

## Out of scope

- Changing `FlowState` / run semantics (UI is presentation-only).
- LLM involvement in the technical layer.
- The component-graph editor (superseded by the guided flow).
