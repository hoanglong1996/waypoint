# Contract: Graph View UI

No new HTTP endpoints. Consumes `/api/config` (`expected_steps[].group`, `.inputs[].from`) and `/api/runs` unchanged. Visual source: `docs/design/pipeline-monitor-graph-update`.

## Pure functions (`static/js/graph-model.js`)
- `edgesOf(steps)` (cfg steps) -> `[{from, to, input, k, n}]`
- `nodeStates(run)` -> `{st: ['ok'|'loss'|'stopped'|'unreached'], affected: {index: true}}`
- `edgeInfo(run, edge)` -> `{state: 'ok'|'empty'|'inactive', value}`
- `edgeWidth(value, max)` -> px
- `pickLayout(containerWidth, prefer)` -> `{kind: 'lr'|'compact'|'tb', scale}`
- `neighbours(edges, i)` -> `{up, down}` (direct only)
- `partition(expectedSteps)` -> `{placed, other}` (steps in the position table vs not)

## View (`static/js/views/graph.js`)
- `mountGraph(el, {run, runs, mode: 'run'|'skeleton'|'ghost', details: el|null, prefer: 'auto'|'compact', ghostMsg, selected})`
- Rebuilds on resize (debounced 120 ms), keeps `selected`; `refresh(el)` re-renders after data refresh.
- Selection: click, Enter, Space; second click, Esc or empty-space click clears; Esc handled in capture phase so a drawer closes on the second Esc.
- Tooltips (node: inputs with `from`, output, time, state; edge: `producer → consumer`, `input · count`) on hover and focus.

## Step card (`static/js/views/latest.js`)
- `stepItemHTML(run, runs, cfg, i, compact)` extracted from `stepsHTML` into `views/step.js` (re-exported by `views/latest.js`); used by the list, the drawer and the Selected-step panel.

## DOM/ARIA
- Graph `role="group"` labelled "Pipeline graph, <direction>"; nodes are `<button aria-pressed aria-label>` in column-by-column order; edge SVG `aria-hidden`; tooltip element reused from the page.

## View toggle
- "List | Graph" radio segmented control in the Steps head (Latest) and above the steps in the drawer; one shared choice in `localStorage['pm-steps-view']`; default Graph.

## New tokens (light + both dark blocks)
`--grp-callrail`, `--grp-gads`, `--grp-merge`, `--grp-persist` (+ `-bg`), `--edge`, `--edge-hl`, `--edge-empty`, `--edge-inactive`, `--edge-flow`.
