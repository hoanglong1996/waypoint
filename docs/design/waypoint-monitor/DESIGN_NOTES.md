# Waypoint Monitor — design notes

Waypoint Monitor is a generic, self-describing pipeline monitor. Every run carries its own **flow description** (groups, steps, hand-offs), and the views draw whatever the run describes. Nothing about a specific pipeline is hard-coded in the views; the mock pipelines in `app.js` are only data.

The app has three pages: **Home** (all pipelines, the default landing page), **Latest** and **History** for one pipeline. See §13–§16.

**Files**
- `index.html`: the static shell.
- `styles.css`: tokens and all components.
- `app.js`: mock data, model and rendering. It is a prototype: replace the mock part with real data.
- `graph.js`: the graph view and its layout.
- `screenshots/`: the renders.

Open `index.html` directly in a browser. There is no build step and no external JS. The only external request is one optional Google Fonts family (Geist); without it the system font stack is used.

**Addresses** (hash routes; see §16)

```
#/                                 Home
#/p/<id>                           Latest
#/p/<id>/history?env=<env>         History, filtered to one environment
anything else                      "Pipeline not found"
```

**Design-time URL params** (for reviews and screenshots; not part of the product):

```
?state=healthy|incomplete|loss|stale|partial|running|running-start|stalled|other|
       simple-missing|simple-unreadable|simple-version|long|many|loading|empty|error
&theme=light|dark  &view=list|graph  &run=<i>  &select=<step name>  &step=<trend step>
```

The "Preview state" box in the bottom-right corner is a **design-time tool**. It has a dashed border and a "DESIGN TOOL" tag, and it is not part of the product. Delete the `<aside class="proto">` block and the marked section at the end of `app.js` when you build the real app.

**Storage keys**
- `wp-theme`: light / dark.
- `wp-steps-view`: list / graph.

All reads and writes are wrapped in try/catch.

## 1. Page frame and header
- **Page**: one centred column, `max-width: 1200px`, side gutter 24px (16px under 720px). There is no horizontal page scroll at 375px.
- **Sticky header** (56px):
  - Grid: `brand | spacer | live indicator + theme toggle`. **No dropdown and no tabs** in this row (the picker was removed; see §14).
  - Brand: a 24px indigo (#4f46e5) rounded square with a white path/waypoint glyph (the same artwork as the favicon), then "Waypoint Monitor". There is no subtitle. The brand is a link to Home (`#/`).
  - On pipeline pages a second bar (the context bar) sits under it: back link, pipeline name and the Latest | History tabs (§14).
- **Favicon**: an inline SVG data URI in `<head>`, the same glyph as the brand mark.
- **Tabs**: now plain links (`<nav aria-label="Pipeline views">`, `aria-current="page"` on the active one), because each tab is its own address.
- **Banners** (stale, partial read) sit above the active view.

## 2. Latest view
1. **Hero card**: `[status + title + meta] | [KPIs]`.
   - **Status pill**: `Complete` (ok), `Incomplete` (bad), `Running` (accent, spinner), `Stalled` (warn, alert). It can be followed by `Possible data loss` (bad) and `Stale · 32h old` (warn).
   - **Title**:
     - "Last night's run completed"
     - "Run stopped before the end"
     - "Run finished, but one step lost data"
     - **"A run is in progress"**
     - "Run stalled at a step"
   - **Body line while running**: "Running now: `<step>`. The page updates by itself every few seconds." If no step has reported yet: "Started, waiting for the first step to report."
   - **Meta**: date and start time. While running, "finished … ago" and the duration are hidden. While stalled, the duration is hidden.
   - **KPIs** come from the pipeline (`pipe.kpis`: label + step + output/input), so any pipeline can choose its own headline counts. A KPI without a value shows "—" with **"in progress"** while running and **"not reported"** otherwise.
   - **Step map**: one cell per step, in flow order. Group labels sit above the cells: one span per run of consecutive steps in the same group, with `fr` widths equal to the step count and a `.gdot.g-N` before each label. Reported steps that are not in the flow come last, under "Other". In simple mode the cells are in report order and there are no group labels.
     - Cell classes: `flow__cell--ok`, `--loss`, `--missing`, `--running` (accent fill, spinner), `--waiting` (transparent, dotted border, hourglass), `--stalled` (warn fill, dashed border, alert icon).
2. **Steps list**: `<ol>` with a left rail.
   - Group headings are read from the run, with a slot dot. Steps that are not in the flow go under the heading **"Not in this run's flow"**, and their card gets a small neutral `not in flow` pill.
   - **Card title**: "Label · technical_name" when the label differs (label in semibold sans, name in mono). Otherwise it is just the mono name.
   - Input chips have the tooltip "from X". When the producer is not in the flow the tooltip is "from X (not in this flow)" and the chip gets a dashed warn border (`.chip--dangling`).
   - Live states: see §9.

## 3. History view (unchanged apart from renames)
- **Trend card**: the step picker is built from the run's flow and shows "Label · name". It shows an SVG area chart, a hover tooltip and a delta chip. Live runs show "in progress" in the tooltip.
- **Runs list**: the KPI columns use `pipe.kpis[].short`. A live run shows a `Running` pill and "in progress" instead of a duration.
- **Drawer**: the same step renderer as the list, in compact mode, with the same List | Graph toggle.

## 4. Page states
| State | Treatment |
|---|---|
| Loading | Skeleton hero and steps, sized by the pipeline's step count. In graph mode: skeleton nodes in the real layout. |
| Empty | "No runs yet for `<pipeline label>`". In graph mode: a ghost graph behind the message. |
| Data store unreachable | Red card with `role="alert"`, retry. No numbers shown. |
| Stale (> 26 h) | Amber banner + `Stale` pill. Never shown while a run is in progress. |
| Some records unreadable | Info banner + `N unreadable` pill in History. |
| Incomplete / Data loss | As before. |
| Running / Waiting / Stalled | See §9. |

## 5. Tokens (all in `:root` in `styles.css`)
- **Base**: `--bg --surface --surface-2 --surface-3 --border --border-strong --text --text-2 --text-3 --accent --accent-soft --focus`.
- **Status**: `--ok/--warn/--bad/--neutral`, each with `-bg` and `-border`.
- **Chart**: `--chart-*`, `--spark`, `--bar`.
- **New, live steps**: `--running: var(--accent)` and `--running-bg: var(--accent-soft)`. They are defined once in the light block and follow the theme automatically, because `--accent` is redefined per theme.
- **New, group colour slots `--grp-0 … --grp-7` and `--grp-N-bg`**. They replace `--grp-callrail/gads/merge/persist` and are defined in **all three** token blocks.

  | slot | colour | light | dark |
  |---|---|---|---|
  | 0 | teal | #0d7680 | #45c6d0 |
  | 1 | blue | #2f5fc9 | #7aa2ff |
  | 2 | violet | #7349cc | #b69bff |
  | 3 | slate | #556070 | #9aa3b0 |
  | 4 | amber | #b45309 | #f0a35e |
  | 5 | pink | #be185d | #f08cb6 |
  | 6 | green | #3f7d20 | #8fd16a |
  | 7 | brown | #8a5a2b | #d3a574 |

  - The `-bg` values are the same colour at about 5% alpha.
  - Light values are ≥ 4.5:1 on `--surface`, so they also work for the band label text.
- **Edges**: `--edge`, `--edge-hl`, `--edge-empty`, `--edge-inactive`, `--edge-flow`.
- **Dark theme** blocks: `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` and `:root[data-theme="dark"]`. Keep the two identical.

## 6. Motion and accessibility
- **Motion**: live-dot pulse, skeleton shimmer, drawer slide, chart crosshair, edge flow dots. New: the spinner, the indeterminate progress bar and the running-node pulse ring.
- **Reduced motion** (`prefers-reduced-motion: reduce`) keeps every icon and every word and removes all movement:
  - The spinner stays a **static partial ring**.
  - The progress bar becomes a **static 40% segment** at the left.
  - The pulse ring and the edge flow dots are not drawn.
  - All screenshots were rendered with reduced motion on, so they show exactly this static look.
- **Accessibility**:
  - Visible focus rings, a skip link, 44px touch targets.
  - Status is never colour alone: icon + word, plus a dashed/dotted/hatched pattern for missing, waiting and stalled.
  - Graph nodes are `<button>`s whose `aria-label` holds the label, technical name, group, state and output.

## 7. Mapping to the build
- Copy the static shell, tokens and CSS as they are.
- Replace `buildRuns()`/`makeRun()` with real data. The model needs:
  - **run** = `{ id, startedAt, live, flow | null, flowStatus: 'ok'|'missing'|'unreadable'|'version', problems[], records[], unreadable }`
  - **flow** = `{ version, groups: [{id, title}], steps: [{name, label?, group?, inputs: [{name, from?}], col?, row?}] }`
  - **record** = `{ name, label?, state: 'done'|'running'|'stalled', startedAt, finishedAt|null, inputs: [{name, value}], output|null, expectedS? }`
- All rules live in plain, testable functions:
  - `model(run)`: steps, other steps, groups and slots, edges, dangling inputs, loop removal, states, affected set.
  - `analyse(run)`: run status, counts, stale.
  - `headline()`, `metric()`, `isLoss()`.
  - `PMGraph.layout(model, kind, width)` in `graph.js`.

## 8. Graph view (List | Graph)
- **Toggle**: shared by the Latest tab and the drawer, saved in `wp-steps-view`.
- **Model** (`model(run)` in app.js):
  - **Edges**: one for every declared input whose `from` names a step **in the flow**.
  - **Edge count**: the consumer's recorded input value.
  - **Edge state** (first match wins):
    1. `pending`: either end is running or waiting. Accent colour at 60% opacity, dashes `3 5`. The chip shows the value or "…".
    2. `inactive`: no hand-off happened (grey long dashes, chip "—").
    3. `empty`: count 0 (red short dashes, chip "0").
    4. `ok`: solid line, width `1.25 + 2.75 × log10(n+1)/log10(max+1)`.
  - **Node states**: `ok` (Fine), `loss`, `stopped` (Not reported, the first missing step), `unreached` (Not reached), plus the live states in §9. A Fine step downstream of a loss also gets an "affected" pill.
- **Layout** (`layout()` in graph.js): a small layered algorithm. No library and no hand-placed coordinates.
  1. **Layer** = longest path from a source (topological order; declaration order breaks ties). An optional `col` hint moves a step to a later layer. A hint that would put a step *before* one of its inputs is ignored and listed under Problems.
  2. **Long edges** (skipping layers) get invisible **dummy waypoints**, one per skipped layer. They take part in ordering, so a long edge runs through a free lane instead of behind a node.
  3. **Order and position inside a layer**:
     - Each item wants the **average position of its producers** (barycenter). Ties keep declaration order.
     - An optional `row` hint fixes the wanted position at `row × (node size + gap)`.
     - Sources in the first layer stack in declaration order.
     - A 1-D **block placement** then keeps items apart. Spacing between nodes is node size + 34px (lr). Dummies need less room.
     - When two items collide, they and their neighbours form a block that is centred on the mean of what they wanted. This is the same idea as isotonic regression, and it keeps fan-outs centred around their producer.
  4. **Ports**: an edge leaves the producer at the middle of its right side (bottom side in tb). It enters the consumer on the left (top in tb), spread at `(r+1)/(n+1)`. Inputs are **sorted by where their edge arrives**, so edges do not cross at the node.
  5. **Paths**: a cubic Bézier with horizontal tangents (vertical in tb) between layers, and a straight line through each dummy. The line stops 7px before the port, and an 8×9 arrowhead path is drawn there.
  6. **Chips**: at the midpoint of an edge's first curve, which is always in a gap between layers.
     - Desktop chips are two-line, max 80px. Phone chips are one line.
     - A simple collision pass moves overlapping chips apart vertically.
     - No chips in compact mode (they show in the tooltip instead).
  7. **Bands**: the bounding box of each group's nodes (+8px, plus 22px above for the label). They are filled with `--g-bg` through the slot class, with the label in `--g`.
- **Sizes**

  | kind | node | gap between layers | gap inside a layer | when |
  |---|---|---|---|---|
  | `lr` | 154×128 | 88 | 34 | panel ≥ 600px and scale ≥ 0.77 |
  | `compact` | 100×72 | 30 | 26 | drawer, tablet |
  | `tb` | (width−50)/2, 104–160 × 124 | 64 | 18 | < 600px |

  - On phones the nodes narrow (down to 104px) before the graph is scaled. Below 130px the class `graph--narrow` hides the finish time; it is still in the tooltip.
- **Interaction**:
  - Click, Enter or Space selects a step. Its neighbours stay and the rest dims. The "Selected step" panel reuses the step card.
  - Esc or a click on empty space clears the selection. Tooltips work on nodes, edges and stubs.
  - Rebuilt on resize.

## 9. Live steps: Running, Waiting, Stalled
| state | when | list card (`.step--…`) | graph node (`.gnode--…`) | pill (`.gpill--…`) | step map (`.flow__cell--…`) |
|---|---|---|---|---|---|
| **running** | record `state: 'running'` | accent border + 3px `--running-bg` ring, spinner on the rail, time row "Running · started hh:mm:ss", output = **elapsed** (`42 s` · `3m 05s` · `1h 02m`) in accent + "running" + an indeterminate 3px sliding bar | accent border + soft **pulsing ring** (`::after`), elapsed count, "running" | `Running` (accent bg, spinner) | accent fill + spinner |
| **waiting** | no record yet while the run is live | **dotted** border, no shadow, muted title, hourglass on the rail, "Not started" instead of a time, "waiting for an earlier step" in the output area | dotted border, no shadow, muted label, "—" + "Not started" | `Waiting` (dotted, neutral) | transparent, dotted border, hourglass |
| **stalled** | record `state: 'stalled'` (running far past its usual time; the run stopped here) | warn colour, **dashed** border, warn tint, alert icon, elapsed time + "stalled · usually ~40 s" | warn dashed border + **diagonal hatch** over a warn tint, elapsed in warn, "stalled" | `Stalled` (warn) | warn fill, dashed border, alert icon |

- Steps after a stalled step are **Not reached**. Edges that touch a running or waiting step are **pending**.
- **Timers**: every `.js-elapsed` span carries `data-since`. One 1-second interval updates all of them. In the real app, use `Date.now()`; the prototype uses a fixed "now" so the renders stay stable.
- **Graph header summary**: also shows "running `<step>`" (accent, spinner) and "stalled at `<step>`" (warn, alert icon).
- **Legend**: a "Live" group with the three pills.

## 10. Self-describing graph: steps that are not on the map
- **"Other steps" row** (`.graph-other`): steps that reported but are not in the run's flow description.
  - They are not placed in the graph. Below it there is a wrapping row: eyebrow "Other steps", the faint note "not in this run's flow", then chip buttons (state icon + label + mono name).
  - Clicking a chip selects the step: the "Selected step" panel says "Not in this run's flow, so its hand-offs are unknown."
  - In the list these steps sit under the "Not in this run's flow" heading with a `not in flow` pill.
- **Dangling input** (`.gedge--dangling`): an input whose `from` is not in the flow.
  - It is drawn as a **34px dashed stub** (28px on phones) in `--warn`, 1.5px wide, dashes `3 3`, with an arrowhead into the port. It is never a full arrow.
  - The tooltip, the list chip and the Selected step panel read "from `<name>` (not in this flow)".
- **Loops**: the model finds each cycle and drops the edge that points furthest *back* in declaration order (the hand-off that closes the loop). It repeats until there are no cycles left, then lists what it dropped under Problems.
- **Simple mode**: used when `run.flow` is null. Steps are shown **in the order they reported**:
  - a wrapping grid of nodes (`.graph-simple`, `auto-fill, minmax(170px, 1fr)`; 2 columns on phones), each with an order badge;
  - no edges, no bands, no "Arrows" or "Groups" legend.
  - The list view shows the same notice.
  - An info notice (`.graph-notice`: info icon, `--surface-2`, rounded 10px) sits above the graph with one of:
    - `missing`: "No flow description for this run, showing steps in the order they reported"
    - `unreadable`: "Flow description unreadable" (the parse error goes into Problems)
    - `version`: "Unsupported record version: this run was written by a newer pipeline library, showing steps in the order they reported"
- **Problems disclosure** (`.graph-problems`): a collapsed `<details>` under the legend, shown only when there are problems.
  - Its summary is warn-coloured: alert icon + "Problems in this run's description (N)" + a chevron.
  - It opens to a bullet list. Long text wraps (`overflow-wrap: anywhere`).
  - It lists: dangling inputs, dropped loop edges, ignored hints, unreadable descriptions, and the names of the "other" steps.
- **Labels**: a step can have a friendly `label`.
  - The graph node shows the label, plus the mono name when they differ.
  - The list title is "Label · technical_name".
  - The tooltip and `aria-label` include both.

## 11. Group slots
- `model()` gives each group in `run.flow.groups` a slot `0–7` in declaration order (wrapping after 8).
- Bands, band labels, step-map labels, list group headings and legend dots all use **one generic class** `.g-0 … .g-7`. The class sets `--g` and `--g-bg`, and the components read only those variables (`.gband { fill: var(--g-bg) }`, `.gband-label { color: var(--g) }`, `.gdot { background: var(--g) }`).
- Group titles are always read from the run.

## 12. Screens
These are in `screenshots/`; all of them also exist in light or dark as listed.

Note: `w`, `l` and `g` shots were taken before Home existed, so their header still shows the old pipeline picker. Everything below the header is unchanged. The new header is in `P01–P05`.
- `w01–w14`: core screens with the new header, in both themes.
- `l01–l08`: list view: running, run just started, stalled, mobile running, other steps, simple mode.
- `g01–g19`: graph view:
  - a 6-group graph, data loss, incomplete, selected, mobile, drawer, loading/empty, tablet;
  - running, stalled;
  - other steps + dangling stub + Problems (closed and open), a selected other step;
  - the three simple-mode notices;
  - a second pipeline (Google Ads click view) to show the generic layout.
- `H01–H05`: Home desktop (light, dark), mobile 375 (light, dark), tablet 820.
- `S01–S09`: Home states: loading, empty, data store unreachable, partial data, 22 cards, long name (desktop, mobile), hover + focus, many cards on mobile.
- `E01–E07`: History with the environment filter: prod, qa (dark), mobile, no runs (desktop, mobile), drawer of a qa run, a pipeline with one environment.
- `P01–P08`: headers (Home, Latest, History, mobile, long name) and the env tag on Latest.
- `N01–N02`: Pipeline not found (desktop, mobile).

## 13. Home page
**Layout**
- Head: h1 "Pipelines" + a one-line summary ("4 pipelines · 2 need attention · each card shows the newest run in any environment"). Same h1 style as the Latest hero title.
- Two groups, each with a small title and a count: **"Needs attention"** (title in `--bad` + warning icon) and **"Healthy and running"**. When nothing needs attention there is one group, "All pipelines". Each group is sorted A–Z.
- Grid: `.pgrid` = `repeat(auto-fill, minmax(min(340px, 100%), 1fr))`, gap 16px. That gives 1 column at 375px, 2 at 820px and 3 at 1200px. Cards in a row share the same height.

**Card anatomy** (`.pcard`, the whole card is one `<a href="#/p/<id>">`)
```
┌───────────────────────────────────────────────┐
│ ⚠ Needs attention                    (flag)    │ only attention cards
│ Pipeline name (2 lines max, then …)   [prod]   │ name + env tag
│ (Stale) · finished 31 h ago                    │ status pill (sm) + time
│ Last night's run is missing (expected …)       │ reason, attention only
│ ────────────────────────────────────────────── │
│ FIRST STEP     LARGEST STEP     LAST STEP      │ eyebrow labels
│ 12,480         12,311           12,290         │ hero-number style, 26px
│ fetch_calls    dedupe           write_table    │ mono step names
└───────────────────────────────────────────────┘
```
- Padding 20px (16px under 720px), radius `--radius-lg`, 1px `--border`, `--surface` background.
- Vertical rhythm: 8px between name, status and reason; 16px above the divider; 14px below it. Number columns have a 12px gap; each column truncates its step name with an ellipsis.
- "Largest step" = the step with the highest count between the first and the last. Steps that have not reported show "—" and "not reported"; a running step shows "in progress".
- `aria-label` reads the whole card as one sentence: "Google Ads, prod, Lost data, needs attention, finished 2 h ago. …" followed by the three numbers
- **Hover**: border becomes `--border-strong`, shadow `--shadow-2`, lift 1px (no lift with reduced motion). **Focus**: 2px `--focus` outline, offset 3px.

**Status pill and colour** (newest run in any environment; first match wins)

| Pill | Tone (existing pill) | When | Attention? |
|---|---|---|---|
| Running | `--running` (accent) | a run is in progress | no |
| Stale | warn (amber) | newest run is older than 26 h | yes |
| Incomplete | bad (red) | stopped or stalled before the last step | yes |
| Lost data | bad (red) | a step got input but returned 0 | yes |
| Completed | ok (green) | otherwise | no |

- Never colour alone: every pill has an icon and a word; attention cards also get the "Needs attention" flag text, a coloured 1px border plus a 1px inset ring (`--bad-border` or `--warn-border`), a reason line, and they are in their own titled group.
- A stalled live run shows "Incomplete" on Home (reason "Stalled at <step>"), because Home only has the five pills from the brief. The Latest page still shows the full "Stalled" detail.

**States**
| State | Treatment |
|---|---|
| Loading | 6 skeleton cards in the real grid (same shapes as a card). |
| Empty | Existing empty card: "No pipelines yet" / "Pipelines appear here after their first run." |
| Data store unreachable | Existing red error card + "Retry now" and a live countdown "Retrying automatically in 30s · last success 4m ago" (`.js-countdown`, ticks every second). |
| Some records unreadable | Existing info banner "Some records could not be read" above the grid; cards still show. |
| Very long name | 2 lines, then ellipsis; full name in `title` and in the `aria-label`. |
| 20+ cards | Same grid; the page scrolls. Attention group stays first. |

## 14. Pipeline page header
- The top row is the same as on Home (brand link, live indicator, theme).
- Under it, the **context bar** `.ctxbar` (48px, `--surface`, bottom border):
  `‹ All pipelines` (`.backlink`, links to `#/`) · a 1px separator · the pipeline name (`.ctxbar__name`, 16px/600, one line + ellipsis, full name in `title`) · the **Latest | History** tabs on the right (existing tab style, underline on `aria-current="page"`).
- Under 720px it wraps into three rows: back link / name (18px) / full-width tabs (two equal halves).
- The pipeline dropdown is **removed**, and so is the `wp-pipeline` storage key. The pipeline now comes from the address.
- The page `<title>` follows the route, e.g. "CallRail · History · Waypoint Monitor".

**Env tag** (`.env-tag`): mono 11px, 20px tall, `--surface-2` background, `--border-strong` border, radius 6px; text is the env name (prod, qa). `.env-tag--lg` (26px tall, 12px) sits right after the status pill in the Latest hero. The same tag appears on Home cards and in the run drawer summary. It is neutral grey on purpose, so it never looks like a status.

## 15. History: environment filter
- A small card `.envbar` above the Step trend card: label **"Environment"** + a segmented control (`.segmented--env`).
- It is the existing segmented control, built as a radio group (`role="radiogroup"`, native `<input type="radio" name="env">`), so arrow keys move between envs and the applied one is always visibly selected (raised white segment with a shadow and border, same as the existing control).
- Options: only envs that have runs for this pipeline, in a fixed order (prod first, then A–Z). A single env is still shown, as the applied one. If the address asks for an env with no runs, that env is added with a "no runs" hint so the control still shows what is applied.
- **Default** (no `?env`): prod if the pipeline has prod runs, else the env of the newest run.
- It limits **the trend, the runs list and the drawer**. A note under the control says "Showing 30 prod runs. The trend, the runs list and run details use this environment."
- Changing it sets `?env=` in the address (a new history entry) and keeps keyboard focus on the chosen option.
- **No runs in this environment**: the existing empty card ("No runs in this environment", "<Pipeline> has no runs in [qa] yet. Choose another environment above.") replaces the trend and the list; the filter stays usable.
- At 375px the label and control fit on one row; the note wraps below.

## 16. Navigation and not found
- Home → card → Latest ⇄ History (tabs). "All pipelines" back link or the brand → Home.
- Every page has its own address, so reload, Back/Forward and links keep the view. Moving between routes closes the drawer and scrolls to the top; List | Graph choice is kept.
- An unknown pipeline id or any other address shows **"Pipeline not found"**: the existing empty-card layout, the id in mono, and a primary button "All pipelines" (`.btn--primary`, links to `#/`). The context bar is hidden.
- Read-only everywhere: no create, rename, delete or settings. Only counts and names are shown.

## 17. Reused components (no new visual language)
- Pills (`.pill`, `.pill--sm`) and their ok / warn / bad / running tones.
- Hero-number style (eyebrow label + large tabular number + mono step name) → card numbers.
- Segmented control → environment filter (as radios).
- Tabs → Latest | History (now links).
- Empty, error and info-banner cards → Home empty, unreachable, partial, no runs in env, not found.
- Skeleton shimmer → loading cards.
- Live indicator, theme toggle, focus ring, tokens: unchanged.
- New, small pieces only: `.pcard`, `.pgrid`, `.ctxbar`, `.backlink`, `.env-tag`, `.envbar`, `.btn--primary`.

