---

description: "Task list for Pipeline Directed Graph View"
---

# Tasks: Pipeline Directed Graph View

**Input**: `/specs/003-pipeline-directed-graph/` (spec, plan, research, data-model, contracts/ui.md) and the approved design `docs/design/pipeline-monitor-graph-update/` (`DESIGN_NOTES.md` §8, `graph.js`, `styles.css` §10, `screenshots/graph/`).

**Tests**: `node --test` unit tests for the pure graph rules, plus one backend contract test.

**Organization**: Grouped by user story. Paths are under `performance_monitoring_app/` unless stated. Front end only. Do not copy from the prototype: the preview switcher, mock data, fixed NOW date, `?state=` and `?select=` params.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Design approved and saved in `docs/design/pipeline-monitor-graph-update/`
- [X] T002 [P] Add a contract test in `tests/test_api.py` asserting every `expected_steps[].inputs[]` in `/api/config` has a non-empty `from` naming an existing step, every step has a `group`, and the graph is acyclic with 9 input links

## Phase 2: Foundational (pure rules + shared refactors; blocks all stories)

- [X] T003 Create `static/js/graph-model.js` with `edgesOf(expectedSteps)` (one edge per consumer input: `from`, `to`, `input`, `k`, `n`; 9 total) and the front-end position table keyed by step name (label, col, row, per research §3 / DESIGN §8.3) with `partition(expectedSteps)` returning `{placed, other}` so unknown steps go to "Other steps"
- [X] T004 [P] Add `nodeStates(run)` in `static/js/graph-model.js`: states in this order `stopped` (first missing), `unreached` (later missing), `loss`, `ok`; `affected` = `ok` nodes transitively downstream of a `loss` node. Import `isLoss` from `static/js/model.js`; do not duplicate it
- [X] T005 [P] Add `edgeInfo(run, edge)` (`inactive` if producer or consumer missing, `empty` if count 0, else `ok`; count = consumer's recorded input value), `edgeWidth(value, max)` = `1.25 + 2.75 × log10(value+1)/log10(max+1)` px, and `neighbours(edges, i)` (direct only) in `static/js/graph-model.js`
- [X] T006 [P] Add `pickLayout(containerWidth, prefer)` in `static/js/graph-model.js`: width < 600 → `tb`; ≥ 880 and `prefer !== 'compact'` → `lr` with scale `min(1, w/1138)`; otherwise `compact` with scale `min(1.35, w/628)`
- [X] T007 Write `static/tests/graph-model.test.mjs` covering: 9 edges; merge has 3 incoming, `read_instances` 2 outgoing; stopped vs unreached; loss; affected set; edge states and counts; edge width at min and max; neighbours of merge and a source; `pickLayout` at 375, 600, 879, 880, 1440 and with `prefer: 'compact'`; `partition` puts an unknown step in `other`; shape identical across runs; run `node --test static/tests`
- [X] T008 [P] Extract `stepItemHTML(run, runs, i, compact)` from `stepsHTML` in `static/js/views/latest.js` (export it) and make `stepsHTML` call it; no visual change to the list
- [X] T009 [P] Add the `pm-steps-view` helpers `getStepsView()`/`setStepsView()` (values `list|graph`, default `graph`, try/catch around storage) and any missing icons (flow, list, graph, octagon, gap, down, arrowIn; take SVG from the design's `app.js`) in `static/js/ui.js`

**Checkpoint**: tests pass; list view unchanged.

## Phase 3: User Story 1 - See how data flows between steps (P1) 🎯 MVP

**Goal**: Latest run shown as a directed graph with labelled arrows.

**Independent Test**: Open the latest run in Graph view; 9 nodes, 9 arrows, no crossings, labels and counts match the stored records (compare with `screenshots/graph/g01`).

- [X] T010 [US1] Add tokens `--grp-callrail/gads/merge/persist` (+ `-bg`) and `--edge`, `--edge-hl`, `--edge-empty`, `--edge-inactive`, `--edge-flow` to the light block AND both dark blocks of `static/styles.css`, plus section 10 "GRAPH VIEW" from the design's `styles.css` (incl. reduced-motion rule hiding `.gedge__flow`)
- [X] T011 [US1] Create `static/js/views/graph.js` exporting `mountGraph(el, {run, runs, mode, details, prefer, ghostMsg, selected})` and `refresh(el)`: build the layout (desktop LR, compact LR, top-to-bottom 2 lanes per DESIGN §8.3–8.5, constants from the design), group bands, SVG edges (hit, line, flow paths; path arrowheads, skip edge routing, Merge ports at 1/4, 2/4, 3/4), edge chips (desktop and phone only), node buttons in tab order (account, partners, call, instances, campaigns, clickview, merge, record, save), scale transform with reserved stage height. Escape every API-derived value
- [X] T012 [US1] In `static/js/views/graph.js` add the graph header ("Data flows left to right/top to bottom. An arrow A → B means A's output is B's input."), the "Other steps" row for unplaced steps (unconnected nodes), and a debounced (120 ms) resize relayout that keeps `selected`
- [X] T013 [US1] Add the "List | Graph" radio segmented control to the Steps head in `static/js/views/latest.js` and mount the graph or the list per `getStepsView()`; re-render on change
- [X] T014 [US1] Check no horizontal page scroll at 375, 600, 768, 1024, 1440 px and legibility in light and dark against `g01`, `g05`, `g08`

**Checkpoint**: US1 works alone and is demoable.

## Phase 4: User Story 2 - Spot loss or a stopped run on the graph (P1)

**Goal**: Health, stop point and downstream impact visible.

**Independent Test**: seeded loss and stopped runs match `g02` and `g03`.

- [X] T015 [US2] Render node states in `static/js/views/graph.js`: Fine (check), Data loss (octagon, red tint), Not reported (amber, dashed + hatched), Not reached (grey, dashed + hatched), each with icon + word; "affected" dashed amber pill and border on affected nodes; "n/a · returns nothing" for null output; full `aria-label` per node
- [X] T016 [US2] Render edge states in `static/js/views/graph.js` and `static/styles.css`: ok solid with width from `edgeWidth`, empty red short dashes with chip "0", inactive grey long dashes with chip "—"; flow animation only on ok edges
- [X] T017 [US2] Add the summary line ("N of 9 steps reported", "stopped at <step>", "data loss at <step>") and the legend (steps, arrows, groups; compact hint) in `static/js/views/graph.js`
- [X] T018 [P] [US2] Ensure the fake store in `tests/fakes.py` can seed a loss run (`read_campaigns` output 0) and a stopped run (before `read_gads_clickview`) for the quickstart; add them if absent

## Phase 5: User Story 3 - Explore a step and its neighbours (P2)

**Goal**: Selection, tooltips, Selected-step panel, History drawer.

**Independent Test**: matches `g04`, `g06`, `g09`; Esc behaviour as in the quickstart.

- [X] T019 [US3] Implement selection in `static/js/views/graph.js`: click/Enter/Space selects (`aria-pressed`, accent ring), second click or empty-space click clears, highlight direct upstream/downstream nodes, edges and chips and dim the rest (nodes .38, edges .18), turn off flow animation while selecting
- [X] T020 [US3] Render the "Selected step" panel in `static/js/views/graph.js` using `stepItemHTML` from `views/latest.js` (do not duplicate card markup), with Upstream/Downstream jump buttons and a clear button
- [X] T021 [US3] Add node and edge tooltips (hover and focus) to `static/js/views/graph.js` per DESIGN §8.6; reuse the page's tooltip element
- [X] T022 [US3] Add the capture-phase Escape handler in `static/js/views/graph.js`: clears the selection and refocuses the node, and stops propagation so in the drawer the first Esc clears and the second closes it
- [X] T023 [US3] Show the List | Graph control and the compact graph in the History drawer in `static/js/views/history.js` (`prefer: 'compact'`), sharing the same choice; keep selection through the automatic refresh in `static/js/app.js`

## Phase 6: Polish

- [X] T024 [P] Loading skeleton graph (`mode: 'skeleton'`) and empty ghost graph (`mode: 'ghost'`, "No runs yet for <env>") in `static/js/views/graph.js` wired from `static/js/views/latest.js` and `static/js/ui.js`; error card still replaces the graph (FR-014)
- [X] T025 [P] Update `README.md` (graph view, `pm-steps-view`, design source) and mark the new files in this feature's quickstart if steps changed
- [ ] T026 (partly done: checked 1440/960/375 px, loss and stopped runs, drawer, Esc order, toggle, skeleton and ghost in a browser; not yet a screenshot-by-screenshot light/dark comparison or keyboard-only pass) Run the quickstart (all 12 steps), compare each of `screenshots/graph/g00`–`g09` in light and dark at 1440, 960 and 375 px plus the drawer, check keyboard-only use (Tab column by column, Enter selects, Esc clears), and list any difference from the design that could not be fixed
- [X] T027 Run `node --test static/tests` and `python -m unittest discover tests`; fix failures

## Dependencies & Order

- T003 first; T004, T005, T006 [P] after it; T007 after T003–T006. T008 and T009 are independent [P].
- US1 (T010–T014) after Foundational. T011 before T012, T013.
- US2 and US3 both extend `views/graph.js`: do US2 (T015–T017) then US3 (T019–T022); T018 any time.
- T023 after T019–T022. Polish last.

## Parallel Examples

- Start together: T002, T003, T008, T009.
- After T003: T004, T005, T006.
- During US2: T018 alongside T015–T017.
- Polish: T024 and T025.

## Implementation Strategy

- **MVP**: Phases 1–3 (US1): readable directed graph with labelled arrows and the toggle. Then US2 (health states), then US3 (exploration, drawer).
- The list view remains the fallback behind the toggle.
