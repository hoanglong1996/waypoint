Implement the new "Home page, pipeline pages and environment filter" design for Waypoint Monitor.

## Design source (read first)
The design is in `docs/pipeline-monitor-degisn/` (I copied the new `waypoint-monitor` package over it).
Read these before you write code:
1. `CHANGES.md`: the top section "Home page, pipeline pages, environment filter" lists everything that changed.
2. `DESIGN_NOTES.md` §13–§17: Home page, pipeline header, environment filter, navigation and not found, reused components.
3. The prototype `index.html`, `styles.css` and `app.js`: open `index.html` in a browser. Go to `#/`, `#/p/callrail`, `#/p/callrail/history?env=qa` and `#/p/unknown`.
4. Screenshots in `screenshots/`: `H01–H05` (Home), `S01–S09` (Home states), `E01–E07` (History env filter), `P01–P08` (headers, env tag), `N01–N02` (not found).

The prototype is the reference for look and behaviour. Copy its CSS classes and markup structure. Do not copy its mock data or the "DESIGN TOOL" box (`<aside class="proto">` and the marked section at the end of `app.js`).

## What to build
1. **Routing** with hash addresses:
   - `#/` = Home (the new default page)
   - `#/p/<id>` = Latest
   - `#/p/<id>/history?env=<env>` = History
   - anything else = "Pipeline not found" with a link to `#/`
   - Reload, Back/Forward and shared links must open the same view. The page `<title>` follows the route.
2. **Header**: remove the pipeline picker and the `wp-pipeline` storage key. The brand links to `#/`. On pipeline pages add the context bar: "‹ All pipelines" back link, pipeline name, and Latest | History tabs as links with `aria-current="page"`.
3. **Home page**: a grid of pipeline cards (`.pgrid`, `.pcard`), one card per pipeline, based on the newest run in any environment.
   - Status mapping, first match wins: Running → Stale (> 26 h) → Incomplete (stopped or stalled) → Lost data → Completed.
   - Group "Needs attention" first (stale, incomplete, lost data), then the others. Sort A–Z inside each group.
   - Three numbers per card: first step, largest middle step, last step.
   - States: loading skeletons, empty, data store unreachable with a 30 s retry countdown, partial-data banner.
4. **Latest**: add the env tag (`.env-tag--lg`) right after the status pill. Also add it in the run drawer summary.
5. **History environment filter** (`.envbar`, radio-based `.segmented--env`, above Step trend):
   - It lists only envs that have runs, with prod first.
   - Default: prod if the pipeline has prod runs, else the env of the newest run.
   - It filters the trend, the runs list and the drawer. Changing it updates `?env=` and keeps focus on the chosen option.
   - The "No runs in this environment" state keeps the filter usable.

## Data
Use our real data layer, not the prototype's mock pipelines.
- Each run needs `env` (prod or qa).
- Home needs a list of pipelines with id, label and their runs (or at least the newest run).
- If the current API cannot give this, tell me what is missing before you invent anything.

## Rules
- Plain HTML/CSS/vanilla JS. No framework, no build step, no new libraries.
- Read-only: no create, rename, delete or settings. Counts and names only, no personal data.
- Keyboard-only use must work, with a visible focus ring. Never use colour alone (keep the text, icons and borders). Keep contrast in light and dark.
- No horizontal scroll at 375px.
- Do not change the graph view (`graph.js`) or other existing screens, except where CHANGES.md says so.

## How to work
1. First read the files above and the current code. Give me a short plan: which files you will change and any data gaps. Wait for my OK.
2. Build it in small steps: routing + header → Home → env tag → env filter → not found.
3. At the end, test at 1440px and 375px in both themes and compare with the screenshots. Also do the keyboard flow: Home → Enter on a card → History tab → change env → back link. Report what you checked and anything that differs from the design.
