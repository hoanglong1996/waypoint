---

description: "Task list for Run Duration and Run Events"
---

# Tasks: Run Duration and Run Events

**Input**: Design documents from `/specs/012-duration-and-run-events/`

**Prerequisites**: plan.md, spec.md, research.md (R1-R15), data-model.md, contracts/{redis-keys,library-api,api,ui}.md, quickstart.md

**Tests**: Included. The constitution (principle IV) requires tests for changed behaviour, and spec FR-031 / SC-008 need regression tests for unchanged old runs.

**Organization**: Grouped by user story. Paths are relative to the repository root. `LIB` = `packages/waypoint_etl`, `MON` = `waypoint_monitor`.

**Conventions**: Python is fully typed (`mypy --strict`), `ruff` + `black` line length 100; the library supports Python 3.10+ and uses only the standard library. Test runners: `python -m unittest discover tests` (in `LIB` and in `MON`), `node --test static/tests/*.test.mjs` (in `MON`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1-US7 (from spec.md)

Story map: US1 step and run durations · US2 Slower than usual in History · US3 Events timeline · US4 send events from a pipeline · US5 warning/error counts and step events · US6 events never slow or break the pipeline · US7 older pipelines and monitors.

## Phase 1: Setup

- [X] T001 Run the baseline before changing anything: in `packages/waypoint_etl` and in `waypoint_monitor` run `python -m unittest discover tests`, `mypy`, `ruff check .`, `black --check .`; in `waypoint_monitor` run `node --test static/tests/*.test.mjs`. Record the pass counts under "Baseline" in `specs/012-duration-and-run-events/quickstart.md`
- [X] T002 [P] Verify research R14 by test: add a case to `waypoint_monitor/tests/test_parsing.py` showing `parse_records` today ignores unknown extra fields on a step record (a record with `started_at` and `duration_ms` still parses and is not counted unreadable); record the result in `specs/012-duration-and-run-events/research.md` R14 if it differs

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: The library writes the new finish fields and knows the event key; the monitor reads the finish fields and has its settings. No display change yet.

### Library: finish record fields

- [X] T003 [P] Extend `packages/waypoint_etl/tests/test_auditor.py` (confirm failing first): `finish()` writes `started_at` equal to the start marker's `started_at` and `duration_ms` an int `>= 0` measured with a monotonic clock (patch `time.monotonic` to prove a wall-clock jump does not change it); all earlier fields (`pipeline`, `run_id`, `env`, `step`, `index`, `inputs`, `output`, `finished_at`) are unchanged and still present; a finish for an index that was never begun omits both new fields; `StepAuditor.run` writes them too
- [X] T004 Implement in `packages/waypoint_etl/src/waypoint_etl/auditor.py`: `begin()` also remembers `time.monotonic()` per index (a second dict next to `_begun`); `finish()` adds `started_at` (the same string as the marker) and `duration_ms = max(0, round((monotonic_now - begun) * 1000))` when the index is known, and pops both; the step's result and exceptions stay untouched. Make T003 pass
- [X] T005 [P] Add `events_key(pipeline, env, run_id, level)` to `packages/waypoint_etl/src/waypoint_etl/keys.py` returning `waypoint:{pipeline}:{env}:{run_id}:events:{level}` for `level` in `info`, `warning`, `error` (anything else raises `ValueError`), plus the constants `EVENT_CAPS = {"info": 500, "warning": 200, "error": 200}`; add the matching tests to `packages/waypoint_etl/tests/test_keys.py` (exact key strings, invalid level)

### Monitor: read the finish fields, settings

- [X] T006 [P] Write `waypoint_monitor/tests/test_parsing.py` additions for the optional finish fields (confirm failing): `started_at` (ISO-8601 UTC) and `duration_ms` (int >= 0) parse into `StepRecord`; a wrong type (`duration_ms: "5"`, `-1`, `true`, `started_at: "x"`) is ignored for that field only and the record is **not** unreadable; a record without them parses with both `None`
- [X] T007 Add `started_at: Optional[datetime] = None` and `duration_ms: Optional[int] = None` to `StepRecord` in `waypoint_monitor/app/domain/models.py` (update its docstring: "started_at: UTC ISO-8601, optional. duration_ms: int >= 0, optional") and parse them in `_validate` in `waypoint_monitor/app/domain/parsing.py` per T006. Make T006 pass and keep every existing parsing test green
- [X] T008 [P] Add `slow_run_multiple: float = 2.0`, `duration_window_runs: int = 30`, `duration_min_runs: int = 5` to `Settings` in `waypoint_monitor/app/config.py`, read from `SLOW_RUN_MULTIPLE`, `DURATION_WINDOW_RUNS`, `DURATION_MIN_RUNS` (invalid values fall back to the default; a multiple `<= 0` or a window/min `< 1` also falls back); add cases to `waypoint_monitor/tests/test_config.py`; add the three values to `GET /api/config` in `waypoint_monitor/app/api/routes.py` and to `waypoint_monitor/.env.example` with a comment each
- [X] T009 Update `waypoint_monitor/tests/fakes.py` and `waypoint_monitor/tests/seed_demo.py` so finish records can carry `started_at` and `duration_ms`; make `seed_demo` write: a completed run with exact durations, an old-style completed run (no start fields, no markers), a failed run, and, after at least 6 completed runs of a pipeline, one run that took more than 2x the typical duration, and, once US3 exists, one run with author events (including more than 500 info events, a few warnings and errors) written as the three event lists (used by the manual pass)

**Checkpoint**: A finish record written by the library carries its start and duration; the monitor parses it; nothing is displayed differently yet.

---

## Phase 3: User Story 1 - See how long each step and run took (Priority: P1)

**Goal**: Every run and step shows a duration; the slowest step is highlighted.

**Independent Test**: View a completed run of the previous library version: the run shows a correct duration, each step an approximate one, the slowest step is highlighted; a running run shows `…` and an increasing value (quickstart section 3, steps 1-4).

### Tests (write first, confirm they fail)

- [X] T010 [P] [US1] Write `waypoint_monitor/tests/test_durations.py` for the pure functions of `app/domain/durations.py` (data-model.md "Step duration", "Run duration", "Bottleneck"): source order `duration_ms` > finish `started_at` > start marker > previous end (approximate: previous step's finish or failure time among steps with a lower attempt index, the run start for the first step); `duration_approx` is true only for the last source; a negative or missing result is `None` ("duration_seconds: int >= 0 or null"); a failed step is `failed_at - started_at`; `running`/`stalled`/`died`/`waiting`/`missing` steps get no duration; run `seconds` runs from the run id time to the latest finish or failure time, and to now for a running run, `running` true, `complete` equal to `status == "complete"`; bottleneck is the step with the strictly largest duration, `None` with fewer than two durations or a tie for the maximum
- [X] T011 [P] [US1] Write `waypoint_monitor/tests/test_analysis.py` additions: `done`, `unplanned` and `failed` steps carry `duration_seconds` and `duration_approx`; `done`/`unplanned` steps carry `started_at` when known; the run carries `duration` and `bottleneck`; existing `duration_seconds` of the run is unchanged; for a run with no new fields the only new keys are `duration`, `bottleneck` (and `duration_*` on steps); a retry that finished uses the latest attempt's duration
- [X] T012 [P] [US1] Write `waypoint_monitor/tests/test_overview.py` and `test_api.py` additions: `latest.duration_seconds` and `latest.duration_running` are set from the latest run; `/api/runs` returns the fields of T011; `card_status` and ordering are unchanged by durations
- [X] T013 [P] [US1] Write front-end tests in `waypoint_monitor/static/tests/model.test.mjs`, `graph-model.test.mjs`, `overview.test.mjs`, `run-view.test.mjs`: `fmtDuration(seconds, {approx, running})` gives `37s`, `4m 05s`, `1h 04m`, `2d 03h`, `<1s` for 0, `—` for null, `≈4m 05s` when approximate, a trailing `…` when running; `mapStep` maps `durationSeconds`, `durationApprox`, `startedAt` for done steps; `mapRun` maps `duration` and `bottleneck`; the card maps `durationSeconds`/`durationRunning`; `analyse` exposes the bottleneck and its share of the run (`Slowest: <step>, 62% of the run`, absent with fewer than two durations)

### Implementation

- [X] T014 [US1] Implement `waypoint_monitor/app/domain/durations.py` (pure, typed): `step_duration(...)`, `run_duration(...)`, `find_bottleneck(...)` per data-model.md and research R1, R10; make T010 pass
- [X] T015 [US1] Wire it in `waypoint_monitor/app/domain/analysis.py` (`add_done`, `add_failed`, `_build_run`): add the step fields and the run fields `duration`, `bottleneck`; `duration.slow` stays `false` here (US2); keep every other key unchanged. Make T011 pass and all existing analysis tests stay green
- [X] T016 [US1] Add `duration_seconds`, `duration_running` to the summary in `waypoint_monitor/app/domain/overview.py`. Make T012 pass
- [X] T017 [P] [US1] Update `waypoint_monitor/static/js/model.js`: `fmtDuration` per T013 (replace the current `dur` helper's callers or make `dur` delegate to it, keeping existing behaviour for existing tests), `analyse` exposes `bottleneck` and `bottleneckShare`
- [X] T018 [P] [US1] Update `waypoint_monitor/static/js/api.js`: `mapStep` (`durationSeconds`, `durationApprox`, `startedAt` for done), `mapRun` (`duration`, `bottleneck`), overview card (`durationSeconds`, `durationRunning`). Make T013 pass together with T017
- [X] T019 [P] [US1] Update `waypoint_monitor/static/js/graph-model.js` so a node exposes its duration and a `bottleneck` flag; update its header comment
- [X] T020 [P] [US1] Add to `waypoint_monitor/static/js/ui.js` a `durationHTML(seconds, {approx, running})` helper (uses `fmtDuration`, adds the tooltip "estimated from the previous step" when approximate) and a `slowestTag()` (stopwatch icon + the word "Slowest", so colour is not the only cue)
- [X] T021 [US1] Update `waypoint_monitor/static/js/views/step.js`: show the step's duration beside its time line (`running`/`stalled` keep elapsed with `…`), "Slowest" tag when it is the bottleneck
- [X] T022 [P] [US1] Update `waypoint_monitor/static/js/views/run.js`: total duration in the headline (with `…` while running), the line "Slowest: <step>, N% of the run" when a bottleneck exists
- [X] T023 [P] [US1] Update `waypoint_monitor/static/js/views/graph.js`: duration label under each node name and the "Slowest" marker on the bottleneck node (icon + text)
- [X] T024 [P] [US1] Update `waypoint_monitor/static/js/views/home.js`: the card shows the latest run's duration (`…` while running)
- [X] T025 [US1] Add styles in `waypoint_monitor/static/styles.css`: duration text, `.tag-slowest`, `.gnode__dur`, `.gnode--slowest` (solid outline + icon, not colour only), dark-mode tokens like the existing ones, no horizontal page scroll at phone width
- [X] T026 [US1] Run all suites, `mypy`, `ruff`, `black --check`; then do quickstart section 3 steps 1-4 against the seeded Redis and note the results in `specs/012-duration-and-run-events/quickstart.md`

**Checkpoint**: US1 works end to end (SC-001, SC-002).

---

## Phase 4: User Story 2 - Notice a run that is slower than usual (Priority: P1)

**Goal**: History shows durations over time, the typical values, and flags slow runs.

**Independent Test**: A pipeline with runs of about 10 minutes plus one of 35 minutes: only that run is flagged; the typical and slow-end values are shown; with fewer than 5 completed runs nothing is flagged (quickstart section 3, steps 5-6).

### Tests (write first, confirm they fail)

- [X] T027 [P] [US2] Extend `waypoint_monitor/tests/test_durations.py` for `typical(runs, window, min_runs, multiple)` and `flag_slow(runs, typical)` (data-model.md "Typical duration"): only `status == "complete"` runs with a known duration qualify (Failed, Died, Stalled, Incomplete and running never do; Lost data does), newest `window` of them; median is the middle value and the mean of the two middle values for an even count, rounded to the second; p95 is nearest-rank, the `ceil(0.95 * n)`-th smallest; `None` when fewer than `min_runs` qualify; `slow_after_seconds = multiple * median_seconds`; a run is slow when `duration.seconds > slow_after_seconds` and typical exists, including a running run whose elapsed time already exceeds it; a run at exactly the threshold is not slow; flags never change `status`
- [X] T028 [P] [US2] Write `waypoint_monitor/tests/test_api.py` and `test_overview.py` additions: `/api/runs` returns `typical` over **all** runs read (not the `limit` slice) and `duration.slow` per run; `/api/overview` `latest.slow`; `card_status`, `needs_attention` and card order are identical with and without a slow run (FR-013); settings from `Settings` change the result
- [X] T029 [P] [US2] Write front-end tests: `model.test.mjs` for `mapRun` `duration.slow`, `typical`, and `slowText(run, typical)` = `Slower than usual: 35m 00s vs 10m 12s typical`; `state.test.mjs` for a pure `durationSeries(runs, typical)` returning one point per run (value, slow flag, running flag) plus the median and p95 lines, and "not enough history" when `typical` is null

### Implementation

- [X] T030 [US2] Implement `typical` and `flag_slow` in `waypoint_monitor/app/domain/durations.py`; make T027 pass
- [X] T031 [US2] In `waypoint_monitor/app/api/routes.py::build` compute `typical` after `build_runs` over every built run, set each run's `duration.slow`, keep `typical` with the window result, return it from `/api/runs` (top-level `typical`, `null` when none) and `latest.slow` from overview (`waypoint_monitor/app/domain/overview.py`). Make T028 pass
- [X] T032 [P] [US2] Update `waypoint_monitor/static/js/api.js` (`fetchRuns` returns `{runs, typical}`, with `app.js` passing `typical` to `renderHistory`; `duration.slow`, card `slow`) and `waypoint_monitor/static/js/model.js` (`slowText`, `durationSeries`). Make T029 pass
- [X] T033 [P] [US2] Add `drawDuration(box, statEl, tooltipEl, series)` to `waypoint_monitor/static/js/chart.js`: one point per run, dashed median line, p95 band, a marker shape plus label for slow runs, tooltip with value and median, keyboard arrows like `drawTrend`
- [X] T034 [US2] Update `waypoint_monitor/static/js/views/history.js`: Duration column in the runs list, a "Run duration" card beside "Step trend", the stat line "Typical <median> · slow end <p95> · <n> runs" or "Not enough history yet (needs <min> completed runs)", the "Slower than usual" pill (clock icon + text) on flagged rows; add `slowPill()` to `waypoint_monitor/static/js/ui.js`
- [X] T035 [P] [US2] Update `waypoint_monitor/static/js/views/run.js` to show the "Slower than usual" pill in the headline when the run is slow (and still running or finished)
- [X] T036 [P] [US2] Add styles in `waypoint_monitor/static/styles.css` for the duration chart, `.pill--slow`, the slow marker; dark mode
- [X] T037 [US2] Run all suites, `mypy`, `ruff`, `black --check`; do quickstart section 3 steps 5-6 and note the results

**Checkpoint**: US1 and US2 deliver roadmap item 2 (SC-003).

---

## Phase 5: User Story 3 - Read what a run did, as a timeline (Priority: P1)

**Goal**: The run page has an Events tab with a time-ordered, filterable, paged timeline built from derived events plus recorded events.

**Independent Test**: A three-step pipeline whose second step fails, with no author events: the Events tab shows run start, step 1 start/finish, step 2 start, the step 2 error with type and message, and "Run stopped at ..." in order (quickstart section 4, steps 1-3).

### Tests (write first, confirm they fail)

- [X] T038 [P] [US3] Write `waypoint_monitor/tests/test_parsing.py` additions for `parse_events(env, pipeline, raw) -> Tuple[List[RunEvent], Dict[str, int]]` (events, unreadable count by run id) over `(key, [json, ...])` pairs: a valid element parses; bad JSON, wrong `v`, missing or bad `ts`, a `level` that differs from the key's list, `n` not an int `>= 1` are skipped and counted for their run ("n: int >= 1"); `message` longer than 300 characters is shortened, `fields` with more than 10 entries or names not matching `^[A-Za-z0-9_.-]{1,40}$` or values that are not finite numbers or strings of at most 100 characters are dropped (not rejected); a missing `message` gives `None`; other pipelines', envs' and non-event keys are ignored; never raises
- [X] T039 [P] [US3] Write `waypoint_monitor/tests/test_timeline.py` for `app/domain/timeline.py` (data-model.md "Timeline entry", research R3, R4, R13): each derived kind in the table exists with the stated level, `ts` rule and fields (`run_started`, `step_started`, `step_finished`, `step_failed` with `Type: message` and no traceback, `step_stalled` at `started_at + stall_seconds`, `run_died`, `run_stopped`, `run_finished`); `finished`/`failed`/`ended` events sort at the end of their second so a recorded event sent 0.6 s into the last second of a step sorts before its `step_finished`; equal timestamps keep derived before recorded, derivation order for derived and `n` for recorded; filters by level (one or several) and by exact step; paging by `offset`/`limit` with `matched`, `total`, `has_more`; `dropped = max(0, max(n) - number of recorded events)`; a run with no flow still gets its derived events in index order; derived entries have `source: "monitor"`, recorded `source: "pipeline"`; a step that retried has one started/finished pair per attempt still shown; a step not in the flow keeps its events
- [X] T040 [P] [US3] Write `waypoint_monitor/tests/test_redis_store.py` additions: `list_event_counts(env, pipeline)` scans exactly `waypoint:{pipeline}:{env}:*:events:*` and runs a pipelined `LLEN`, never writes; `read_events(env, pipeline, run_id)` runs `LRANGE key 0 -1` on the three level keys of that run only; a `ResponseError` (for example `NOPERM`) gives empty results and not `StoreUnavailable` (research R12 degraded mode) while a `ConnectionError` raises `StoreUnavailable`
- [X] T041 [P] [US3] Write `waypoint_monitor/tests/test_api.py` additions for `GET /api/runs/{pipeline}/{env}/{run_id}/events`: fields of contracts/api.md; a run with 900 recorded events answers the first page in under 2 seconds (SC-009, measured with the fake store); defaults `offset=0`, `limit=200`; `limit` outside 1 to 500, bad `level`, negative `offset` give 400; unknown `env` and invalid `pipeline` or `run_id` give 400; an unknown run returns `total: 0`, not 404; `recorded: 0` for a run without author events; a damaged element is counted in `unreadable` and the rest is shown; store unreachable gives 503; the endpoint never calls a write
- [X] T042 [P] [US3] Write front-end tests: `router.test.mjs` for `?tab=events&level=warning,error&step=load` parsing and building; `run-view.test.mjs` for `eventRowHTML` (level icon plus word, step chip, fields as `name value` chips, "monitor" tag, every text escaped: a message `<img onerror=x>` appears as text), `filterSummary` ("N of M events"), and `eventNotes` (dropped note, "does not send events" note when `recorded == 0`, unreadable note)

### Implementation

- [X] T043 [US3] Add `RunEvent` (frozen dataclass: `run_id`, `level`, `n`, `ts`, `step`, `message`, `fields`) to `waypoint_monitor/app/domain/models.py` and implement `parse_events` plus the event key regex in `waypoint_monitor/app/domain/parsing.py` following `parse_failures`; make T038 pass
- [X] T044 [US3] Add `list_event_counts` and `read_events` to the `RecordStore` protocol in `waypoint_monitor/app/infrastructure/store.py` (docstrings: "Read only") and implement them in `waypoint_monitor/app/infrastructure/redis_store.py` per research R12; add the fake versions to `waypoint_monitor/tests/fakes.py` (an `.events` mapping by run id and level, helper `add_event`); make T040 pass
- [X] T045 [US3] Implement `waypoint_monitor/app/domain/timeline.py` (pure, typed): `derive_events(run, stall_seconds)`, `merge(derived, recorded)`, `select(events, levels, step, offset, limit)`, `dropped(recorded)`; make T039 pass
- [X] T046 [US3] Add the events endpoint to `waypoint_monitor/app/api/routes.py` (validation with `PIPELINE_NAME` and `parse_run_id`; build the run with the cached `build`, read recorded events with `store.read_events`, merge, select, respond per contracts/api.md); make T041 pass
- [X] T047 [P] [US3] Update `waypoint_monitor/static/js/router.js` so the run route accepts and builds `tab`, `level`, `step` in the hash query; make the router test pass
- [X] T048 [P] [US3] Add `fetchEvents(pipeline, env, runId, {level, step, offset, limit})` and `mapEvent` to `waypoint_monitor/static/js/api.js`; add `eventLevelMeta` (icon id, word) to `waypoint_monitor/static/js/model.js`; add level icons `I.eventInfo`, `I.eventWarning`, `I.eventError` (distinct shapes) to `waypoint_monitor/static/js/ui.js`
- [X] T049 [US3] Create `waypoint_monitor/static/js/views/events.js`: renders the toolbar (level checkboxes, step select, "N of M events"), the list rows (time `hh:mm:ss` with full-time tooltip, level icon and word, step chip linking to the step, message, field chips, "monitor" tag), the notes of ui.md, "Load more" paging, loading/empty/error states, polite live-region announcement of new rows; export `eventRowHTML`, `filterSummary`, `eventNotes` for the tests of T042
- [X] T050 [US3] Update `waypoint_monitor/static/js/views/run.js` with the `Steps | Events` tabs (tab state from the route), and `waypoint_monitor/static/js/app.js` so a running run refetches the loaded event pages on each `REFRESH_SECONDS` without resetting filters or scroll position; make T042 pass
- [X] T051 [P] [US3] Add styles in `waypoint_monitor/static/styles.css`: tabs, events toolbar, list rows, level colours plus icons, field chips, monitor tag; dark mode; wrapping long messages without horizontal page scroll at phone width (390)
- [X] T052 [US3] Run all suites, `mypy`, `ruff`, `black --check`; do quickstart section 4 steps 1-3 and note the results

**Checkpoint**: US3 works end to end from derived events alone (SC-005, SC-009).

---

## Phase 6: User Story 4 - Send my own events from a pipeline (Priority: P1)

**Goal**: `waypoint_etl.log/warn/error` store events that appear in the timeline, attached to the right step, with the same privacy controls as errors.

**Independent Test**: Call it from inside a step, outside any step, before `init`, and with the store unreachable: the first appears on that step in the timeline, the others do nothing and raise nothing (quickstart section 4, steps 4 and 6).

### Tests (write first, confirm they fail)

- [X] T053 [P] [US4] Write `packages/waypoint_etl/tests/test_events.py` for `build_event(...)` in `waypoint_etl/events.py` (contracts/library-api.md, research R7, R8, R11): `level` outside `info`/`warning`/`error` becomes `info`; `message` cut to 300 characters; at most 10 `fields`; names must match `^[A-Za-z0-9_.-]{1,40}$` else dropped; values must be finite `int`/`float` or `str` of at most 100 characters, booleans, lists, dicts and NaN dropped; `ts` is UTC with milliseconds; `n` increases by one per event across levels; capture off omits `message` and drops text values but keeps numbers; `redact` is applied to the message and to each text value before the cap, a `redact` that raises or returns a non-string drops that text; a marker string never appears anywhere in the built event when capture is off (SC-010)
- [X] T054 [P] [US4] Write `packages/waypoint_etl/tests/test_events.py` additions for step attachment (research R8): an event sent inside a decorated step (sync, `async` and from a nested call) carries that step; `step=` overrides; in a worker thread (no inherited context) the single open step is used, and no step when none or several are open; outside any step `step` is absent; concurrent `async` steps keep their own names (context variable)
- [X] T055 [P] [US4] Write `packages/waypoint_etl/tests/test_stores.py` additions: `RedisStepAuditStore.push_events(items, ttl_seconds)` where `items` is a sequence of `(key, values, cap)` triples, issues, in one transaction, `RPUSH key *values`, `LTRIM key -cap -1` and `EXPIRE key ttl` per triple (use a fake client recording calls); a store without `push_events` makes `log` skip with one warning
- [X] T056 [P] [US4] Write `packages/waypoint_etl/tests/test_unconfigured.py` additions: `log`, `warn`, `error` before `init`, after a failed `init` (invalid spec, no URL), and after `clear()` return `None` and raise nothing, and print at most one warning in total

### Implementation

- [X] T057 [US4] Implement `build_event` and the limits in `packages/waypoint_etl/src/waypoint_etl/events.py` (standard library only, typed); make T053 pass
- [X] T058 [US4] Add the context variable for the current step in `packages/waypoint_etl/src/waypoint_etl/events.py` and set/reset it in both wrappers of `packages/waypoint_etl/src/waypoint_etl/decorator.py` and in `StepAuditor.run` (set after `begin`, reset in `finally`); add `current_open_step()` to `StepAuditor` for the worker-thread fallback; make T054 pass
- [X] T059 [US4] Add `push_events(items: Sequence[Tuple[str, Sequence[str], int]], ttl_seconds: int)` (triples `(key, values, cap)`) to `RedisStepAuditStore` in `packages/waypoint_etl/src/waypoint_etl/stores.py` (transaction pipeline as in T055; `NoopStepAuditStore` gets a no-op); make T055 pass
- [X] T060 [US4] Implement the `EventWriter` (bounded `queue.Queue(maxsize=2000)`, daemon thread `waypoint-events`, `put_nowait`, drain up to 100 waiting at most 1 second, one `push_events` call per flush, warning throttle at most once per 60 seconds, `flush(timeout)`, `stop()`) in `packages/waypoint_etl/src/waypoint_etl/events.py`, own it from `StepAuditor` (start with `start()`, stop in `stop()`), have `registry.clear()` flush it and register one `atexit` hook; then add `log`, `warn`, `error` to `packages/waypoint_etl/src/waypoint_etl/registry.py` (no-ops without an active auditor, never raise, wrap everything in `try/except Exception`, enqueue through the writer) and export them plus keep `init` unchanged in `packages/waypoint_etl/src/waypoint_etl/__init__.py` and `__all__`; make T056 pass
- [X] T061 [US4] Update the `init` docstring in `packages/waypoint_etl/src/waypoint_etl/registry.py` so `capture_error_message` and `redact` say they cover all free text the library stores (failure messages and event text), per research R7
- [X] T062 [US4] Add an end-to-end test `packages/waypoint_etl/tests/test_event_flow.py` with a recording store: events sent in two steps land under `events_key(...)` of the right level with the right step, one transaction per flush per level, TTL equals the run's `ttl_days`, and a `capture_error_message=False` run stores no marker text anywhere (SC-010)

**Checkpoint**: US3 and US4 deliver roadmap item 3 (SC-004, SC-005).

---

## Phase 7: User Story 6 - Pipelines never get slower or break because of events (Priority: P1)

**Goal**: Sending events is non-blocking, bounded in memory and in Redis, and safe when Redis is down.

**Independent Test**: 5,000 info events plus errors in one run: stored events stay within the caps, errors are all kept, the run finishes normally and in about the same time (quickstart section 4, steps 5 and 7).

### Tests (write first, confirm they fail)

- [X] T063 [P] [US6] Write `packages/waypoint_etl/tests/test_event_writer.py` for the writer in `waypoint_etl/events.py` (research R5, R6): `log` returns without touching the store (the store's `push_events` is blocked on an `Event` and the call still returns immediately); the queue holds 2,000 events and beyond that an info event is dropped while a warning or error displaces a queued info event; events are written in batches of at most 100 grouped by level (one transaction per flush); `clear()` flushes what is queued, waiting at most 2 seconds with a store that hangs; the same at process exit (`atexit` handler registered once, unregistered by `clear()`); a store that raises on every write is caught, one warning at most per 60 seconds (patch the clock), the batch is discarded, later events still flow once the store recovers; a run that sends 5,000 events with a fast fake store ends with no event lost beyond the queue rule and `n` gaps equal to the dropped count
- [X] T064 [P] [US6] Write `packages/waypoint_etl/tests/test_event_writer.py` additions: many threads (8 x 500 events) sending at once lose none (store large enough) and keep per-thread order; a step's return value and an exception raised by the step are identical with a hanging or raising event store (SC-007)
- [X] T065 [US6] Make T063 and T064 pass by hardening the `EventWriter` built in T060 (queue-full rule: a warning or error displaces a queued info event; flush timeout with a hanging store; throttled warnings; thread safety)
- [X] T066 [US6] Add a timing test in `packages/waypoint_etl/tests/test_event_writer.py` that 5,000 `log` calls take at most 5% of a fixed 1-second step budget on the fake store (assert the loop with 5,000 `log` calls takes at most 1.05x the time of the same loop without `log`, using the best of 5 runs; skip only via an explicit environment variable, never silently) (SC-006)

**Checkpoint**: US6 holds (SC-006, SC-007).

---

## Phase 8: User Story 5 - Warnings and errors visible without opening a run (Priority: P2)

**Goal**: Home cards and History rows show warning and error counts; a step's details list its events.

**Independent Test**: A pipeline that emits two warnings and one error: the card and the History row show `2 warnings` and `1 error`; the step's details list only that step's events (quickstart section 4, step 4).

### Tests (write first, confirm they fail)

- [X] T067 [P] [US5] Write `waypoint_monitor/tests/test_analysis.py`, `test_overview.py`, `test_api.py` additions: `build_runs(..., event_counts=...)` puts `event_counts = {"warning": n, "error": m}` on each run (zeros when none); `latest.warnings`/`latest.errors` on cards; counts come only from `list_event_counts` (no event bodies read for `/api/runs` or `/api/overview`: assert `read_events` is never called there); a step failure is not added to the counts; a store without the permission gives zeros
- [X] T068 [P] [US5] Write front-end tests in `waypoint_monitor/static/tests/overview.test.mjs` and `run-view.test.mjs`: `mapRun` maps `eventCounts`; `countChipsHTML({warnings, errors})` returns nothing for 0/0, `2 warnings` and `1 error` chips with icons and an accessible name; the step details show at most 10 of the step's newest events and a "View all in timeline" link to `?tab=events&step=<name>`

### Implementation

- [X] T069 [US5] In `waypoint_monitor/app/api/routes.py` add `list_event_counts` to `Window`/`keys_for` (same cache), pass `event_counts=` into `build_runs` (new optional parameter in `waypoint_monitor/app/domain/analysis.py`, default empty) and add `warnings`/`errors` to the summary in `waypoint_monitor/app/domain/overview.py`; make T067 pass
- [X] T070 [P] [US5] Update `waypoint_monitor/static/js/api.js` (`eventCounts`, card `warnings`/`errors`) and add `countChipsHTML` to `waypoint_monitor/static/js/ui.js`; show the chips in `waypoint_monitor/static/js/views/home.js` and in each row of `waypoint_monitor/static/js/views/history.js`
- [X] T071 [US5] Update `waypoint_monitor/static/js/views/step.js` to list the step's events (fetched through `fetchEvents` with `step=`, newest 10) and the "View all in timeline" link; make T068 pass
- [X] T072 [P] [US5] Add styles for the count chips and the step events list in `waypoint_monitor/static/styles.css`; dark mode
- [X] T073 [US5] Run all suites, `mypy`, `ruff`, `black --check`; do quickstart section 4 step 4

---

## Phase 9: User Story 7 - Older pipelines and monitors keep working (Priority: P1)

**Goal**: Runs without the new data look right; damaged data is tolerated; the old and new halves interoperate.

**Independent Test**: View a run produced by library 0.3.0: durations correct (steps approximate), a derived timeline, no banner or error about missing data (quickstart section 5).

- [X] T074 [P] [US7] Add a regression test in `waypoint_monitor/tests/test_analysis.py`: for each existing run scenario (running, stalled, died, complete, incomplete, lost data, failed, no flow, unplanned step) the `build_runs` output with no new inputs equals the previous output plus only the new keys (`duration`, `bottleneck`, `event_counts`, and `duration_seconds`/`duration_approx` on done/failed steps); no existing assertion needed change
- [X] T075 [P] [US7] Add tests in `waypoint_monitor/tests/test_api.py` with a `FakeStore` that has no event data and finish records without the new fields: `/api/runs`, `/api/overview` and the events endpoint succeed; step durations are `duration_approx: true`; `recorded` is 0; no `unreadable` increase; a run whose finish time is before its start gives a `null` duration and no negative number anywhere (FR-003)
- [X] T076 [P] [US7] Add front-end tests in `waypoint_monitor/static/tests/model.test.mjs` and `run-view.test.mjs`: a run with `null` durations renders `—` and no `NaN`, `undefined` or negative text; the events tab for `recorded == 0` shows the derived timeline and the upgrade note only
- [X] T077 [US7] Confirm by test in `packages/waypoint_etl/tests/test_auditor.py` that finish records still contain every earlier field with the same values (a pre-0.4 monitor needs no change), and by assertion in `waypoint_monitor/tests/fakes.py` that `record_died` stays the only write the monitor makes (FR-033)

---

## Phase 10: Polish & cross-cutting

- [X] T078 [P] Update `packages/waypoint_etl/README.md`: `log`/`warn`/`error` (signature, step attachment, limits, volume caps, delivery and exit flush, `SIGKILL` note, "keep data values out of event text"), the shared privacy setting, durations in finish records; set `version = "0.4.0"` in `packages/waypoint_etl/pyproject.toml` and `__version__ = "0.4.0"` in `packages/waypoint_etl/src/waypoint_etl/__init__.py`
- [X] T079 [P] Update `waypoint_monitor/README.md`: durations (exact vs approximate, bottleneck, Slower than usual, typical values and the three settings), the Events tab and the events endpoint, derived vs author events, the **new read permission** (`LLEN`, `LRANGE`) and the degraded mode without it; update `README.md` (root) and `deploy/README.md` (permissions line, install URL tag `waypoint-etl-v0.4.0`)
- [X] T080 [P] Update `.claude/skills/adopting-waypoint-etl/SKILL.md` so adopters learn `log`/`warn`/`error`, the shared `capture_error_message`/`redact` meaning, and the Python 3.10+ standard-library-only note
- [X] T081 Run the full automated set from `specs/012-duration-and-run-events/quickstart.md` section 1 (library, monitor Python, `node --test`, `mypy`, `ruff`, `black --check` in both packages) and record the counts under "Results"
- [X] T082 Run the quickstart manual passes sections 2-5 (real Redis, Playwright at desktop 1440 and phone 390 widths), including the `<img onerror>` event-message check, the capture-off grep, the 5,000-event cap check, the Redis-down run, the previous-library run and the limited-permission monitor; record outcomes in `specs/012-duration-and-run-events/quickstart.md`
- [X] T083 Re-check the constitution table in `specs/012-duration-and-run-events/plan.md` against the final code (typing, tests, PII, resilience) and update `specs/012-duration-and-run-events/checklists/requirements.md` notes and `specs/roadmap.md` (mark items 2 and 3 done with a "Khác với đề xuất ban đầu" block like item 1: events as lists, derived automatic events, approximate durations for old runs, three settings) if any decision changed

---

## Dependencies & Execution Order

- Phase 1 first. Phase 2 blocks everything: library tasks (T003-T005) and monitor tasks (T006-T009) are independent of each other and can proceed in parallel.
- **US1** (Phase 3) needs Phase 2 only. **US2** (Phase 4) needs US1 (T014, T015, T018, T034 builds on `durations.py` and the run durations).
- **US3** (Phase 5) needs Phase 2 and the derived pieces of US1 (T015: step start times) but not US2. Its recorded-event reading is tested with fakes, so it does not need the library.
- **US4** (Phase 6) is library-only and independent of the monitor; its end-to-end value shows once US3 exists (quickstart section 4). **US6** (Phase 7) needs T057 and T059 from US4 and finishes the writer that T060 routes through.
- **US5** (Phase 8) needs US3 (T044 store methods, T048 api helpers). **US7** (Phase 9) needs US1 and US3.
- Polish last. Release order: monitor first (works with any library), then library 0.4.0 pipeline by pipeline.

Story order: US1 → US2 (roadmap item 2) and US3 ∥ US4 → US6 (roadmap item 3) → US5 → US7.

### Parallel examples

```text
Phase 2:  T003 + T005 (library tests) | T006 + T008 (monitor parsing test + settings)
US1:      T010 + T011 + T012 + T013 (tests) ; then T017 + T018 + T019 + T020 (front-end modules)
          then T022 + T023 + T024 (views, different files)
US3/US4:  Phase 5 (monitor) and Phases 6-7 (library) at the same time
US3:      T038 + T039 + T040 + T041 + T042 (tests) ; T047 + T048 + T051 (front-end helpers)
Polish:   T078 + T079 + T080
```

## Implementation Strategy

1. **MVP (roadmap item 2)**: Phases 1, 2, 3 and 4 (US1 + US2): durations and Slower than usual, which already work for every existing run. Stop here and demo with quickstart section 3.
2. Add US3 (derived timeline) next: useful with no pipeline change, and it exercises the events endpoint and tab.
3. Add US4 and US6 together (the library side of events; ship `0.4.0` only after US6 proves the non-blocking and cap guarantees), then US5 and US7.
4. Release order: monitor first, then library 0.4.0.
