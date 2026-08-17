> **SUPERSEDED — re-scoped.** The family-specific port model described here (EP Scan / VCP Enrich as distinct node types) is superseded by the component model. Facts remain useful for tickets 12/14–17.

Type: research
Status: resolved

## Question

Document the input/output data shape of every Phase, so the spec can name typed Ports and the merge-by-SymbolKey product. For each Phase (Universe start, EP Scan, EP Catalyst, EP Rating, VCP Scan, VCP Enrich, VCP Report, BO Scan, BO Enrich, BO Report), name the Pydantic model(s) it consumes and produces with `file:line`, and note the shared models (VCP/BO reuse `agents/enrichment.py` and `apply_vcp_caps`).

## Answer

All paths relative to `mcp_stock_analyze/`.

### Phase → model table

| Phase | Input | Output | file:line |
|---|---|---|---|
| **Universe start** | paste `str` or Polygon snapshot | `list[SymbolKey]` (`(symbol, exchange)`); paste envelope `ForceIncludeParseResult` | `data/symbols.py:7`, `force_include.py:36,72`, `pipeline.py:96` |
| **EP Scan** | raw row dicts (`to_ep_row`/`merge_force_rows`) | `EpScanResult` ⊃ `StockBucket` ⊃ `EpStock` (+ `GateThresholds`) | `scanners/ep/runner.py:17,52`, `models/ep.py:41/36/9/24` |
| **EP Catalyst** | `EpStock` | `CatalystBucket` ⊃ `CatalystEnrichedStock` (internal `CatalystSummary`) | `agents/catalyst.py:79`, `models/catalyst.py:22/40/11` |
| **EP Rating** | `CatalystEnrichedStock` | `RatedBucket` ⊃ `EpRatedStock` (internal `EpRatingProposal`) | `agents/rating.py:73`, `models/rating.py:30/52/22` |
| **VCP Scan** | force rows + OHLCV `DataFrame` + SPY | `VcpScanBucket` ⊃ `VcpStructuralRating` ⊃ `VcpContraction` | `scanners/vcp/runner.py:61,70`, `models/vcp.py:150/21/9` |
| **VCP Enrich** | `VcpStructuralRating` | `VcpEnrichedBucket` ⊃ `VcpContextEnrichment` | `agents/enrichment.py:248`, `models/vcp.py:65/164` |
| **VCP Report** | `VcpStructuralRating` + `VcpContextEnrichment` → `apply_vcp_caps` | `VcpRatedBucket` ⊃ `VcpRatedStock` | `pipeline.py:482`, `scanners/vcp/gates.py:118,77`, `models/vcp.py:108/171` |
| **BO Scan** | force/snapshot rows + OHLCV + SPY | `BoScanBucket` ⊃ `BoSetupRating` (+ `BoNearMiss`; internal `BoBase`) | `scanners/bo/runner.py:63,72`, `models/bo.py:120/34/91/11` |
| **BO Enrich** | `BoSetupRating` → `enrich_with_vcp_context` | `BoEnrichedBucket` ⊃ `VcpContextEnrichment` | `agents/enrichment.py:248`, `pipeline.py:532`, `models/bo.py:135` |
| **BO Report** | `BoSetupRating` + `VcpContextEnrichment` → `apply_vcp_caps` | `BoRatedBucket` ⊃ `BoRatedStock` | `pipeline.py:532`, `scanners/bo/gates.py:28`, `models/bo.py:142/176` |

### Raw-shape notes

- **EP Scan** consumes raw dicts, normalized to `EpStock` in `normalize_row` (`scanners/ep/metrics.py:27,87`).
- **VCP/BO Scan** consume raw dicts + `pandas.DataFrame` OHLCV + SPY; Pydantic ratings are produced internally by `score_vcp` / `score_bo_setup`.
- **BO Enrich** type-hints `VcpStructuralRating` but at runtime receives BO rating dicts (`pipeline.py:825`); only `symbol`/`exchange` are read (`enrichment.py:297-302`).
- **Universe** output is not Pydantic: `list[SymbolKey]` on `RunConfig.force_keys`; paste path also emits `ForceIncludeParseResult` with `symbols`/`rejected`/`errors`.

### Shared models

- `VcpContextEnrichment` (`models/vcp.py:65`) shared by VCP Enrich and BO Enrich (`models/bo.py:8,139`).
- `apply_vcp_caps` (`scanners/vcp/gates.py:77`) shared by VCP Report (`gates.py:118`) and BO Report (`bo/gates.py:28`); BO applies caps to `funnel_stars`.
- `IndustryGroupStrengthFlag` (`models/vcp.py:62`) shared by both rated-stock models.
- `passes_liquidity_gate`/`MIN_ADV_DOLLAR` and `passes_market_cap_gate`/`MIN_MARKET_CAP` (`vcp/gates.py:29,7,58,55`) reused by BO Scan and VCP Scan.
- Tavily + OpenRouter shared by EP Catalyst (`catalyst.py:171,205`), EP Rating (`rating.py:180,214`), VCP/BO Enrich dual-query (`enrichment.py:62,118`), and Force Include parse (`force_include.py:133`).
- `SymbolKey`/`row_symbol_key` (`data/symbols.py:7,25`) is the shared identity type for dedup/merge across all three scan runners.

### Implication for Ports

The natural typed Port groups are: **Universe → SymbolKey set**; **Scan → family bucket** (EP `StockBucket`, VCP `VcpScanBucket`, BO `BoScanBucket`); **Enrich → `VcpContextEnrichment` list** (shared by VCP and BO, distinct from EP's `CatalystBucket`); **Rate/Report → family rated bucket** (`RatedBucket` / `VcpRatedBucket` / `BoRatedBucket`). The lane-merge product keys on `SymbolKey`; a generic lane summary needs at minimum `symbol`, `exchange`, family/source tag, and a rating/score if present.
