# Pipeline Monitor — design notes

Files: `index.html` (static shell), `styles.css` (tokens + all components), `app.js` (mock data + rendering, prototype only), `graph.js` (graph view), `screenshots/` (list view) and `screenshots/graph/` (graph view).
Open `index.html` directly in a browser. No build step, no external JS. The only external request is one optional Google Fonts family (Geist); without it the system font stack is used.

Prototype URL params: `?state=healthy|incomplete|loss|stale|partial|loading|empty|error&tab=latest|history&env=prod|qa&theme=light|dark&run=<i>&step=<name>&view=list|graph&select=<step name>`.
Scenarios used by the graph: `loss` = `read_campaigns` returns 0 from 14 instances; `incomplete` = the run stopped before `read_gads_clickview` (steps 6–9 missing). The dashed "Preview state" box (bottom right) does the same. Remove it in production.

## 1. Page frame
- One centred column, `max-width: 1200px`, side gutter 24px (16px under 720px). `body { overflow-x: hidden }` plus `minmax(0, …)` on every grid track, so there is no horizontal scroll at 375px.
- **Sticky header**, 56px, translucent background + blur. Desktop grid: `brand | tabs | spacer | env | live+theme`. Under 720px it becomes three rows: `brand … live+theme` / `env` / full-width tabs (each tab is 50%).
- Tabs use `role="tablist"`, roving `tabindex`, ←/→ keys. The environment switch is two real radio inputs styled as a segmented control, so the keyboard works for free.
- Banners (stale, partial read) sit in `#banners` above the active view, so they apply to both tabs.

## 2. Latest view (the hero)
1. **Hero card**: a 2-column grid, `[status + title + meta] | [3 KPIs]`.
   - Status pills always use icon + text + colour: `Complete` (ok, check-circle), `Incomplete` (bad, x-circle), `Possible data loss` (bad, octagon), `Stale · 32h old` (warn, clock).
   - The title is one plain sentence that answers "did it work?" (“Last night’s run completed”, “Run stopped before the end”, “Run finished, but one step lost data”).
   - A one-line explanation names the first missing step or the loss step in `code` style.
   - KPIs: Accounts = output of step 1, Calls = output of step 2, Saved stats = input of step 9. Each has a delta chip versus the previous run. If the step is missing it shows `—` + “not saved”.
   - **Flow strip**: 9 equal cells under group labels (CallRail 2 · Google Ads 4 · Merge 1 · Persist 2). Ok = green cell with check, loss = red cell with `!`, missing = dashed, hatched cell with its number. This gives the "where did it break" answer in about one second.
2. **Steps timeline**: `<ol>` of steps with a 36px left rail (2px line + numbered node), grouped by source with small uppercase dividers.
   - Step card grid (desktop): `name+time | input chips | output | sparkline`, columns `minmax(180px,1.25fr) minmax(150px,1.5fr) minmax(120px,.8fr) 128px`.
   - Under 1040px it becomes `name output / inputs spark`. Under 720px it becomes `name / inputs / output spark` (stacked cards).
   - Input chips: `→ name **count**`, with a tooltip saying which step the input came from. An empty input list shows a dashed `input none` chip.
   - Output: 28px tabular numerals, an `output` label + delta vs previous run, and a 3px **magnitude bar** (log scale against the biggest count in the run). The bars make the funnel visible: 10 → 1,284 → 6 → 14 → 92 → 3,410 → 1,284.
   - `null` output: muted `n/a` + “returns nothing”. Its sparkline shows the input instead and is labelled `input · 14 runs`.
   - **Loss rule**: `output === 0 && some input > 0` gives a red-tinted card, a red `!` node, a red count and a `Possible data loss` pill next to the time.
   - **Missing step**: dashed border, hatched background, dashed node, `expects <input>` chips and “Step did not report for this run”.
   - Sparkline: 128×36 inline SVG, last 14 runs. Gaps (missing) break the line, zero values get a red dot, and the latest point is an accent dot.

## 3. History view
- **Trend card** (top): step `<select>`, the latest value with a delta chip on the right, and a 240px (200px on mobile) SVG area chart of the last 30 runs.
  - The chart is redrawn at the container's pixel width (on resize too), with a 4-line grid, compact y labels (1.5k), and about 7 date labels.
  - Hover: a dashed crosshair + focus dot + floating tooltip (date, value, delta vs the run before). The chart is focusable: ←/→/Home/End move between runs, and focus shows the latest run.
  - Missing runs break the line and are drawn as a dashed circle on the baseline. A 0 caused by data loss is a filled red point.
- **Runs list**: a header row + `<button class="run-row">` per run (columns: run · status · accounts · calls · saved · flags · chevron). Under 860px each row becomes a 3-column mini card with small labels.
- **Drawer**: a right-side `role="dialog"`, `aria-modal`, `min(680px,100%)` wide, scrim behind it, slide-in 320ms. Esc / scrim / ✕ close it, focus is trapped while open and goes back to the row after closing. It reuses the same step renderer in `steps--compact` mode (no sparkline/bar).

## 4. States
| State | Where | Treatment |
|---|---|---|
| Loading | both views | Skeleton hero + 9 skeleton step rows (shimmer), live dot grey “Loading…”, `aria-busy` |
| Empty | both views | Centred card, inbox icon, “No runs yet for qa”, `role="status"` |
| Data store unreachable | replaces both views | Red-bordered card with `role="alert"`, error code, Retry button + auto-retry hint, live dot grey “Last updated 4m ago”. No numbers shown |
| Stale (> 26 h) | banner + hero pill | Amber banner `role="alert"` with the last finish time; amber `Stale` pill in the hero |
| Some records unreadable | banner + History flag | Neutral info banner with the count; `N unreadable` pill on the run row |
| Incomplete | hero + steps | Red `Incomplete` pill, first missing step named, hatched missing cards, KPI `—` |
| Data-loss step | hero + step | Extra red pill in the hero, red flow cell, red-tinted step card |

## 5. Tokens (all in `:root` in `styles.css`)
- Colours: `--bg --surface --surface-2 --surface-3 --border --border-strong --text --text-2 --text-3 --accent --accent-soft --focus`, status `--ok/--warn/--bad/--neutral` each with `-bg` and `-border`, chart `--chart-*`, `--spark`, `--bar`.
- Dark theme: the same names are redefined under `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` **and** `:root[data-theme="dark"]` (keep both blocks the same). The toggle sets `data-theme` and saves it in localStorage.
- Contrast (checked against `--surface`): text 18:1, text-2 8:1, text-3 ≥ 5.5:1, status text on its tinted background ≥ 5.6:1 in light mode.
- Spacing `--s-1…--s-12` (4px base) · radius `xs 4 / sm 6 / md 10 / lg 14 / pill` · shadows `--shadow-1/2/3` (dark mode uses borders, not shadows).
- Type: Geist (or the system stack), mono for step names and env. Scale `11/12/13/14/16/20/24` + numerals `22/28/40`. Every count uses `.num` (tabular numerals, -0.02em tracking).

## 6. Motion and accessibility
- Motion: only the live-dot pulse (2.4s), skeleton shimmer, drawer slide, and chart crosshair easing. All are turned off under `prefers-reduced-motion`.
- Visible `:focus-visible` ring (2px `--focus`), skip link, 44px touch targets for tabs and the segmented control.
- Status is never shown by colour only: there is always an icon + word, plus a hatch/dash pattern for missing data.

## 7. Mapping to the build tasks
- Static shell + tokens → copy `index.html` / `styles.css` as they are.
- Rendering → replace `buildRuns()` in `app.js` with the real fetch. The view code needs the step shape `{name, inputs:[{name,value}], output|null, finishedAt}` or `{name, missing:true}`, which is what the API returns.
- Derived rules live in `analyse()` / `isLoss()` / `headline()` / `metric()`. Keep them as plain functions so they are easy to unit-test.


## 8. Graph view (List | Graph)
A second way to show the same 9 steps, in the Latest tab and in the History drawer. Code: `graph.js`, CSS section 10 in `styles.css`.

### 8.1 Toggle
- "List | Graph" segmented control in the Steps section head (Latest) and above the steps in the drawer. It uses two real radio inputs, like the env switch.
- The choice is shared by both places and remembered in `localStorage['pm-steps-view']` (wrapped in try/catch). `?view=` overrides it.

### 8.2 Model
- Edges come from the step definitions: `consumer.inputs = [[inputName, producerIndex]]`. That gives 9 edges.
- **Edge count** = the consumer's recorded input value (not the producer's output).
- **Node state** (in this order):
  1. `stopped` = the first missing step ("Not reported": amber, dashed + hatched)
  2. `unreached` = later missing steps ("Not reached": grey, dashed + hatched)
  3. `loss` = `output === 0 && some input > 0` ("Data loss": red tint, octagon icon)
  4. `ok` = otherwise ("Fine": check icon)
- **Affected**: an `ok` node that is downstream (transitively) of a loss step gets an extra dashed amber "affected" pill and an amber border.
- **Edge state**:
  - `inactive` = the producer or the consumer is missing. Grey long dashes, chip shows "—".
  - `empty` = count is 0. Red short dashes, red chip "0".
  - `ok` = otherwise. Solid line; width = `1.25 + 2.75 × log10(count+1) / log10(max+1)` px, where max = the largest edge count in this run.
- Status is never colour alone: every node has icon + word; missing nodes also get a hatch + dashed border; edges differ by dash pattern, not only colour.

### 8.3 Layout rules (fixed, hand-tuned, no auto-layout library)
The graph shape never changes, so positions are constants. Columns are layers: col 0 = sources, col 4 = sinks.

| step | col | row |
|---|---|---|
| read_callrail_account | 0 | 0 |
| read_callrail_call | 1 | 0 |
| read_partners | 0 | 1.5 |
| read_instances | 1 | 1.5 |
| read_campaigns | 2 | 1 |
| read_gads_clickview | 2 | 2 |
| merge_calls_clickview | 3 | 1 |
| record_call_statistics | 4 | 0.5 |
| save_call_statistics | 4 | 1.5 |

- `x = 8 + col × (w + gap)` and `y = top + row × (h + rowGap)`.
  - **Desktop LR**: w 154, h 128, gap 88, rowGap 28, top 28. The design box is 1138 × 480 px.
  - **Compact LR**: w 100, h 72, gap 28, rowGap 20, top 22. The design box is 628 × 274 px.
- This gives zero edge crossings. CallRail sits in row 0, Google Ads in rows 1–2, and Merge sits in the middle, level with Campaigns.
- **Group bands**: faint tinted rounded rects behind the nodes (`--grp-*-bg`) with an uppercase label in `--grp-*`. CallRail = cols 0–1, row 0. Google Ads = cols 0–2, rows 1–2. Merge = col 3, Persist = col 4 (full height). Each node also shows a group dot.
- **Tab order** = column by column, top to bottom: account, partners, call, instances, campaigns, clickview, merge, record, save.

### 8.4 Edge routing
- **Ports**: an edge leaves the producer at the middle of its right side. It enters the consumer on the left side at `y = top + h × (k+1)/(n+1)`, where k = input index and n = input count. This spreads Merge's 3 inputs as calls / campaigns / clickview, top to bottom.
- **Normal edge**: cubic Bézier `M s C (s.x+d, s.y) (e.x−d, e.y) e` with `d = half the horizontal distance`. The curve leaves and enters horizontally.
- **Skip edge** (calls → merge spans 2 columns): it runs straight along row 0 (that row is empty in col 2), then bends only inside the last gap. So it never passes behind Campaigns.
- **Arrowhead**: an 8 × 9 px filled triangle drawn as its own path at the port. The line stops 7 px early. No `<marker>`, so the colour follows the edge state easily.
- **Hit area**: a transparent 14 px stroke on the same path, used for the hover tooltip.
- **Chips** (desktop only): two lines (input name / count), max 80 px wide. They sit at the Bézier midpoint, which always falls inside an 88 px gap, so they never cover a node. The skip edge's chip sits on its straight part above Campaigns. A 3 px `--surface` ring cuts the line behind the chip.
- **Flow animation**: a second path on `ok` edges with a moving dotted dash (1.6 s loop). It is hidden under `prefers-reduced-motion` and while a node is selected.

### 8.5 Responsive

| container width (inside the card) | layout |
|---|---|
| ≥ 880 px | Desktop LR, scaled `min(1, width / 1138)` (0.77–1) |
| 600–879 px (tablet, History drawer at 680 px) | Compact LR, scaled `min(1.35, width / 628)` |
| < 600 px (phones, drawer on phones) | Top-to-bottom, 2 lanes |

- **Desktop LR** shows all chips, mono names and times.
- **Compact LR** hides the mono name, the time and the state text; the state icon sits in the bottom-right corner. Edge labels show in the hover/focus tooltip, and tapping a step opens its details.
- **Top-to-bottom (phones)**: I chose this over a horizontal scroll panel, because a scroll panel hides half the graph and the merge point is the most important part.
  - Lane A = CallRail and the left branch, lane B = Google Ads. Merge spans both lanes.
  - The calls → merge edge leaves Calls on its left side and runs down a 22 px gutter, so it never crosses Campaigns.
  - Chips are one line, sitting in the 64 px row gaps. Two chips that share a gap are staggered ±12 px.
- **Scaling**: positions are px inside `.graph` (absolute). The whole box gets `transform: scale(s)`, and `.graph-stage` reserves `H × s` height. The layout is rebuilt on resize (debounced 120 ms), and the selection is kept.
- No horizontal page scroll at 375, 600, 768, 1024 and 1440 (checked).

### 8.6 Interaction
- Nodes are real `<button>`s with a full `aria-label` (label, step name, group, state, output).
- **Click / Enter / Space** selects a node:
  - The node gets an accent ring. Its direct upstream and downstream nodes and their edges stay; everything else dims (nodes to .38, edges to .18).
  - A "Selected step" panel opens under the graph. It reuses the list's step card (`stepItemHTML`) and adds Upstream / Downstream chips that jump to that step.
  - Clicking the same node again clears the selection.
- **Esc** or a click on empty graph space clears the selection and moves focus back to the node. Esc is caught in the capture phase, so in the drawer the first Esc clears the selection and the second closes the drawer.
- **Hover/focus on a node** shows a tooltip: the full inputs with their "from" step, the output, the finish time and the state.
- **Hover on an edge or chip** shows a tooltip: `producer → consumer`, `input · count`, plus a note for 0 / not reached.

### 8.7 Graph panel states
- **Loading**: the same layout with skeleton nodes and dashed ghost edges. The header still says how data flows.
- **Empty**: a ghost graph (names, no counts, dashed) behind a centred message "No runs yet for qa".
- **Error**: same as the list view; the error card replaces everything.

### 8.8 New tokens (light and dark, in all three token blocks)
- `--grp-callrail`, `--grp-gads`, `--grp-merge`, `--grp-persist` and their `-bg` fills (band labels ≥ 4.5:1 on `--surface`).
- `--edge` (≥ 3:1), `--edge-hl` (= accent), `--edge-empty` (= bad), `--edge-inactive`, `--edge-flow`.

### 8.9 Screens (`screenshots/graph/`)
- `g01` healthy (light/dark), `g02` data loss at `read_campaigns`, `g03` incomplete (stopped before `read_gads_clickview`).
- `g04` node selected (merge / instances), `g05` mobile 375 px, `g06` drawer compact (with tooltip in dark).
- `g07` loading / empty, `g08` tablet 960 px, `g09` hover tooltip, `g00` the full Latest page in graph mode.
