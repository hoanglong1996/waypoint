You are adding a new "Graph" view to the Pipeline Monitor front-end in this repository.

## Context
The base UI (Latest tab with hero + step list, History tab with runs list, trend chart and run drawer) was built earlier from the design in `docs/pipeline-monitor-degisn/`. That design folder has now been updated with a directed-graph view of a pipeline run. Your job is to implement this graph view in the real front-end, next to the existing step list.

## Read these first, before writing any code
1. `docs/pipeline-monitor-degisn/CHANGES.md`: what changed in the design and which files.
2. `docs/pipeline-monitor-degisn/DESIGN_NOTES.md`, section 8 "Graph view": model, layout table, edge routing, states, responsive rules, interaction, tokens.
3. `docs/pipeline-monitor-degisn/graph.js`: the reference implementation.
4. Section 10 "GRAPH VIEW" and the new `--grp-*` / `--edge*` tokens in `docs/pipeline-monitor-degisn/styles.css`.
5. The changes in `docs/pipeline-monitor-degisn/app.js`: `stepItemHTML`, `viewToggleHTML`, `stepsHeadHTML`, `renderLatest`, `openDrawer`, the loading/empty states and `window.PM`.
6. `docs/pipeline-monitor-degisn/screenshots/graph/*.png`: the target look. Open and look at them.
   g01 healthy, g02 data loss, g03 incomplete, g04 node selected, g05 mobile 375px, g06 History drawer (compact), g07 loading/empty, g08 tablet, g09 hover tooltip.
7. The current front-end code in this repo: how the Latest view, the drawer, the step card and the data model are built today.

Then give me a short plan: which files you will create or change, and how the reference code maps onto the existing code. Wait for my OK before you start.

## Hard constraints (same as before)
- Plain HTML, CSS and vanilla JavaScript (ES modules are fine). No framework, no build step, no CDN, no JS libraries, no graph-layout library.
- Edges are inline SVG. Nodes are real <button> elements. Icons are inline SVG.
- Reuse the existing CSS variable names. Add only the new tokens from the design (`--grp-callrail/gads/merge/persist` + `-bg`, `--edge`, `--edge-hl`, `--edge-empty`, `--edge-inactive`, `--edge-flow`) in the light block AND both dark blocks.
- Use `textContent` or escaping for any value that comes from the API.

## What to build
1. A "List | Graph" segmented control (radio inputs, styled like the env switch):
   - In the Steps section head of the Latest tab, and above the steps in the History drawer.
   - Both places share one choice, saved in localStorage (`pm-steps-view`, wrapped in try/catch).
2. A graph module (for example `graph.js` or `views/graph.js`) with one entry point, like `mountGraph(el, { run, runs, mode: 'run'|'skeleton'|'ghost', details, prefer })`.
3. Refactor the existing step renderer so a single step card can be rendered on its own (like `stepItemHTML`). The graph's "Selected step" panel must reuse it; do not duplicate the card markup.
4. Graph panel states:
   - Loading: skeleton nodes in the real layout.
   - Empty: a ghost graph with "No runs yet for <env>".
   - Error: keep the existing error card.

## Rules that must match the design exactly
- Edges come from the step input definitions (consumer input → producer step). That gives 9 fixed edges.
- The edge count is the consumer's recorded input value.
- Node state:
  - "Not reported" = the first missing step.
  - "Not reached" = later missing steps.
  - "Data loss" = output === 0 and some input > 0.
  - "Fine" = otherwise.
  - "affected" = a Fine step downstream of a loss step.
- Edge state:
  - inactive = producer or consumer missing (grey long dashes, chip "—").
  - empty = count 0 (red short dashes, red chip "0").
  - ok = otherwise (solid; width 1.25 + 2.75 × log10(count+1)/log10(max+1) px).
- Status is never colour only: always icon + word, plus a hatch/dashed border for missing steps.
- Layout: copy the fixed column/row table and the sizes from DESIGN_NOTES 8.3 (no auto-layout).
  - The calls → merge skip edge runs straight through the empty row and bends only in the last gap.
  - Merge's 3 inputs enter at 1/4, 2/4 and 3/4 of its height.
- Responsive, chosen by the panel's inner width:
  - ≥ 880px: desktop left-to-right, scaled down to fit.
  - 600–879px: compact left-to-right. This is also used in the 680px drawer.
  - < 600px: top-to-bottom in 2 lanes, with the calls → merge edge in the left gutter.
  - Rebuild the layout on resize (debounced) and keep the selection.
  - No horizontal page scroll at 375px.
- Interaction:
  - Click / Enter / Space selects a node: highlight it with its direct upstream and downstream nodes and edges, dim the rest, and open the "Selected step" panel with Upstream/Downstream chips.
  - Esc or a click on empty graph space clears the selection and moves focus back to the node.
  - In the drawer, the first Esc clears the selection and the second Esc closes the drawer.
  - Hover/focus shows tooltips: for nodes, the inputs with their "from" step, output, time and state; for edges, `producer → consumer`, `input · count`.
- Flow animation on ok edges only. Turn it off under `prefers-reduced-motion` and while a node is selected.

## Do not copy from the prototype
- The "Preview state" switcher, the mock data, the fixed NOW date, and the `?state=` / `?select=` URL params (`?view=` is optional).
- The changed mock scenarios (loss at read_campaigns, incomplete before read_gads_clickview) exist only to make the screenshots. Real data drives the states.

## Tests and checks
- Add unit tests (for example with `node --test`) for the pure graph rules: node state per step (including stopped vs unreached), the affected set, edge state and count, and the edge-width formula.
- Open the page with real or seeded data and compare it with each screenshot in `screenshots/graph/`, in light and dark, at 1440px, 960px and 375px, plus the drawer.
- Check keyboard use: Tab order goes column by column, Enter selects, Esc clears.
- List any difference from the design that you could not fix.

## Working style
- Work in small steps and tell me what changed after each one.
- If the real data shape or the existing code doesn't fit these rules, stop and ask me. Do not guess.