---

description: "Task list for Pipeline Monitor Dashboard"
---

# Tasks: Pipeline Monitor Dashboard

**Input**: Design documents from `/specs/002-pipeline-monitor-dashboard/`, and the approved UI design in `docs/design/pipeline-monitor-degisn/` (`DESIGN_NOTES.md`, `index.html`, `styles.css`, `app.js`, `screenshots/*.png`)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md

**Tests**: Included (constitution principle IV). Python: `unittest`, FastAPI `TestClient`, fake store, no live Redis. Front end: `node --test` on pure functions. Visual fidelity is checked against the design screenshots.

**Organization**: Grouped by user story. Paths are relative to `integrations/callraill/performance_monitoring_app/` unless they start with `docs/` or `specs/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3 from spec.md

## Design reuse rules (apply to every front-end task)

- Copy from `docs/design/pipeline-monitor-degisn/` and adapt; do not redesign. Keep both dark-theme token blocks identical (`prefers-color-scheme` and `[data-theme="dark"]`).
- Remove prototype-only parts: the "Preview state" box, URL params (`state`, `run`, `hover`, ...), the fixed `NOW`, the mock data (`buildRuns`, `makeRun`, `BASE`, `rng`) and the hard-coded `STEPS` array (it now comes from `/api/config`).
- Never inject API strings with `innerHTML`; use `textContent` or the design's `esc()`.
- No JS libraries or CDN. The one allowed external request is the optional Geist Google Fonts stylesheet already in the design.

## Phase 1: Setup

- [X] T001 Create the folder tree from plan.md: `app/`, `app/domain/`, `app/infrastructure/`, `app/api/`, `static/`, `static/js/`, `static/js/views/`, `static/tests/`, `tests/`, each Python package with an empty `__init__.py`
- [X] T002 [P] Create `requirements.txt` pinning `fastapi==0.116.1`, `uvicorn==0.35.0`, `redis==5.0.8`, `httpx==0.28.1`, `black==25.1.0`, `ruff==0.12.0`, `mypy==1.15.0`
- [X] T003 [P] Create `pyproject.toml` with the same black (line length 100, py312), ruff (`E,F,B,I`, ignore `E501`) and mypy (`strict = true`, `ignore_missing_imports = true`) settings as the pipeline's `pyproject.toml`
- [X] T004 [P] Create `Dockerfile` (python:3.12-slim, install requirements, copy `app/` and `static/`, `EXPOSE 8080`, entrypoint `python -m app.main`) and a first `README.md` (purpose, env vars, run commands, no-login-in-v1 note)

---

## Phase 2: Foundational (blocking)

**Purpose**: Models, config, definition of the pipeline and record parsing, used by every story.

- [X] T005 Create `app/config.py` with a `Settings` dataclass read from env: `REDIS_URL` (str, default ""), `ENVIRONMENTS` (comma list, default `prod,qa`), `STALE_HOURS` (float, default 26, invalid → 26), `REFRESH_SECONDS` (int, default 60), `RETRY_SECONDS` (int, default 30), `PORT` (int, default 8080), `CACHE_SECONDS` (int, default 10)
- [X] T006 [P] Create `app/domain/steps.py` with `EXPECTED_STEPS`, an ordered list of `StepDefinition(name, group, inputs=[(input_name, from_step)], returns_nothing)` exactly as the table in data-model.md (groups CallRail 2, Google Ads 4, Merge 1, Persist 2)
- [X] T007 [P] Create `app/domain/models.py` with typed frozen dataclasses `StepDefinition`, `StepRecord`, `Run` and `ParseResult(records, unreadable_by_run, unreadable_unattributed)` per data-model.md. `StepRecord` constraints, quoted: `run_id`: "`YYYYMMDDTHHMMSSZ`; must equal the id in the key"; `env`: "must equal the env in the key"; `step`: "non-empty; one of the expected steps"; `index`: "int ≥ 1"; `inputs`: "map string → int ≥ 0 ... values may not be null"; `output`: "int ≥ 0 or null"; `finished_at`: "UTC ISO-8601"
- [X] T008 Create `app/infrastructure/store.py` with `RecordStore` Protocol: `list_records(env: str) -> list[tuple[str, str]]` returning `(key, raw_json)` pairs (read-only) and `ping() -> None` that raises when unreachable; plus `StoreUnavailable(Exception)`
- [X] T009 Create `app/domain/parsing.py` with `parse_records(env, raw) -> ParseResult`: parse keys `callrail:audit:{env}:{run_id}:{NN}-{step}` and JSON values, validate each field against the T007 constraints, drop unknown fields, and count each invalid record in `unreadable_by_run[run_id]` when the key identifies a run, else `unreadable_unattributed`; never raise
- [X] T010 [P] Create `tests/fakes.py` with `FakeStore` (in-memory `RecordStore`, can raise `StoreUnavailable`) and `make_run(env, run_id, missing_from=None, overrides=None, corrupt=())` that builds valid key/JSON pairs for the 9 steps using the design's sample counts (10, 1284, 6, 14, 92, 3410, 1284, null, null)
- [X] T011 [P] Create `tests/test_parsing.py`: valid record parsed; bad JSON, missing field, negative count, null input value, key/value run_id mismatch, unknown step and non-integer index each counted as unreadable for the right run; a key that cannot be parsed counts as unattributed; unknown extra fields ignored and not retained (PII guard)
- [X] T012 Create `app/infrastructure/redis_store.py` with `RedisRecordStore(url)`: `redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)`; `list_records` uses `scan_iter(match=f"callrail:audit:{env}:*", count=500)` then `mget` in batches of 200, skipping missing values, converting `redis.RedisError` to `StoreUnavailable`; `ping()` calls `client.ping()`. It MUST NOT call any write or delete command
- [X] T013 [P] Create `tests/test_redis_store.py` with a mocked client: scan pattern, mget batching, `RedisError` → `StoreUnavailable`, and an assertion that only `scan_iter`, `mget` and `ping` are ever called

**Checkpoint**: Records can be read, validated and attributed to runs from any store.

---

## Phase 3: User Story 1 - Latest run at a glance (Priority: P1) 🎯 MVP

**Goal**: Operator opens the page and sees the latest run per environment, matching the design's Latest view.

**Independent Test**: With a fake store holding runs, `/api/runs` returns full 9-step runs with flags; the page renders hero, KPIs, flow strip and steps like screenshots 01/02/12/13.

### Tests for User Story 1

- [X] T014 [P] [US1] Create `tests/test_analysis.py` for `build_runs(parse_result, env, now, stale_hours)`: groups by run_id, newest first; always 9 steps in order with `{"name","missing": true}` for absent ones; duplicate step → latest `finished_at` wins; inputs ordered per `EXPECTED_STEPS`; complete vs incomplete with `first_missing_step` and `missing_count`; "output exactly 0 and at least one input > 0" → in `loss_steps`; null output never a loss; `started_at` from run_id; `ended_at` = latest finished_at (fallback `started_at`); `duration_seconds`; `age_seconds` and `stale` (> stale_hours × 3600); per-run `unreadable` and a step whose record was unreadable counts as missing
- [X] T015 [P] [US1] Create `tests/test_api.py` with `TestClient` and `FakeStore`: `/api/config` matches contracts/api.md (including the 9 `expected_steps` with groups and `from`), `/api/health` (ok and 503), `/api/runs` shape (200, empty list when no runs, 400 unknown env, 503 `{"error": "Data store unavailable"}`, `limit` default 30 / max 100, `unreadable_total`)
- [X] T016 [P] [US1] Create `static/tests/model.test.mjs` (`node --test`) for `static/js/model.js`: `metric` (output; first input when output null; null when missing), `headline` (accounts, calls, saved from `call_statistics` input; null when step missing), `deltaPct` rules from data-model.md (both present required; 0→0 is 0%; prev 0 → "new"; ±0.05% → no change; sign and rounding), `series(runs, step, n)` oldest→newest with nulls for missing, and formatting helpers (`fmt`, `ago`, `dur`)

### Implementation for User Story 1

- [X] T017 [US1] Create `app/domain/analysis.py` with `build_runs` per T014 and the `Run` serialisation to the JSON shape in `contracts/api.md` (only the documented fields)
- [X] T018 [US1] Create `app/api/routes.py`: `APIRouter` with a small cache (`CACHE_SECONDS`) around `store.list_records`; implement `/api/health`, `/api/config` (from `Settings` and `EXPECTED_STEPS`) and `/api/runs?env=&limit=` per `contracts/api.md`; validate `env` against `Settings.ENVIRONMENTS` (400) and map `StoreUnavailable` to 503
- [X] T019 [US1] Create `app/main.py` with `create_app(store=None, settings=None) -> FastAPI` (builds `RedisRecordStore` when none is given, includes the router, mounts `static/` at `/` with `index.html`, `Cache-Control: no-cache` for `index.html`) and `main()` running `uvicorn` on `Settings.PORT`
- [X] T020 [P] [US1] Copy `docs/design/pipeline-monitor-degisn/styles.css` to `static/styles.css` unchanged (tokens, light and dark blocks, all components, responsive rules, reduced-motion rules); only remove rules used solely by the prototype's `.proto` switcher
- [X] T021 [P] [US1] Create `static/index.html` from `docs/design/pipeline-monitor-degisn/index.html`: keep header, env segmented control, live indicator, theme toggle, tabs, banners area, view sections, drawer and tooltip; remove the `.proto` preview box; load `js/app.js` as `type="module"`; keep the early theme script and the optional Geist font link
- [X] T022 [P] [US1] Create `static/js/model.js` (pure, no DOM) by extracting from the design's `app.js`: `stepOf`, `metric`, `headline`, `deltaPct`, `series`, `fmt`, `ago`, `dur`, `dayLabel`, `shortDay`, `hhmm`, plus `analyse(run)` reduced to reading the API flags (`status`, `first_missing_step`, `missing_count`, `loss_steps`, `ended_at`, `duration_seconds`, `age_seconds`, `stale`) instead of recomputing them; make T016 pass
- [X] T023 [US1] Create `static/js/api.js`: `loadConfig()` and `loadRuns(env)` (fetch `/api/config`, `/api/runs?env=&limit=30`) mapping to the view shape `{ id, env, startedAt: Date, endedAt: Date, steps: [ {name, inputs:[{name,value}], output: number|null, finishedAt: Date} | {name, missing:true} ], unreadable, ...flags }`; throw a typed `DataStoreUnavailable` error on 503 or network failure; do not guess field names beyond `contracts/api.md`
- [X] T024 [P] [US1] Create `static/js/chart.js` with `sparkline(values)` extracted from the design (128×36 SVG, gaps break the line, zero values get a red dot, latest point accent dot)
- [X] T025 [US1] Create `static/js/views/latest.js` from the design's `heroHTML`, `stepsHTML` and `renderLatest`: hero (status pill, loss pill, stale pill, title sentence and why-line), three KPIs with delta chips, flow strip with group labels from `/api/config`, steps timeline with chips (tooltip "from" taken from `expected_steps`), magnitude bars, `n/a` + "returns nothing", loss and missing step styling, sparklines over the last 14 runs
- [X] T026 [US1] Create `static/js/app.js` (shell, first part) from the design: env segmented control, tabs with roving tabindex and arrow keys, theme toggle persisted in `localStorage` inside try/catch (follow the OS setting when nothing saved), loading skeleton while the first fetch runs, call `loadConfig`/`loadRuns`, render the Latest view; no polling yet

**Checkpoint**: MVP; Latest view correct for prod and qa, matches screenshots 01, 02, 12, 13 at 1440 px and 375 px.

---

## Phase 4: User Story 2 - Run history and trends (Priority: P2)

**Goal**: Browse past runs, open one in the drawer, and view per-step trends, matching the design's History view.

**Independent Test**: With several fake runs, the History tab lists them newest first, the drawer shows step details, and the trend chart shows the chosen step's last 30 runs with change chips (screenshots 03, 04, 06, 14).

### Tests for User Story 2

- [X] T027 [P] [US2] Extend `static/tests/model.test.mjs`: trend `series` of 30 runs with gaps for missing steps, no-output steps use their first input (`returns_nothing`), per-point change vs the run before, single-run list gives no change
- [X] T028 [P] [US2] Extend `tests/test_api.py` for `/api/runs` with several runs: newest first, `limit` truncation, per-run `unreadable` and `loss_steps`, and `ended_at`/`duration_seconds` values

### Implementation for User Story 2

- [X] T029 [US2] Extend `static/js/chart.js` with `drawTrend(el, runs, step, tooltipEl)` from the design: 240 px (200 px mobile) SVG area chart redrawn at the container's width and on resize, 4-line grid, compact y labels, about 7 date labels, dashed circle for missing runs, red point for a zero caused by data loss, crosshair + tooltip on pointer move, focusable with ←/→/Home/End
- [X] T030 [US2] Create `static/js/views/history.js` from the design's `renderHistory` and drawer code: trend card with step `<select>` (options from `expected_steps`), runs list (run, status, accounts, calls, saved, flags, `N unreadable` pill, chevron), the drawer as `role="dialog"` with focus trap, scrim, Esc/✕ close, focus returning to the row, reusing the steps renderer in compact mode
- [X] T031 [US2] In `static/js/app.js` wire the History tab: render `views/history.js` from the loaded runs; keep selected tab, run and step in memory across refreshes (no URL parameters)

---

## Phase 5: User Story 3 - Stay current and handle problems (Priority: P3)

**Goal**: Auto-refresh with a live indicator, stale and unreadable notices, empty and error states, as in screenshots 07–11.

**Independent Test**: A new run appears within one refresh interval; stopping the store shows the error card with Retry; stale, empty and partial-read cases show the designed banners.

### Tests for User Story 3

- [X] T032 [P] [US3] Extend `tests/test_api.py`: `stale` true and `age_seconds` correct for an old run, `/api/config` reflects `REFRESH_SECONDS`, `RETRY_SECONDS` and `STALE_HOURS`, cache serves the same data within `CACHE_SECONDS` and refreshes after it (inject a clock), and a `StoreUnavailable` after a successful call is raised rather than served from cache
- [X] T033 [P] [US3] Extend `static/tests/model.test.mjs`: relative "updated Ns ago" formatting and the next-retry countdown helper used by the live indicator and error card

### Implementation for User Story 3

- [X] T034 [US3] Make the cache clock injectable in `app/api/routes.py` (default `time.monotonic`), and make sure an unreachable store is never answered from cache
- [X] T035 [US3] Extend `static/js/app.js`: poll `loadRuns` every `refresh_seconds` (pause while the tab is hidden, refresh immediately when visible), preserve tab/env/run/step selection across refreshes, live indicator "Updated Ns ago" counted from the last successful fetch, banners in `#banners` (stale amber `role="alert"`, unreadable info notice with count) and the designed empty state ("No runs yet for <env>")
- [X] T036 [US3] Extend `static/js/app.js`: on `DataStoreUnavailable` replace both views with the designed error card (`role="alert"`, no numbers, "Retry now" button, "Retrying automatically in Ns · last success …" using `retry_seconds`) and set the live indicator to "Last updated … ago" in its off style; recover automatically on the next success

---

## Phase 6: Polish

- [X] T037 [P] Complete `README.md` (env var table: `REDIS_URL`, `ENVIRONMENTS`, `STALE_HOURS`, `REFRESH_SECONDS`, `RETRY_SECONDS`, `PORT`, `CACHE_SECONDS`; run, test (`unittest`, `node --test static/tests`) and docker commands; the key format it reads; no-login security note; where the design lives)
- [X] T038 Run `black .`, `ruff check .`, `mypy .`, `python -m unittest discover tests` and `node --test static/tests` inside `performance_monitoring_app/`; fix findings
- [ ] T039 Seed a test Redis with the feature 001 record format (or use the unit-test fakes served by `create_app`) and walk through `specs/002-pipeline-monitor-dashboard/quickstart.md`; compare against every screenshot in `docs/design/pipeline-monitor-degisn/screenshots/` at 1440 px and 375 px, light and dark; check keyboard and reduced motion; list any visual differences you could not fix

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 → US2 and US3 → Polish
- Phase 2: T005 and T006/T007 first; T008 → T012; T009 needs T007; T010, T011, T013 follow their targets
- US1: tests T014–T016 first (they fail), then backend T017 → T018 → T019; front end T020, T021, T022, T024 in parallel, then T023, T025, T026
- US2 and US3 both extend `static/js/app.js` and `routes.py`: run them one after the other (US2 first)

### Parallel examples

- Setup: T002, T003, T004 together
- Foundational: T006 with T007; then T010, T011, T013 together
- US1 tests: T014, T015, T016 together; front-end copy tasks T020, T021, T022, T024 together
- US2 tests: T027 with T028; US3 tests: T032 with T033

## Implementation Strategy

- **MVP**: Phases 1–3. Stop and validate the Latest view against screenshots 01, 02, 12, 13.
- Then US2 (history, drawer, trend), then US3 (polling, banners, error state), then polish and the full quickstart walk-through.
- Keep the front end dependency-free and keep the design's tokens and component CSS unchanged; resist redesigning.
