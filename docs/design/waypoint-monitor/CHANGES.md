# Waypoint Monitor: Home page, pipeline pages, environment filter

Changed files: `index.html`, `styles.css`, `app.js`, `DESIGN_NOTES.md` (new §13–§17), `CHANGES.md`. `graph.js` is unchanged.
New screenshots: `H01–H05`, `S01–S09`, `E01–E07`, `P01–P08`, `N01–N02`. Removed: `h01–h05` (they showed the old picker).

## 1. Home page (new default, `#/`)
- Grid of pipeline cards (`.pgrid`, `.pcard`): 1 column at 375px, 2–3 on wider screens.
- Each card is one link to Latest: name, env tag, status pill (Completed / Incomplete / Lost data / Running / Stale), time since the run, and three hero numbers (first, largest, last step with step names).
- "Needs attention" group first (stale, incomplete, lost data), flagged with text + icon + border; the rest follow A–Z.
- States: loading skeleton cards, empty, data store unreachable with retry countdown, partial-data banner, long name, 20+ cards.

## 2. Header and pipeline pages
- **Removed**: the pipeline picker and the `wp-pipeline` storage key. The header row is now brand (links home) · live indicator · theme toggle.
- **New** context bar on pipeline pages: "‹ All pipelines" back link · pipeline name · Latest | History tabs. Tabs are now links with `aria-current`.
- Latest: an env tag (`.env-tag--lg`) right after the status pill. The run drawer shows the env tag too.

## 3. History: environment filter
- `.envbar` card above Step trend with a radio-based segmented control. Lists only envs with runs; default prod, else the newest run's env.
- Filters the trend, runs list and drawer. Stored in the address as `?env=`.
- New state: "No runs in this environment" (filter still usable).

## 4. Routing
- Hash routes: `#/`, `#/p/<id>`, `#/p/<id>/history?env=<env>`. Unknown → "Pipeline not found" with a link home.
- Mock data now has 4 pipelines with `prod` / `qa` runs. Design-time states `long` and `many` were added; `no-pipelines`, `?pipeline=` and `?tab=` were removed (use the address instead).

---

# Waypoint Monitor: design update

This replaces the `pipeline-monitor-graph-update` package. All four source files changed, so every file is included. Copy the folder over your design folder. Old screenshots are replaced; the new ones are listed in DESIGN_NOTES §12.

Kept as before: the History view, drawer, trend chart, banners, and the loading / empty / error / stale / partial-read / incomplete / data-loss screens (only renames and live states touch them).

## 1. Rename and header
- "Pipeline Monitor" is now **"Waypoint Monitor"** (`<title>`, brand, error text). The "CallRail × Google Ads" subtitle is gone.
- New brand mark and **favicon**: an indigo `#4f46e5` rounded square with a white path/waypoint glyph (inline SVG; the favicon is a data URI).
- The prod | qa segmented control is gone. In its place is a **pipeline picker**:
  - `#picker > select#pipeline-picker.select.select--picker`, max width 200px, sans font, visually hidden label "Pipeline".
  - Desktop order: `brand | tabs | spacer | picker | live + theme`. Under 720px it gets its own full-width row (40px tall) between the brand row and the tabs.
  - It lists the discovered pipelines by human label (mock: "CallRail calls", "Google Ads click view", "Meta Ads spend"). It is hidden when no pipelines are known (`state=no-pipelines`). The last choice is stored in `wp-pipeline`.
- Storage keys renamed: `wp-theme` (was `pm-theme`), `wp-pipeline` (new), `wp-steps-view` (was `pm-steps-view`).
- The "Preview state" box is now explicitly a **design-time tool**: it has a "DESIGN TOOL" tag and a comment in both index.html and app.js, its options are grouped, and new states were added. Delete it when you build the app.

## 2. Dynamic groups (8 colour slots)
- Tokens: `--grp-callrail/gads/merge/persist` are replaced by **`--grp-0 … --grp-7` and `--grp-N-bg`**, in all three token blocks.
  - Slots 0–3 keep the old teal, blue, violet and slate.
  - New slots: 4 amber `#b45309` / `#f0a35e`, 5 pink `#be185d` / `#f08cb6`, 6 green `#3f7d20` / `#8fd16a`, 7 brown `#8a5a2b` / `#d3a574`.
  - Each `-bg` is about 5% alpha.
- Classes: `.gband--*`, `.gband-label--*` and `.gdot--*` are removed. **`.g-0 … .g-7`** set `--g` / `--g-bg`, and `.gband`, `.gband-label` and `.gdot` read those variables. The same classes are used in the list group headings and step-map labels.
- Groups, titles and slots are read from the run (declaration order).

## 3. Live steps
- New tokens: `--running: var(--accent)`, `--running-bg: var(--accent-soft)`.
- New classes:
  - list: `.step--running / --waiting / --stalled`, `.step__progress`, `.step__count--running / --stalled`, `.step__wait-msg`
  - graph: `.gnode--running / --waiting / --stalled`, `.gpill--running / --waiting / --stalled`
  - step map: `.flow__cell--running / --waiting / --stalled`
  - other: `.pill--running`, `.t-run`, `.t-wait`, `.spin`
- Elapsed timers (`.js-elapsed[data-since]`) are updated every second: "42 s", "3m 05s", "1h 02m".
- Hero:
  - Running: title "A run is in progress"; the body names the running step, or says "Started, waiting for the first step to report."; "finished … ago" and the duration are hidden; KPI placeholders say "in progress" (otherwise "not reported").
  - Stalled: title "Run stalled at a step", plus how long and the usual time.
- Graph header summary adds "running `<step>`" and "stalled at `<step>`".
- Edges that touch a running or waiting step are drawn as **pending** (`.gedge--pending`).
- Legend: a new "Live" group.
- Reduced motion: the spinner becomes a static partial ring, the progress bar a static 40% segment, and the pulse ring is not drawn.

## 4. Self-describing graph
- The graph is drawn from **each run's flow description**, using a generic layered layout in `graph.js`:
  - layers by longest path, dummy waypoints on long edges, barycenter ordering, block placement;
  - `col` and `row` hints are respected;
  - loops drop the edge that points furthest back in declaration order.
- `.graph-other`: an "Other steps" row for reported steps that are not in the flow. The chips select the step. In the list these steps go under the heading "Not in this run's flow" and get a `not in flow` pill.
- `.gedge--dangling`: an input from a step outside the flow is drawn as a short dashed warn stub (1.5px, `3 3`, with an arrowhead). Its text reads "from X (not in this flow)".
- **Simple mode** (`.graph-simple`): when a run has no usable flow description, steps are shown in the order they reported, with no edges, no bands and no Arrows legend. The `.graph-notice` above shows one of three texts (missing / unreadable / newer version).
- `.graph-problems`: a collapsed `<details>` with the warn summary "Problems in this run's description (N)" and a wrapping list.
- Labels: the list title is "Label · technical_name"; graph nodes show the label; tooltips and aria text include both.

## 5. Code structure (app.js)
- `model(run)` is the one normalised view of a run: steps, other steps, groups and slots, edges, dangling inputs, problems, states and the affected set. Every screen uses it.
- KPIs, the trend step and the history columns come from per-pipeline data (`pipe.kpis`), not from code.
- New mock scenarios: `running`, `running-start`, `stalled`, `other`, `simple-missing`, `simple-unreadable`, `simple-version`, `no-pipelines`.

## 4. Died state (spec 009, added in code, not produced by the design tool)

Built directly in `waypoint_monitor/static` from the existing tokens and the Stalled pattern; the files in this folder were not regenerated, so they do not show it. Screenshots of the real UI were taken on 2026-10-16 (`.playwright-mcp/spec009-*.png`, local only).
- New state `died` for a step and a run: the pipeline's process is gone (no heartbeat for 90 s). Permanent once shown.
- Error colour (`--bad`) and a **solid** border, versus Stalled (warn colour, dashed border). Icon `I.power`. No animation.
- Classes: `.gpill--died`, `.gnode--died`, `.step--died`, `.flow__cell--died`, `.step__live-sub`.
- Home card: status pill "Died", line "last seen N ago", reason "Died at <step> (the process is gone)", in the needs-attention group.
- Run page: status pill "Died", title "The pipeline process died", step list shows "Died · last seen hh:mm:ss / process gone", graph node shows "last seen hh:mm:ss", legend gains a Died entry.
- Wording: Stalled = "alive but not progressing", Died = "process gone".
