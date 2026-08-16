> **SUPERSEDED — re-scoped.** Decided on the old family-specific model. The skip-enrich *concept* survives (Report accepts scan/filtered/enriched rows without context), but port-shape details are superseded by the component model.

Type: grilling
Status: resolved

## Question

Is a Scan → Rate/Report wire legal (skipping the Enrich/Catalyst Phase), mirroring today's `run_catalyst=false`? Decide whether Enrich is optional on a family path, and what "skip" means for the final rating/report output.

## Answer

Scan → Rate/Report is a legal direct wire in all three families. Enrich/Catalyst is optional on a family path; a lane may also simply end at Scan (terminal — inherent to a DAG).

1. **Scan → Rate/Report is legal in all families.** Enrich/Catalyst is optional on a family path.
2. **EP is unaffected by optional-context**: EP Rating re-fetches news itself (`agents/rating.py:194`), so EP Scan → EP Rating is a normal direct wire on its existing structural input; EP Catalyst is additive only.
3. **VCP/BO Report gets a required structural port + an optional context port.** Skip-enrich = context port left unconnected → `final_rating = structural (VCP) / funnel_stars (BO)`, `cap_applied=false`, `cap_reason="no_enrichment"`, context fields null.
4. **General rule**: a Port is `required` or `optional`; an optional port may simply be unconnected.

### Code evidence

- Today `run_catalyst=false` is *not* "skip Enrich and still rate" — it early-returns right after Agent 1 (Scan) in all three families: `pipeline.py:658` (VCP), `pipeline.py:810` (BO), `pipeline.py:1002` (EP). It writes `agent1.json` then returns with no rating/report at all.
- VCP/BO Report is not a standalone Phase today — it is fused inside `execute_vcp_enrichment` / `execute_bo_enrichment`, which return `{agent2, agent3, rated_stocks}` in one step. The DAG walker must factor Report out into its own Phase (see map "Not yet specified").
- The rated-stock models already carry the skip-enrich fields: `VcpRatedStock`/`BoRatedStock` have `final_rating`, `cap_applied`, `cap_reason`, plus null-able context fields (per ticket 02).
