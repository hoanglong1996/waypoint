---

description: "Task list for Live Step Running Indicator"
---

# Tasks: Live Step Running Indicator

**Input**: `/specs/004-step-running-indicator/` (spec, plan, research, data-model, contracts/start-marker.md, contracts/api.md, quickstart.md)

**Tests**: Included. Constitution principle IV requires tests for changed behaviour; no live Redis, CallRail or Google Ads calls in tests.

**Organization**: Grouped by user story. Paths are relative to `integrations/callraill/` unless prefixed `app/`, `static/`, `tests/` under **MONITOR** = `performance_monitoring_app/`. Run pipeline checks from `integrations/callraill` (`python -m unittest discover tests`, `black --check .`, `ruff check .`, `mypy .`), monitor checks from `performance_monitoring_app` (`pytest`, `node --test static/tests`).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 [P] Extend the test fake in `performance_monitoring_app/tests/fakes.py`: add `FakeStore.list_markers(env)` (raises `StoreUnavailable` when `fail`, returns `(key, json)` pairs whose key starts `callrail:running:<env>:`), a `markers` list on the fake, and `make_markers(env, run_id, running_index, started_at)` that builds one marker pair `callrail:running:<env>:<run_id>:<NN>-<step>` with record `{"run_id","env","step","index","started_at"}` (UTC `YYYY-MM-DDTHH:MM:SSZ`)

## Phase 2: Foundational (data flow; blocks all stories)

**Purpose**: the pipeline announces step starts and the monitor derives `running` / `waiting` states. No UI yet.

- [X] T002 In `src/application/step_audit.py` add constants `START_KEY_PREFIX = "callrail:running"` and `START_MARKER_TTL_SECONDS = 86400`; in `StepAuditor.run`, before `fn(*args)`, write key `f"{START_KEY_PREFIX}:{env}:{run_id}:{index:02d}-{name}"` with record `{"run_id","env","step","index","started_at"}` (UTC `%Y-%m-%dT%H:%M:%SZ`) via `self.store.write(key, record, START_MARKER_TTL_SECONDS)`. Wrap in its own try/except that prints `Warning: step start marker failed for {name}: {exc}` and continues. Counts and timestamps only. Keep the finish-record behaviour unchanged (contracts/start-marker.md)
- [X] T003 [P] Update `tests/application/test_step_audit.py`: the marker now goes through the same fake store, so make the existing tests count finish records only (filter `store.records` on keys starting `callrail:audit:`) in `test_record_fields_and_key`, `test_indices_are_sequential`, `test_ttl_is_30_days`, `test_custom_ttl` and `test_step_exception_propagates_and_is_not_recorded` (which must still see only `["ok"]` as finished). Then add tests: marker is written before `fn` runs (fn observes it in the fake store); key and TTL are `callrail:running:...` and 86400; record has exactly the five fields; a store that raises on the marker write still runs `fn` and writes the finish record; when `fn` raises, the marker exists and no finish record is written; `NoopStepAuditStore` works
- [X] T004 [P] Add `StartMarker` frozen dataclass (`run_id`, `env`, `step`, `index` int >= 1, `started_at` datetime) to `performance_monitoring_app/app/domain/models.py`
- [X] T005 Add `parse_markers(env, raw)` to `performance_monitoring_app/app/domain/parsing.py` with key regex `^callrail:running:(?P<env>[^:]+):(?P<run>\d{8}T\d{6}Z):(?P<idx>\d{2,})-(?P<step>.+)$`; validate `run_id`/`env`/`step` equal the key, `step` in `STEP_NAMES`, `index` int >= 1 and not bool, `started_at` parses as UTC ISO-8601; return `List[StartMarker]`; invalid markers are dropped silently and never counted as unreadable audit records
- [X] T006 [P] Add parsing tests in `performance_monitoring_app/tests/test_parsing.py`: valid marker parsed; wrong env, bad run id, unknown step, index 0, bool index, bad time, non-JSON, wrong key shape each dropped with no exception and `unreadable_total` of the audit parse unchanged
- [X] T007 Add `list_markers(self, env: str) -> List[Tuple[str, str]]` to the `RecordStore` protocol in `performance_monitoring_app/app/infrastructure/store.py` ("Return `(key, raw_json)` pairs for every start marker of `env`. Read only.") and implement it in `app/infrastructure/redis_store.py` by the same SCAN + `mget` batching as `list_records` using pattern `callrail:running:{env}:*`, mapping `redis.RedisError` to `StoreUnavailable`
- [X] T008 [P] Add tests for `list_markers` in `performance_monitoring_app/tests/test_redis_store.py` (returns pairs, skips expired `None` values, wraps `RedisError`) mirroring the existing `list_records` tests
- [X] T009 In `performance_monitoring_app/app/domain/analysis.py` change `build_runs(parsed, env, now, stale_hours)` to also take optional `markers: Sequence[StartMarker] = ()` and `stall_seconds: float = 900.0` (defaults keep existing callers and tests working), and give every step in `steps` a `state`: `done` (finish record; add nothing else), `running` (no finish record, marker exists, `now - started_at <= stall_seconds`; fields `started_at`, `elapsed_seconds = max(0, int(...))`, no `inputs`/`output`), `waiting` (no record, no marker, run has a live running step with a lower definition index), `missing` (everything else; keep `missing: True`). A finish record always overrides a marker. `missing: True` only for state `missing`. Run gets `status` `"running"` when a live running step exists (else `complete`/`incomplete` as today), new `running_step` (name or `None`), `stale = False` while running, and `first_missing_step` / `missing_count` count only `missing` steps. A run that has only markers (no finish records yet) still exists. Do not implement `stalled` here (T030)
- [X] T010 [P] Add analysis tests in `performance_monitoring_app/tests/test_analysis.py`: marker + earlier records gives one `running` step, later steps `waiting`, `status == "running"`, `stale is False`, `missing_count == 0`; finish record beats marker; skipped earlier step stays `missing`; marker-only run exists with step 1 running; overlapping runs: only the run with the marker has a running step; `elapsed_seconds` never negative when `started_at` is after `now`; run without markers is byte-for-byte as before apart from the new `state`/`running_step` keys
- [X] T011 In `performance_monitoring_app/app/api/routes.py` read markers in the same cached window as records (cache the pair `(records, markers)` per env under the existing `cache_seconds`; clear the cache on `StoreUnavailable` from either call) and pass `parse_markers(env, markers)` and `settings.stall_seconds` to `build_runs`. Add `"stall_seconds": settings.stall_seconds` to `/api/config` (contracts/api.md)
- [X] T012 In `performance_monitoring_app/app/config.py` add `stall_seconds: float = 900.0` read from `STALL_SECONDS` via `_float`
- [X] T013 [P] Add API tests in `performance_monitoring_app/tests/test_api.py`: `/api/runs` returns `status: "running"`, `running_step`, and per-step `state` for a fake store with a marker; `/api/config` includes `stall_seconds`; `FakeStore.fail` on markers yields 503 `Data store unavailable`; older runs have no running step. Add `STALL_SECONDS` default and override to `tests/test_config.py`

**Checkpoint**: `python -m unittest discover tests` and `pytest` pass; `curl /api/runs` shows a `running` step against a hand-written marker.

## Phase 3: User Story 1 - See which step is running right now (P1) 🎯 MVP

**Goal**: the running step shows a spinner, progress bar and "Running" on the graph node and the list card; waiting steps read "Waiting"; a running run is not shown as failed or stale.

**Independent Test**: with a marker for step 4 and finish records for steps 1-3 (quickstart §2), exactly one step shows the loading indicator and "Running", steps 5-9 show "Waiting", and no stop/stale warning appears. With OS reduced motion on, nothing animates.

- [X] T014 [P] [US1] In `performance_monitoring_app/static/js/model.js` add `stepState(step)` (returns `step.state`, falling back to `missing ? 'missing' : 'done'` for old payloads), make `isLoss` and `metric` return false/`null` for any state other than `done`, make `headline(run)` read counts only from `done` steps, and extend `analyse(run)` with `running: run.status === 'running'` and `runningStep: run.runningStep`. In `static/js/api.js` map snake_case `running_step`, `started_at`, `elapsed_seconds`, `state` to camelCase like the existing fields
- [X] T015 [P] [US1] Add tests to `performance_monitoring_app/static/tests/model.test.mjs`: `stepState` for each value and the legacy fallback; `isLoss`/`metric` ignore running and waiting steps; `analyse` flags `running`; `headline` ignores a running `read_callrail_call`
- [X] T016 [US1] In `performance_monitoring_app/static/js/graph-model.js` extend `nodeStates(run)` so `running` and `waiting` steps get states `running` and `waiting` (never `stopped`/`unreached`/`affected`), and `edgeInfo` returns `inactive` unless both producer and consumer are `done`
- [X] T017 [P] [US1] Add tests to `performance_monitoring_app/static/tests/graph-model.test.mjs`: running node state, waiting nodes, no `stopped` while a run is running, edges into running/waiting steps inactive, edges between done steps unchanged
- [X] T018 [US1] Add CSS to `performance_monitoring_app/static/styles.css`: `--running` and `--running-bg` tokens in the light block and both dark blocks; `.step--running`, `.step--waiting` card styles; `.spinner` (CSS-only ring, `@keyframes`), `.step__progress` indeterminate bar (a moving segment inside a track), `.gnode--running` pulsing outline, `.gnode--waiting` dotted outline; and a `@media (prefers-reduced-motion: reduce)` block that stops every new animation and shows the spinner as a static partial ring and the bar as a static filled segment
- [X] T019 [P] [US1] In `performance_monitoring_app/static/js/ui.js` add `spinner` and `hourglass` icons (aria-hidden SVG) to `I`, and a `running` variant of `statusPill(a, size)`: when `a.running` return a non-error pill (`pill--run` style, spinner icon, text `Running`) instead of the red `Incomplete` pill; add `.pill--run` to `static/styles.css` using the `--running` tokens from T018. Used by the latest-run header and History rows (T022)
- [X] T020 [US1] In `performance_monitoring_app/static/js/views/step.js` render states in `stepItemHTML`: `running` shows the spinner, text `Running` and a `.step__progress` bar and an inputs row of `input pending`; `waiting` shows `Waiting` with the hourglass; neither shows "No record" or "Step did not report". The card's `aria-label` ends `running` / `waiting`. Escape all API-derived text
- [X] T021 [US1] In `performance_monitoring_app/static/js/views/graph.js` render `running` and `waiting` nodes with the matching classes, spinner or hourglass icon, visible text `Running` / `Waiting`, full accessible label, tooltip text (state, no counts), and `Selected step` panel support via the updated `stepItemHTML`
- [X] T022 [US1] In `performance_monitoring_app/static/js/views/latest.js` make the headline numbers, summary line ("N of 9 steps reported"), stale warning and stop/loss callouts treat `analyse(run).running` as in progress: summary reads `Running: <step>` and neither "stopped at" nor the stale warning is shown; completed runs unchanged. Apply the same in `static/js/views/history.js` so History rows and the drawer summary of a running run use the `Running` pill from T019 (not `Incomplete`) and the drawer's "Incomplete run / First missing step" banner is not shown for it
- [X] T023 [US1] Verify quickstart §2 steps 1-3 and 6 in a browser (Graph and List, light and dark, 375 px and desktop); fix any visual issue

**Checkpoint**: MVP: running step visible everywhere it is drawn.

## Phase 4: User Story 2 - The page updates itself every 5 seconds (P1)

**Goal**: the monitor reloads every 5 s without losing selection and without flicker.

**Independent Test**: leave the page alone while a step finishes: within about 5 s its counts appear and the indicator moves on; selected step, view, env and History run unchanged; the spinner does not restart on every poll.

- [X] T024 [US2] Change defaults in `performance_monitoring_app/app/config.py`: `refresh_seconds: int = 5` and `_int("REFRESH_SECONDS", 5)`; `cache_seconds: int = 2` and `_int("CACHE_SECONDS", 2)`; update `tests/test_config.py` defaults accordingly
- [X] T025 [P] [US2] Add `runSignature(runs)` to `performance_monitoring_app/static/js/model.js`: `JSON.stringify` of the runs with `ageSeconds` and `elapsedSeconds` removed from every run and step (stable key order) and adding `Math.floor(ageSeconds / 60)` per run (a one-minute age bucket, so "ended Xm ago" text and the stale flag still refresh at most once a minute; a running run's age bucket is left out so its spinner is never restarted by it), so only meaningful changes differ; add tests in `static/tests/model.test.mjs` (equal when only age within the same minute or elapsed differ; different when the age crosses a minute for a non-running run; equal across minutes for a running run; different when a step state, count or status changes; different when a run is added)
- [X] T026 [US2] In `performance_monitoring_app/static/js/app.js` `refresh()`: after a successful fetch compute `runSignature(data.runs)`; if it equals `state.signature` and the previous status was `ok`, update only `state.lastOkAt`, call `syncLive()` and `schedule(...)` without calling `render()`; otherwise store the signature and render as today. Reset `state.signature` on env change and on error. Selection and view stay untouched either way
- [X] T027 [US2] In `performance_monitoring_app/static/js/app.js` add a `visibilitychange` listener that calls `refresh()` when the tab becomes visible and `state.status !== 'loading'`, so a returning tab catches up at once (edge case: background tab)
- [X] T028 [US2] Update the env var table in `performance_monitoring_app/README.md`: `REFRESH_SECONDS` default `5`, `CACHE_SECONDS` default `2`, new `STALL_SECONDS` (default `900`, seconds before a running step is shown as Stalled); mention the 5 s polling and that markers expire after 24 h
- [ ] T029 [US2] (Steps 3-4 verified 2026-10-16 against an in-memory demo store: 5 polls in 25 s, same DOM node kept, selection kept across a step change, 503 path covered by API tests. Still open: the real QA run of §3.) Verify quickstart §2 steps 3-4 and §3 (real QA run): no manual refresh needed, selection kept, spinner not restarting, "Updated" label advancing, unreachable store still shows the error card and retries

## Phase 5: User Story 3 - Tell a stalled run from a slow step (P2)

**Goal**: elapsed time on a running step; a step past the stall limit reads "Stalled" with no animation.

**Independent Test**: set `STALL_SECONDS=30`, leave a marker with no finish record: the step counts up, then reads `Stalled · <elapsed>` with no animation and counts as the run's stop point.

- [X] T030 [US3] In `performance_monitoring_app/app/domain/analysis.py` add state `stalled` (marker exists, no finish record, `elapsed_seconds > stall_seconds`; fields `started_at`, `elapsed_seconds`): a stalled step is not `running`, does not make the run `running`, counts in `first_missing_step` / `missing_count` as the first stop point, and `stale` follows the existing age rule. Steps after it are `missing`, not `waiting`
- [X] T031 [P] [US3] Add analysis tests in `performance_monitoring_app/tests/test_analysis.py`: exactly at the limit is still `running`, one second over is `stalled`; stalled run `status == "incomplete"`, `first_missing_step` is the stalled step, later steps `missing`; a late finish record turns a stalled step `done`; and API test in `tests/test_api.py` with `Settings(stall_seconds=...)`
- [X] T032 [P] [US3] Add `elapsedLabel(seconds)` in `performance_monitoring_app/static/js/model.js` (`42 s`, `3m 05s`, `1h 02m`, never negative) with tests in `static/tests/model.test.mjs`
- [X] T033 [US3] In `performance_monitoring_app/static/js/views/step.js` and `static/js/views/graph.js` show `Running · <elapsed>` using a `<span data-elapsed="<seconds at fetch>" data-fetched="<ms>">` element, and render `stalled` with a static warning icon (not the spinner), text `Stalled · <elapsed>`, class `step--stalled` / `gnode--stalled`, and the same "stopped here" emphasis as the existing Not reported node. Add `.step--stalled`, `.gnode--stalled` styles to `static/styles.css` using existing warning tokens plus an icon and text, not colour alone
- [X] T034 [US3] In `performance_monitoring_app/static/js/app.js` extend the existing 1-second ticker (`syncLive` caller) to update every `[data-elapsed]` node as `elapsedLabel(max(0, elapsed + (Date.now() - fetched)/1000))`, so elapsed time counts up between 5-second reloads without redrawing; skip it under no running steps
- [X] T035 [US3] Verify quickstart §2 step 5 with `STALL_SECONDS=30`, and that an old complete run opened from History never shows a running or stalled indicator

## Phase 6: Polish

- [X] T036 [P] Run `black --check .`, `ruff check .`, `mypy .` and `python -m unittest discover tests` in `integrations/callraill`, and `pytest` plus `node --test static/tests` in `performance_monitoring_app`; fix findings
- [X] T037 [P] Update `README.MD` (pipeline) with the `callrail:running:*` key family, its 24 h TTL and that it holds only counts/timestamps; note in the PR how PII scrubbing is unaffected (constitution workflow)
- [ ] T038 (Needs a real pipeline run against QA Redis; not done.) Run the full quickstart (`specs/004-step-running-indicator/quickstart.md`) against QA once with a real pipeline run and record the measured result (time from step finish to page update) in the PR description

## Dependencies & Execution Order

- Phase 1 -> Phase 2 -> US1 -> US2, US3. US2 and US3 can proceed in parallel after US1 (US2 touches `app.js`/config; US3 touches analysis and step/graph views); T033/T034 touch files US1 edited, so sequence them after T020-T022.
- Inside Phase 2: T002 before T003; T004 before T005; T005 before T009 and T011; T007 before T011; T009 before T010; T011 and T012 before T013.
- US1: T014 before T015/T016/T020-T022; T018 and T019 before T020/T021; T023 last.
- US2: T024 and T025 before T026; T028 and T029 last.
- US3: T030 before T031/T033; T032 before T033/T034.

## Parallel opportunities

- Phase 2: T003, T004, T006, T008, T010 (different test/model files once their targets exist).
- US1: T015, T017, T019 together; then T020/T021/T022 are separate files and can be split.
- Pipeline work (T002-T003) and monitor backend (T004-T013) can be done by different people.

## Implementation Strategy

1. **MVP** = Phases 1-3: pipeline writes markers, monitor derives states, running step visible (reload still at the old 60 s until US2; use the page's Retry/browser refresh while testing).
2. Add Phase 4 (5 s auto reload) next: this completes both P1 stories.
3. Add Phase 5 (stalled, elapsed) and Phase 6 polish.
4. Deploy order: the monitor first (it ignores a missing marker family safely), then the pipeline image, so markers never arrive before a reader exists.
