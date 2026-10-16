# Research: Pipeline Directed Graph View

Decisions reflect the approved design in `docs/design/pipeline-monitor-graph-update` (`DESIGN_NOTES.md` §8).

## 1. Where do the relationships come from?
- **Decision**: edges from `expected_steps[].inputs[].from` in `/api/config`; groups from `group`.
- **Rationale**: already served; stored records only carry input names (`call_statistics` is produced by merge but named differently).
- **Alternatives**: infer from names (fragile); new endpoint (unneeded).

## 2. Edge count semantics
- **Decision**: edge count = the consumer's recorded input value; the node shows the producer's own output.
- **Rationale**: matches stored data exactly (SC-002) and keeps a producer/consumer mismatch visible.

## 3. Layout
- **Decision**: fixed hand-tuned table (design §8.3), keyed by step name: columns account 0, call 1, partners 0, instances 1, campaigns 2, clickview 2, merge 3, record 4, save 4; rows 0, 0, 1.5, 1.5, 1, 2, 1, 0.5, 1.5. Zero crossings. The calls → merge skip edge runs straight through the empty row 0 of column 2 and bends in the last gap. Merge's three inputs enter at 1/4, 2/4, 3/4 of its height. Group bands behind nodes.
- **Rationale**: the shape is fixed, so a table is simpler and visually better than auto-layout and is what was approved.
- **Alternatives**: longest-path layering (superseded; same columns but worse routing control); dagre/elkjs (dependency); force layout.
- **Unknown steps**: not in the table, so they go in an "Other steps" row below the graph (spec FR-012).

## 4. Rendering
- **Decision**: absolutely-positioned HTML `<button>` nodes and chips over one `aria-hidden` SVG (bands, edge hit/line/flow paths, arrowhead paths). Whole box scaled with `transform: scale(s)` and a stage that reserves `H × s`. Arrowheads are paths, not markers, so colour follows state.
- **Rationale**: real focus and text for nodes; SVG only for lines.

## 5. Responsive
- **Decision**: by panel inner width: ≥880 desktop LR; 600–879 compact LR (no chips, no mono name or time; tooltip carries labels); <600 top-to-bottom in 2 lanes with the calls → merge edge in a left gutter. Phone chosen over a scroll panel because scrolling hides half the graph and the merge point.
- **Rationale**: no horizontal page scroll at 375 px (spec FR-009).

## 6. Accessibility and interaction
- **Decision**: nodes have a full `aria-label` and `aria-pressed`; tab order column by column; tooltips on hover and focus; Esc handled in the capture phase; reduced motion hides `.gedge__flow`; flow animation also off while selecting. Arrow-key focus movement is not part of the design and is not built.

## 7. View preference
- **Decision**: `localStorage['pm-steps-view']` (`list|graph`), try/catch, default **graph**.
- **Rationale**: the feature's purpose; the prototype defaulted to list, noted as a deviation.

## 8. Porting the reference code
- **Decision**: the reference `graph.js` is a global IIFE using `window.PM`. Port to ES modules: pure state, width, picker and neighbour logic to `graph-model.js` (importing `isLoss` from `model.js`), rendering and wiring to `views/graph.js` (importing icons and `fmt`/`hhmmss`).
- **Rationale**: matches the existing module structure and makes the rules unit-testable.
