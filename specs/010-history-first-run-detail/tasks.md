---

description: "Task list for History-First Pipelines with Run Detail Pages"
---

# Tasks: History-First Pipelines with Run Detail Pages

**Input**: Design documents from `/specs/010-history-first-run-detail/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/routes.md, quickstart.md

**Tests**: Included. The constitution (principle IV) requires tests for changed behaviour, and the plan names `node --test` tests for routing and view rules. No server change, so no Python tests are added.

**Organization**: Grouped by user story. All paths are relative to `integrations/callraill/waypoint_monitor/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2, US3 (from spec.md)

## Phase 1: Setup

- [X] T001 Run the baseline before changing anything: `node --test static/tests/*.test.mjs` and `python -m unittest discover tests`; note any failing tests in `specs/010-history-first-run-detail/quickstart.md` under a "Baseline" heading so later failures can be attributed

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: The route model and the generalised run renderer that US1, US2 and US3 all depend on.

- [X] T002 Rewrite `static/tests/router.test.mjs` for the new contract (`specs/010-history-first-run-detail/contracts/routes.md`): `#/p/callrail` parses to `{name:'pipeline', id:'callrail', page:'history', env:null}`; `#/p/callrail/history?env=qa` keeps `env`; `#/p/callrail/runs/prod/20261015T020000Z` parses to `{name:'run', id:'callrail', env:'prod', runId:'20261015T020000Z'}`; a `runId` not matching `^\d{8}T\d{6}Z$`, an empty `env`, or extra segments → `{name:'notfound', id:'callrail'}`; ids with spaces and slashes round-trip through `buildRoute`; `routeTitle` gives `<Pipeline> · History · Waypoint Monitor` and `<Pipeline> · <label> · Waypoint Monitor` for a run. Run it and confirm it fails
- [X] T003 Update `static/js/router.js`: add the `run` route (`#/p/<pipeline>/runs/<env>/<runId>`, validation per data-model.md), make `#/p/<pipeline>` resolve to `page: 'history'`, remove the `latest` page, extend `buildRoute` and `routeTitle`, update the header comment. Make T002 pass
- [X] T004 [P] Add a test in `static/tests/state.test.mjs` (or a new `static/tests/run-view.test.mjs`) for a pure helper `findRun(runs, runId)` in `static/js/model.js` returning the run or `null`, and for `isNewest(runs, run)`; cover empty list and unknown id
- [X] T005 Implement `findRun` and `isNewest` in `static/js/model.js` so T004 passes
- [X] T006 Rename `static/js/views/latest.js` to `static/js/views/run.js` (use `git mv`) and update its importers (`static/js/views/history.js`, `static/js/app.js`, `static/tests/*.mjs` if any); no behaviour change yet. Run `node --test static/tests/*.test.mjs` and confirm the same results as T001

**Checkpoint**: Route parsing and the renamed module are in place; app behaviour is still the old one.

---

## Phase 3: User Story 1 - A pipeline opens on its history (Priority: P1)

**Goal**: Selecting a pipeline (card or address) opens its history; there is no Latest page or tab.

**Independent Test**: With runs recorded, select a card on the home page and confirm history opens; open `#/p/<pipeline>` directly and confirm history; confirm no "Latest" tab exists.

- [X] T007 [US1] In `static/js/app.js` change `currentView()` and `render()` so a `pipeline` route is always the `history` view: remove the `latest` branches, the `view-latest` skeleton and `renderLatest` calls, and in `refresh()` drop the merged-environment fetch (`loadRuns(state.cfg.environments, card.name)` with no env) so every pipeline route loads the applied environment only
- [X] T008 [P] [US1] In `static/index.html` remove the `Latest | History` tab nav (`#tab-latest`, `#tab-history`, `<nav class="tabs">`) and the `view-latest` section; keep the back link and pipeline name in `#ctxbar`
- [X] T009 [US1] In `static/js/app.js` update `syncHeader(view)` for the removed tabs (no `tab-latest`/`tab-history` lookups) and `showView()` (views: `home`, `history`, `run`, `notfound`)
- [X] T010 [P] [US1] In `static/styles.css` remove the now-unused `.tabs`, `.tabs__tab` and `.ctxbar .tabs` rules (including the phone-width rules near the end of the file) and make sure the context bar still lays out at phone width
- [X] T011 [P] [US1] In `static/js/views/home.js` keep the card link `href="#/p/<id>"` (it now resolves to history, per contracts/routes.md); update any comment or `aria-label` text that says it opens the latest run to say it opens the run history
- [X] T012 [US1] Update `static/js/app.js` banners: `renderBanners` uses `view.card.latest` for the stale banner; keep it on the history view only and make sure it still reads correctly without a Latest page
- [X] T013 [US1] Update `README.md` page-address table (`#/p/<pipeline>` is now History; add the run address) and remove "Latest tab" wording near the List | Graph paragraph
- [X] T014 [US1] Run `node --test static/tests/*.test.mjs`, fix any test that asserted Latest behaviour (`static/tests/layout.test.mjs`, `static/tests/overview.test.mjs`), then follow steps 2 and 8 of `specs/010-history-first-run-detail/quickstart.md`

**Checkpoint**: US1 works alone: pipelines open on history. Runs still open in the drawer at this point.

---

## Phase 4: User Story 2 - A run opens as its own detail page (Priority: P1)

**Goal**: Selecting a run navigates to a full page for that run; the drawer is gone.

**Independent Test**: From history select an older run, confirm a full page with that run's status, counts and steps, no side panel, reload keeps it, back returns to the same filtered history, and a wrong run id shows "Run not found".

- [X] T015 [P] [US2] Add a test in `static/tests/run-view.test.mjs` for a pure helper `heroTitle(analysis, isNewest)` (move the title logic out of `heroHTML` into `static/js/model.js`): newest and complete → existing wording; not newest and complete → "Run completed"; the died, running, stopped and loss titles are unchanged for both. Confirm it fails
- [X] T016 [US2] Implement `heroTitle` in `static/js/model.js` and use it in `heroHTML` in `static/js/views/run.js` so T015 passes; also make the stale pill and banner text apply only when the run is the newest (`isNewest`)
- [X] T017 [US2] Replace `renderLatest(el, runs, cfg)` in `static/js/views/run.js` with `renderRun(el, run, runs, cfg)` that renders the given run (hero, steps head, list or graph) instead of `runs[0]`; keep ids `latest-graph` and `latest-graph-details` renamed to `run-graph` and `run-graph-details`, and update `static/js/app.js` callers
- [X] T018 [US2] In `static/index.html` add `<section id="view-run" class="view" aria-label="Run details" hidden></section>` and remove the whole `#drawer` block (scrim, panel, header, body)
- [X] T019 [US2] In `static/js/views/history.js` make each run row an anchor `<a class="run-row" href="#/p/<pipeline>/runs/<env>/<runId>">` (build the href with `buildRoute`, using the row's `r.env` and `r.id`; pass the pipeline id into `renderHistory` via its existing `envInfo` argument or a new `pipelineId` argument); remove `openDrawer`, `closeDrawer`, `fillDrawer`, `refreshDrawer`, `syncDrawer`, `wireDrawer`, `selectedRunId`, the `openRunId`/`lastFocus`/`drawerWired` state and the row click handler
- [X] T020 [US2] In `static/js/app.js` add the run view: `currentView()` returns `{kind:'run', ...}` for a `run` route, `refresh()` loads `loadRuns([route.env], route.id, route.env, 100)` (add an optional `limit` argument to `loadRuns` in `static/js/api.js`, default 30), `render()` calls `renderRun($('view-run'), findRun(...), state.runs, cfg)`; when the pipeline is known but `findRun` returns `null` the view is `runnotfound`. Remove every `closeDrawer`, `refreshDrawer`, `wireDrawer` import and call and the drawer lines in the `hashchange` and `change` listeners (the List | Graph handler re-renders the run view instead)
- [X] T021 [P] [US2] In `static/js/ui.js` add `runNotFoundHTML(pipelineId, env)` ("Run not found" heading, text that the run may have expired or the address is wrong, button linking to `#/p/<pipeline>/history` plus `?env=<env>` when `env` is non-empty) and a loading skeleton for the run view reusing `skeletonHTML`
- [X] T022 [US2] In `static/js/app.js` update `syncHeader(view)` for the run view: breadcrumb `All pipelines › <pipeline label> › <run date and time>` where the pipeline label links to `#/p/<pipeline>/history?env=<run env>` and acts as the back control (FR-006, FR-007); update `document.title` through `routeTitle`; and include the run id in the redraw `sig` so an in-progress run keeps updating (FR-008)
- [X] T023 [P] [US2] In `static/index.html` and `static/styles.css`: add the breadcrumb markup to `#ctxbar` (a separator and a run-time element, hidden except on the run view) and style it; remove the `.drawer*` rules, the "drawer" mentions in the section index and the `.drawer` overrides (`.drawer .kpis`, `.drawer .kpi__value`, the phone-width rule); make `.run-row` look the same as the old button (anchor reset: `display`, `color`, `text-decoration`)
- [X] T024 [US2] Run `node --test static/tests/*.test.mjs`; then follow steps 3 to 7, 9 and 10 of `specs/010-history-first-run-detail/quickstart.md` in a browser (seed with `tests/seed_demo.py`), including the phone-width check

**Checkpoint**: US1 and US2 work together: history first, runs open as full pages, no drawer.

---

## Phase 5: User Story 3 - The latest run is one selection away (Priority: P2)

**Goal**: The newest run is the first history row and opens like any other; new runs appear at the top without losing place or filter.

**Independent Test**: Open history, select the first row and confirm it is the newest run in the applied environment; seed a newer run and confirm it appears on the next refresh with the filter unchanged.

- [X] T025 [US3] Add a test in `static/tests/run-view.test.mjs` that, for runs sorted newest first (as `loadRuns` returns them), the first history row's route is the route of `runs[0]` and `isNewest(runs, runs[0])` is true; and that a refresh with an extra newer run keeps the same route for the applied environment
- [X] T026 [US3] In `static/js/views/history.js` mark the first row with a small "Newest" tag (text, not colour only) so the shortcut to the latest run is visible; style it in `static/styles.css`
- [X] T027 [US3] Verify the periodic refresh in `static/js/app.js` redraws history when a newer run arrives (`runSignature` changes) and does not reset the environment filter or scroll position beyond what the old drawer-free history did; follow quickstart step 6 with a seeded newer run

**Checkpoint**: All three stories work.

---

## Phase 6: Polish & Cross-Cutting

- [X] T028 [P] Search the front end for leftovers: `grep -rn "drawer\|latest-graph\|view-latest\|tab-latest\|renderLatest\|page: 'latest'" static README.md` and remove or reword every hit that refers to the removed features (keep `card.latest`, which is the home-card data)
- [X] T029 [P] Update `specs/008-pipelines-home-page/contracts/routes.md` with a one-line note at the top that `specs/010-history-first-run-detail/contracts/routes.md` supersedes its address table
- [X] T030 Run the full verification: `node --test static/tests/*.test.mjs`, `python -m unittest discover tests`, and all ten steps of `specs/010-history-first-run-detail/quickstart.md`; record the date and results in a "Results" section at the end of quickstart.md
- [ ] T031 Check accessibility of the new pages by keyboard only: run rows are focusable links and Enter opens them, the breadcrumb back link is reachable, the page heading of the run view receives focus on open (research.md section 8), and nothing traps focus

---

## Dependencies & Execution Order

- **Phase 1** first. **Phase 2** blocks everything else (T002 → T003; T004 → T005; T006 after T003).
- **US1 (Phase 3)** needs Phase 2. **US2 (Phase 4)** needs Phase 2 and the `view-latest` removal from T007 to T009, so do it after US1. **US3 (Phase 5)** needs US2 (the run rows must be links).
- Within a story: tests first (T002, T004, T015, T025), then implementation, then the manual check.
- US1 can ship alone as an intermediate step (the drawer still works), but the full request is US1 + US2.

## Parallel Opportunities

- Phase 2: T004 alongside T002/T003 (different files).
- US1: T008, T010 and T011 are in different files and can run together once T007 is decided.
- US2: T015 with T021 and T023 (test, `ui.js`, markup/CSS) can run together; T019, T020 and T022 all touch `app.js` or `history.js` and should be done in order.
- Polish: T028 and T029.

## Implementation Strategy

- **MVP**: Phases 1 to 4 (US1 + US2). This is the whole request: history first, runs as pages, no right panel.
- **Increment**: US3 adds the visible shortcut to the newest run and refresh checks.
- **Note on cards**: the home card shows the newest run across environments, while history opens on the default environment (prod when present). If the newest run is in qa, the card and the first history row can differ. The spec leaves this unchanged; if it matters later, link the card to `?env=<latest env>`.

## Implementation notes (2026-10-16)

- Applied the analysis findings while building: card link carries the latest run's environment (I1); an unknown run environment is not requested and shows "Run not found" (G1); the unreadable-records banner also shows on run pages (G2); heading focus is implemented (G3); `ui.js` skeleton ids renamed (G4); `runRoute` helper added and tested (G5).
- T031 is left open: run rows are native links and the heading focus was verified in a browser, but a keyboard-only pass was not done.
