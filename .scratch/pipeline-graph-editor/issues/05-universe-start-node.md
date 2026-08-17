> **SUPERSEDED — re-scoped.** The Universe-as-start-node decision survives as-is (auto-seeded once, runtime-bound, not in the palette). Family-specific framing is superseded.

Type: grilling
Status: resolved

## Question

How is the Universe start node represented on the canvas? Options: (a) an unbound placeholder node that is a Phase with a Universe Port, wired by the user; (b) Universe is not on the canvas at all — it stays on the New Scan form and the graph begins at the first Scan.

## Answer

Universe is a canvas **start node** (option a). It is an n8n-style trigger Phase with a single output Port (`out` → `SymbolKey` set), fanned out to one or more Scan Phase 1 nodes (EP/VCP/BO/Custom). This is consistent with the already-locked fan-out + "add another Phase 1" decisions: mixing families is expressed by fanning Universe out to multiple Phase 1 nodes.

The Universe node is **runtime-bound**: the Pipeline Definition stores the node and its outgoing edges, but the Run binds the symbol source (paste / market-wide sweep / Force Include) at launch. The Universe node itself carries no ticker variables in the Definition.
