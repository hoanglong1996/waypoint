---

description: "Task list for Pipelines Home Page"
---

# Tasks: Pipelines Home Page

**Input**: Design documents from `/specs/008-pipelines-home-page/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, contracts/routes.md, quickstart.md

**Tests**: Included, because the constitution (IV) requires tests for changed behaviour. Python tests use the fake store (no live Redis); front-end rules are tested with `node --test` and no DOM.

**Organization**: grouped by user story. All paths are relative to `integrations/callraill/waypoint_monitor/` unless they start with `specs/`. Run commands from that folder.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 home page and card navigation · US2 history environment filter · US3 new and stale pipelines, refresh

## Notes from implementation

- The approved design in `docs/design/waypoint-monitor/` changed several plan details; spec, contracts, data model and research were updated to match (card status order, "largest step between first and last", attention group, filter options prod-first, an `env` without runs is kept, a new history entry per filter change).
- `/api/overview` returns `card_status` and `needs_attention` (not `attention`), and `latest` also carries `first_missing_step`, `stalled_step`, `stalled_seconds` and `unreadable` for the card's reason line and the stale banner.
- T009: `choosePipeline` and its two tests were removed with the picker (`static/tests/picker.test.mjs` deleted, the test in `static/tests/model.test.mjs` removed).
- T015 was not run in parallel with T010 (same test file), as the dependency section says.
- T027 was run against a fake store in a browser (home, history filter, no-runs environment, not found, error and retry, empty store, 375 px width, keyboard from Tab to Enter on a card). Dark theme was not re-checked: the new CSS only uses existing tokens. Focus returns to the page start after a card is opened (the card is replaced); the design does not specify otherwise.
- Not done here (outside this feature): Facebook and Google Ads reporting their own runs.

## Rules for the whole change

- Do not reformat files wholesale. Run `black` and `ruff --fix` only on Python files you edited, then check `git diff --stat` shows no unrelated files. The working tree already has unrelated uncommitted changes in `src/`, `main.py` and other files: do not touch or stage them.
- `/api/config`, `/api/health`, `/api/pipelines` and `/api/runs` keep their shape (contracts/api.md, "Unchanged").
- Nothing new is stored in Redis. Counts and names only; no free-form record content in any response (constitution II).
- The front end has no build step: plain ES modules, no new dependencies.

---

## Phase 1: Setup

- [X] T001 Record the "before" results: run `python -m unittest discover tests` and `node --test static/tests` in `waypoint_monitor/`, then write the pass/fail counts and the names of any failing tests to `specs/008-pipelines-home-page/before-results.md`, so later runs show what this feature changed.

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: the overview data, the routing shell and the API client that every story uses.

- [X] T002 [P] Write failing tests for the overview rules in `tests/test_overview.py` using `tests/fakes.py`: newest run across environments wins by greatest `run_id`; equal ids go to the environment listed first in `ENVIRONMENTS`; `environments` lists only environments with runs, in `ENVIRONMENTS` order and never empty; attention order is `stale` > `incomplete` > `loss` > `running` > `ok`, `none` last, ties by `label` A to Z (data-model.md "Attention rank"); a run matching several states takes the first match.
- [X] T003 [P] Write failing front-end tests in `static/tests/router.test.mjs` for pure route parsing and building (contracts/routes.md): `#/` and empty hash give home; `#/p/<pipeline>` gives latest; `#/p/<pipeline>/history` and `?env=<env>` give history with that env; pipeline names are URL-encoded and decoded; an unknown shape gives "not found"; building a route from parts round-trips.
- [X] T004 Implement `app/domain/overview.py`: a function that takes, per environment, the built runs of each pipeline and returns the `PipelineSummary` list from data-model.md (fields `name`, `label`, `environments`, `attention`, `latest` with `run_id`, `env`, `status`, `stale`, `started_at`, `ended_at`, `age_seconds`, `loss_steps`, `headline`). `headline` is three items `{key, label, value}` for keys `first`, `peak`, `last`, with `value` null when absent, using the same rules as `headline()` in `static/js/model.js` (first step that reported; step with the largest metric; last step with a value; metric = output, or first input when output is null). Make T002 pass. Fully typed (mypy strict).
- [X] T005 Add `GET /api/overview` to `app/api/routes.py` per contracts/api.md: for every pipeline name found in any configured environment, reuse the existing cached `build(env, pipeline, moment)`, pass the results to `app/domain/overview.py`, return `generated_at`, summed `unreadable_total`, and `pipelines` already in attention order; an empty store returns 200 with `pipelines: []`; `StoreUnavailable` returns 503 `{"error": "Data store unavailable"}`.
- [X] T006 [P] Add API tests in `tests/test_api.py` for `/api/overview`: shape and fields exactly as contracts/api.md (no extra fields), prod and qa runs of one pipeline give one card with the newer run and its `env`, a pipeline only in qa still appears, empty store returns an empty list with 200, store failure returns 503, and `/api/pipelines` and `/api/runs` responses are unchanged.
- [X] T007 [P] Implement `static/js/router.js`: pure `parseRoute(hash)` and `buildRoute(route)` per contracts/routes.md, exporting route kinds `home`, `latest`, `history`, `notfound`. Make T003 pass. No DOM access.
- [X] T008 [P] Add `loadOverview()` to `static/js/api.js` returning the `/api/overview` body mapped to camelCase with `latest.startedAt`/`endedAt` as `Date`; change `loadRuns(environments, pipeline)` so it accepts an optional single `env` and, when given, calls only `/api/runs?env=<env>&pipeline=<pipeline>&limit=30` (keep the merged behaviour when no `env` is given).
- [X] T009 Replace the dropdown and tab state with a route-driven shell in `static/js/app.js` and `static/index.html`: remove `#pipeline-select`, `choosePipeline` use and the `wp-pipeline` local-storage code; keep theme, banners, live indicator, polling, retry and visibility handling; listen to `hashchange` and render the view for the current route; make the product name link to `#/`; on pipeline pages show a back link to `#/`, the pipeline name and the Latest | History tabs as links to `#/p/<pipeline>` and `#/p/<pipeline>/history`. An unknown pipeline renders "Pipeline not found" with a link to `#/`. Existing Latest and History views must render unchanged for a valid pipeline. Remove or update `static/tests/picker.test.mjs` to match (the picker rule is gone).

**Checkpoint**: `/api/overview` works, routes parse, the shell navigates between placeholder views, and existing tests pass.

---

## Phase 3: User Story 1 - Pick a pipeline from a home page (Priority: P1)

**Goal**: A home page lists every reporting pipeline as a card; selecting a card opens that pipeline's Latest page.

**Independent Test**: With runs for several pipelines, open `#/`, confirm one card per pipeline with correct status, environment label, age and three counts, problems first; select a card and land on `#/p/<name>`; reload and still be there; the back link returns home.

- [X] T010 [P] [US1] Write front-end tests in `static/tests/overview.test.mjs` for the card rules in `static/js/model.js`: card status label from `attention` and `status`; "time since run" wording reuses the existing `ago` helper; headline values with null show "—"; environment label text; cards stay in the server's order.
- [X] T011 [US1] Add the pure card helpers tested in T010 to `static/js/model.js` (no DOM). Make T010 pass.
- [X] T012 [US1] Implement `static/js/views/home.js`: render one card per pipeline from the overview as a focusable link to `#/p/<name>` showing `label`, status pill (reuse `statusPill`, `lossPill`, `stalePill` from `static/js/ui.js`), an environment label, time since run, and the three headline numbers with their step labels. Pipelines with `attention` other than `ok` get a visible flag. Include empty state (reuse `noPipelinesHTML` text: pipelines appear after their first run), error state with retry (reuse `errorHTML`), and the "some records could not be read" notice when `unreadable_total` > 0.
- [X] T013 [US1] Wire the home route in `static/js/app.js`: on `#/` load `loadOverview()` on the existing polling cycle and render `views/home.js`; a card link opens the Latest route, which loads runs for that pipeline merged across environments so it shows the same run the card showed (spec Assumptions).
- [X] T014 [P] [US1] Add card, grid and flag styles to `static/styles.css`: cards wrap to one column at phone width with no horizontal scroll (FR-015), long names truncate without overlap, visible keyboard focus, light and dark themes.

**Checkpoint**: US1 works alone: home page, card navigation, reload and back link. This is the MVP.

---

## Phase 4: User Story 2 - Filter a pipeline's history by environment (Priority: P2)

**Goal**: The History page has an environment filter that limits runs, run details and step trends to one environment, kept in the address.

**Independent Test**: With prod and qa runs for one pipeline, open its History, choose `prod` then `qa`: only that environment's runs, trend and details show; reload keeps the choice; an environment with no runs is not offered; a bad `?env=` falls back to the default.

- [X] T015 [P] [US2] Write front-end tests in `static/tests/overview.test.mjs` (same file as T010; add after it) for the filter rules: default is `prod` when the pipeline has prod runs, otherwise the environment of its newest run; an `env` not in the pipeline's `environments` falls back to the default; keeping `env` when moving to another pipeline only if that pipeline has runs in it; no environments gives no filter.
- [X] T016 [US2] Add the pure rules from T015 to `static/js/model.js` as `defaultEnv(summary)` and `resolveEnv(summary, requested)`. Make T015 pass.
- [X] T017 [US2] Add the "Environment" select to `static/js/views/history.js`: a native select labelled "Environment" listing only the pipeline's `environments`, always showing the applied one (also when there is only one). Changing it updates `?env=` in the address with `location.replace` (no extra history entry) and reloads the runs.
- [X] T018 [US2] Wire the history route in `static/js/app.js`: resolve `env` with `resolveEnv`, correct an unknown `?env=` in the address without adding a history entry, fetch `loadRuns(environments, pipeline, env)` for that single environment, and pass those runs to the run list, the step trend chart and the run drawer so all three are limited to that environment (FR-009). Carry `env` over when the operator opens another pipeline's History and that pipeline has runs in it.
- [X] T019 [US2] Show the "no runs in this environment" message in `static/js/views/history.js` when the chosen environment returns no runs, keeping the filter usable. Add the filter's styles to `static/styles.css`.

**Checkpoint**: US1 and US2 both work; History is filterable and shareable by address.

---

## Phase 5: User Story 3 - See new and quiet pipelines without configuration (Priority: P3)

**Goal**: New pipelines appear on their own, stale ones are marked, and an open page stays current.

**Independent Test**: Write a first run for a new pipeline name: its card appears on the next refresh. Set `STALE_HOURS=0.001`: cards of finished runs are marked stale. Leave the page open: "Updated … ago" keeps counting and cards refresh.

- [X] T020 [US3] Extend `tests/seed_demo.py` to also write demo `facebook` and `google_ads` pipelines (own flow, a few steps, counts) alongside `demo`, in the given environment, using only the key layout in `specs/007-rename-to-waypoint/contracts/redis-keys.md`; accept an optional pipeline name argument so a new pipeline can be added on demand for the quickstart.
- [X] T021 [P] [US3] Add an API test in `tests/test_api.py` that a pipeline written to the fake store after a first `/api/overview` call appears on the next call once the cache window has passed, and that a run older than `stale_hours` yields `attention` `stale` and `latest.stale` true.
- [X] T022 [US3] Make the home view in `static/js/views/home.js` and `static/js/app.js` refresh on the existing polling cycle without redrawing when nothing changed (reuse the `runSignature` approach in `static/js/model.js`, adding the overview to the signature), so an open page keeps focus and shows "Updated … ago" in the header.
- [X] T023 [US3] Show the stale state on a card (`static/js/views/home.js`): stale pill with the time since the run, ranked as `stale` by the server; also keep the existing stale banner on the Latest page working.

**Checkpoint**: all three stories work independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T024 [P] Update `README.md` in `waypoint_monitor/`: replace the "Pipelines" section (no more header picker or `wp-pipeline`), document the home page, the page addresses and `/api/overview`, and note that `STALE_HOURS` also drives the card's stale state. Add the endpoint to the API list if one exists.
- [X] T025 [P] Run `ruff check .`, `black --check .` and `mypy .` in `waypoint_monitor/` on the Python files edited; fix findings in those files only.
- [X] T026 Run `python -m unittest discover tests` and `node --test static/tests`; compare with `specs/008-pipelines-home-page/before-results.md`: no previously passing test fails, the new ones pass.
- [X] T027 Walk through `specs/008-pipelines-home-page/quickstart.md` in a browser, including phone width (375 px), keyboard only, stopped Redis (error state) and empty Redis (empty state); write any deviation under "Notes from implementation" at the top of this file.
- [X] T028 [P] Check the success criteria that can be measured: SC-001 (two selections from open to a pipeline's Latest page), SC-003 (filter result in under 1 s with 30 runs), SC-004 (every run shown after filtering belongs to the chosen environment); record the figures with the date and how they were measured in `specs/008-pipelines-home-page/before-results.md`.

---

## Dependencies & Execution Order

- Phase 1 first. Phase 2 blocks all stories. Inside Phase 2: T002 and T003 (tests) before T004 and T007; T004 before T005; T005 before T006 passes; T008 after T005 only for manual checks; T009 after T007 and T008.
- **US1** (Phase 3) needs Phase 2 only. **US2** (Phase 4) needs Phase 2 and the history route from T009; it does not need US1's cards, but its default environment uses the overview from T005. **US3** (Phase 5) needs Phase 2 and the home view from US1 (T012, T013) for T022 and T023; T020 and T021 do not.
- Within a story: tests, then pure helpers, then views, then wiring in `app.js`.
- `static/js/app.js` is edited by T009, T013, T018 and T022, `static/js/model.js` by T011 and T016, `static/styles.css` by T014 and T019, `static/js/views/history.js` by T017 and T019, and `static/tests/overview.test.mjs` by T010 and T015: do those in order, not in parallel.

## Parallel Opportunities

- Phase 2: T002, T003 together; then T006, T007 and T008 together after their prerequisites.
- US1: T010 and T014 together (different files).
- US2: T015 can start as soon as Phase 2 is done.
- US3: T020 and T021 together.
- Polish: T024, T025 and T028 together.

## Implementation Strategy

- **MVP**: Phase 1, Phase 2 and US1 (T001 to T014). That gives a home page with working card navigation and shareable addresses, and can be shown to users.
- **Then**: US2 (environment filter), then US3 (new and stale pipelines, demo data), then Polish.
- Stop after each checkpoint and run the quickstart steps for that story.
