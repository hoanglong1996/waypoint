# Pipeline Monitor — graph view update

This update goes on top of the first design package (the `pipeline-monitor` folder you already have).
Copy these files over the old ones, keeping the same paths.

## New files
- `graph.js`: the directed-graph view (layouts, rendering, selection, tooltips). No libraries.
- `screenshots/graph/*.png`: 17 renders of the graph view.
- `design-canvas/Graph-*.dc.html`: the canvas artboards for the graph view.

## Changed files
- `index.html`: loads `graph.js` before `app.js`.
- `app.js`
  - New `stepItemHTML(run, runs, i, compact)`: one step card, now reused by the list and by the graph's "Selected step" panel. `stepsHTML()` calls it.
  - List | Graph switch (`viewToggleHTML`, `stepsHeadHTML`). The choice is saved in `localStorage['pm-steps-view']`; `?view=` overrides it.
  - `renderLatest()`, `openDrawer()`, loading and empty states can show the graph.
  - Exposes `window.PM` (STEPS, icons, fmt, isLoss, hhmmss, stepItemHTML) for `graph.js`.
  - New icons: `flow`, `list`, `graph`.
  - New URL params: `view=list|graph`, `select=<step name>`.
  - Mock scenarios changed: `loss` = `read_campaigns` returns 0; `incomplete` = the run stops before `read_gads_clickview`.
- `styles.css`
  - New tokens in all three token blocks: `--grp-*` (+ `-bg`) and `--edge*`.
  - New section 10 "GRAPH VIEW".
  - Reduced motion also hides `.gedge__flow`.
- `DESIGN_NOTES.md`: new section 8 "Graph view". Sections 1–7 are unchanged, except for the file list and the URL params.
- `screenshots/05, 12, 13`: re-rendered because the loss and incomplete scenarios changed.
- `design-canvas/canvas.json`: now lists the graph artboards.

## Unchanged (not in this zip)
- `screenshots/01–04, 06–11, 14`
- `design-canvas` artboards from the first package
