---

description: "Task list for Run Liveness Heartbeat"
---

# Tasks: Run Liveness Heartbeat

**Input**: Design documents from `/specs/009-run-liveness-heartbeat/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (redis-keys.md, api.md), quickstart.md

**Tests**: Included and written first. The constitution (principle IV) requires tests for changed behaviour, and the agreed workflow is test-first: each story's tests must fail before its implementation. No live Redis, CallRail, Google Ads or Sentry is used in tests.

**Organization**: Tasks are grouped by user story. Two code bases are touched: the library (`packages/waypoint_etl`, "L") and the monitor (`waypoint_monitor`, "M"); all paths below are relative to `integrations/callraill/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: user story from spec.md (US1 to US5)

## Phase 1: Setup

**Purpose**: Know the starting point so "legacy behaviour unchanged" (SC-003) can be proven.

- [X] T001 Record the baseline: run `python -m unittest discover tests` in `packages/waypoint_etl` and in `waypoint_monitor` and `node --test static/tests` in `waypoint_monitor`; note the passing counts (the legacy behaviour that must not change, SC-003).
- [X] T002 [P] Confirm lint and type tooling runs clean before changes: `black --check . && ruff check . && mypy .` in `packages/waypoint_etl` and in `waypoint_monitor` (config in each `pyproject.toml`).

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Shared building blocks used by every story: key helper, data classes, parsing, store access (read and the one write), test fakes and the setting.

**CRITICAL**: No user story starts until this phase is complete.

- [X] T003 [P] Write the failing test for `alive_key(pipeline, env, run_id)` returning `waypoint:{pipeline}:{env}:{run_id}:alive` in `packages/waypoint_etl/tests/test_keys.py`, then add `alive_key` and `HEARTBEAT_SECONDS = 15` to `packages/waypoint_etl/src/waypoint_etl/keys.py`.
- [X] T004 [P] Add frozen dataclasses `AliveSignal(pipeline, env, run_id, beat_at: datetime)` and `DiedVerdict(pipeline, env, run_id, judged_at: datetime, last_seen_at: datetime)` to `waypoint_monitor/app/domain/models.py` (fields per data-model.md; datetimes are UTC).
- [X] T005 Write failing parsing tests in `waypoint_monitor/tests/test_parsing.py`: `parse_alive` and `parse_died` return the signal/verdict for valid items; return nothing for invalid JSON, wrong `pipeline`/`env`/`run_id` versus the key, missing or unreadable time, and a key of another kind; never raise and never count anything as unreadable.
- [X] T006 Implement `_ALIVE_KEY`/`_DIED_KEY` patterns (`waypoint:{pipeline}:{env}:{run_id}:alive|died`), `parse_alive(env, pipeline, raw) -> Dict[str, AliveSignal]` and `parse_died(env, pipeline, raw) -> Dict[str, DiedVerdict]` (keyed by run id) in `waypoint_monitor/app/domain/parsing.py`, reusing `_parse_time`.
- [X] T007 [P] Extend the `RecordStore` protocol in `waypoint_monitor/app/infrastructure/store.py` with `list_alive(env, pipeline)`, `list_died(env, pipeline)` (both return `(key, raw_json)` pairs, read only) and `record_died(key: str, value: str, alive_key: str) -> bool` (`SET NX`, returns False on any failure, never raises).
- [X] T008 [P] Extend `FakeStore` in `waypoint_monitor/tests/fakes.py` with `alive` and `died` lists, `list_alive`, `list_died`, `record_died` (honours NX: returns False if the key exists; `fail_write` flag makes it return False; counts calls) and helpers `make_alive(env, run_id, beat_at, pipeline=PIPELINE)` and `make_died(env, run_id, judged_at, last_seen_at, pipeline=PIPELINE)`; make `list_pipelines` ignore nothing new.
- [X] T009 Write failing tests in `waypoint_monitor/tests/test_redis_store.py` (following that file's fake client): `list_alive`/`list_died` scan only `...:*:alive` / `...:*:died`; `record_died` issues one `SET key value NX PX <PTTL of the alive key>` with fallback 30 days when PTTL is unavailable (-1/-2); returns False and does not raise on `redis.RedisError` including a NOPERM response; no other write or delete command is ever issued.
- [X] T010 Implement `list_alive`, `list_died` and `record_died` in `waypoint_monitor/app/infrastructure/redis_store.py` (uses `_scan`, `pttl`, `set(..., nx=True, px=...)`; catches `redis.RedisError`; logs a warning at most once a minute).
- [X] T011 [P] Add `heartbeat_dead_seconds: float = 90.0` to `Settings` and read `HEARTBEAT_DEAD_SECONDS` via `_float` in `waypoint_monitor/app/config.py` (an unset or invalid value gives 90.0).

**Checkpoint**: The monitor can read and parse alive items and verdicts and can record a verdict; the library knows the key. Nothing user-visible changes yet.

---

## Phase 3: User Story 1 - See at once that a run has died (Priority: P1) MVP

**Goal**: A killed run is shown as Died within about 90 s plus refresh, with the open step, last-seen time, an attention-flagged home card, and a verdict that stays (clarifications 1 and 2). The library sends the beats that make this possible.

**Independent Test**: Seed or start a run with beats, stop it abruptly mid-step, wait past `HEARTBEAT_DEAD_SECONDS`: the run page and home card show Died with last-seen time; restarting the monitor keeps it Died; `redis-cli keys 'waypoint:*:died'` shows one item (quickstart 2 and 4).

### Tests for User Story 1 (write first, they must fail)

- [X] T012 [P] [US1] Write failing tests in `waypoint_monitor/tests/test_analysis.py`: (a) alive item older than `dead_seconds` + open marker, no record -> run `status` `incomplete`, `died` = `{judged_at, last_seen_at, recorded: false}`, open step state `died` with `started_at` and `last_seen_at`, later planned steps `missing` (never `waiting`), `running_step` None, `first_missing_step` set; (b) died between steps (no open marker) and the just-started case (flow only, stale beat) -> Died, not `waiting`/starting; (c) all planned steps recorded + stale beat -> not Died (FR-013); (d) a stored verdict -> Died with `recorded: true` even when the beat is now fresh or the run later shows all steps (FR-007a).
- [X] T013 [P] [US1] Write failing tests in `waypoint_monitor/tests/test_overview.py`: a Died latest run gives `card_status` `died` (rule order running, died, stale, incomplete, lost, ok), `needs_attention` true, sorted among the problem cards, and `latest.died_step` and `latest.last_seen_at` are set.
- [X] T014 [P] [US1] Write failing tests in `waypoint_monitor/tests/test_api.py`: `/api/runs` returns `died` and step state `died` for a stale beat; the first view calls `record_died` once with a verdict holding `judged_at` and `last_seen_at`; later views (and a second app instance sharing the store) read the stored verdict and do not write again; with `fail_write` the response is still 200 with the run Died and the write is retried on the next view (FR-007d); after a successful write the cache entry is dropped; two simultaneous judgements leave one verdict (second `record_died` returns False and the view is still consistent, FR-007e).
- [X] T015 [P] [US1] Write failing tests in `packages/waypoint_etl/tests/test_heartbeat.py`: with a fake store and `heartbeat_seconds=0.05`, `init` writes the alive item immediately, then repeats; key is `alive_key(...)`; value is `{v: 1, pipeline, env, run_id, beat_at}` with `beat_at` UTC `%Y-%m-%dT%H:%M:%SZ`; ttl equals `ttl_days * 86400`; the value contains identities and times only (FR-002).
- [X] T016 [P] [US1] Write failing front-end tests in `waypoint_monitor/static/tests/model.test.mjs`, `waypoint_monitor/static/tests/overview.test.mjs` and `waypoint_monitor/static/tests/graph-model.test.mjs`: step state `died` maps through `api.js`; a Died card gets kind `died` with step and last-seen age; `died` is a stop point in graph-model like `stalled` (later missing steps are unreached).

### Implementation for User Story 1

- [X] T017 [US1] Implement the judgement in `waypoint_monitor/app/domain/analysis.py`: extend `build_runs`/`_build_run` with `alive: Mapping[str, AliveSignal]`, `verdicts: Mapping[str, DiedVerdict]`, `dead_seconds: float = 90.0`; a run is Died when a verdict exists, or an alive item exists, work is unfinished (a planned step has no record, or a marker has no record, or the run is just started) and `now - beat_at > dead_seconds`; Died runs: open step `died`, later planned steps `missing`, no `running_index`/starting, `status` `incomplete`, add `died` object to the run dict and `last_seen_at` on died steps; alive items never create a run on their own.
- [X] T018 [US1] Update `waypoint_monitor/app/domain/overview.py`: `card_status` returns `died` right after `running`; add `died` to `ATTENTION`; `_summary` adds `died_step` and `last_seen_at`.
- [X] T019 [US1] Wire `waypoint_monitor/app/api/routes.py`: `keys_for` also reads `list_alive` and `list_died` in the same cached window; `build` passes `parse_alive`, `parse_died` and `settings.heartbeat_dead_seconds` to `build_runs`; for each run with `died` and `recorded` false call `store.record_died` (verdict value per data-model.md), set `recorded` true on success and drop the cache entry for that (env, pipeline); on False keep the Died view and log a throttled warning; never raise.
- [X] T020 [P] [US1] Create `packages/waypoint_etl/src/waypoint_etl/heartbeat.py`: class `Heartbeat(store, key, value_factory, interval, ttl_seconds)` with `start()` (daemon `threading.Thread`, writes immediately, then every `interval` via `threading.Event.wait`) and `stop()` (sets the event, joins up to 1 s); each write is wrapped so no exception escapes (print `Warning: Waypoint heartbeat failed: ...`).
- [X] T021 [US1] Wire the heartbeat in `packages/waypoint_etl/src/waypoint_etl/auditor.py` (`StepAuditor` gets `heartbeat_seconds`, `start_heartbeat()`, `stop()`) and `packages/waypoint_etl/src/waypoint_etl/registry.py` (`init(..., heartbeat_seconds: Optional[float] = HEARTBEAT_SECONDS)` starts it after `auditor.start()`; `clear()` stops the active one).
- [X] T022 [P] [US1] Bump the library to 0.2.0 in `packages/waypoint_etl/pyproject.toml` and `__version__` in `packages/waypoint_etl/src/waypoint_etl/__init__.py`.
- [X] T023 [P] [US1] Add the Died state to the front-end data layer: `waypoint_monitor/static/js/api.js` (map step state `died`, `last_seen_at`, card `died_step`/`last_seen_at`) and `waypoint_monitor/static/js/model.js` (card kind `died`, text parts, step state list in the doc comment).
- [X] T024 [P] [US1] Add Died to the graph: `waypoint_monitor/static/js/graph-model.js` (stop point like `stalled`), `waypoint_monitor/static/js/views/graph.js` (label `Died`, state text, icon, pill `gpill--died`, header text `died at <step>`), and `waypoint_monitor/static/styles.css` (`.gpill--died`, `.step--died` using the existing error colour tokens, visibly different from `--stalled`).
- [X] T025 [P] [US1] Show Died on the pages: `waypoint_monitor/static/js/views/home.js` (card line `Died at <step>, last seen <age> ago`, attention flag), `waypoint_monitor/static/js/views/latest.js` and `waypoint_monitor/static/js/views/step.js` (died step detail with last-seen time, no live counter).
- [X] T026 [P] [US1] Add a died-run demo to `waypoint_monitor/tests/seed_demo.py` (a run with a stale alive item and an open marker) so the Died view can be checked visually.

**Checkpoint**: User Story 1 is fully functional and testable on its own (the MVP).

---

## Phase 4: User Story 2 - Tell a hung run from a dead one (Priority: P1)

**Goal**: An alive-but-stuck run is shown as Running then Stalled, clearly different from Died; stopping its beats turns it Died.

**Independent Test**: Quickstart scenario 3: beating run with a blocked step shows Running then Stalled, never Died; kill it and it becomes Died.

### Tests for User Story 2

- [X] T027 [P] [US2] Write tests in `waypoint_monitor/tests/test_analysis.py` for hung versus dead: fresh beat + open marker within `stall_seconds` -> `running`; fresh beat + marker older than `stall_seconds` -> `stalled`, never `died`; the same run with the beat aged past `dead_seconds` -> `died`; slow-but-progressing run (records arriving, fresh beat) stays `running`.
- [X] T028 [P] [US2] Write a front-end test in `waypoint_monitor/static/tests/overview.test.mjs` (the card rules live there) that a `stalled` card and a `died` card produce different status words, reasons and time kinds.

### Implementation for User Story 2

- [X] T029 [US2] Make the copy tell hung from dead in `waypoint_monitor/static/js/views/graph.js` and `waypoint_monitor/static/js/views/home.js`: Stalled reads `alive but not progressing`, Died reads `process gone, last seen <age> ago`; adjust `waypoint_monitor/static/js/views/step.js` accordingly (SC-005).

**Checkpoint**: Hung and dead are distinguishable from the run page alone.

---

## Phase 5: User Story 3 - Older pipelines keep working unchanged (Priority: P2)

**Goal**: Runs without alive items look exactly as today; monitors without the feature ignore the new keys.

**Independent Test**: The old test suite passes unchanged; a store holding alive and died items produces no unreadable counts in the old scan patterns.

### Tests for User Story 3

- [X] T030 [P] [US3] Write regression tests in `waypoint_monitor/tests/test_analysis.py` and `waypoint_monitor/tests/test_api.py`: runs with no alive item, an invalid alive item, or an alive item of another run behave exactly as before (marker older than `stall_seconds` -> `stalled`, never `died`; `died` is null); the pre-existing tests pass unchanged.
- [X] T031 [P] [US3] Write a compatibility test in `waypoint_monitor/tests/test_redis_store.py`: the three scan patterns used by `list_flows`, `list_records`, `list_markers` (`*:flow`, `*:step:*`, `*:running:*`) never match `...:alive` or `...:died` keys (use `fnmatch`), so a monitor without this feature ignores them (FR-014).
- [X] T032 [P] [US3] Write a test in `waypoint_monitor/tests/test_api.py` that a store holding alive and died items yields `unreadable_total` 0 and no extra runs or pipelines from alive/died items alone.

### Implementation for User Story 3

- [X] T033 [US3] Fix whatever the three tests above expose in `waypoint_monitor/app/domain/parsing.py` and `waypoint_monitor/app/domain/analysis.py` (invalid alive item = legacy, alive/died never create a run); if all pass without change, record that in the task notes.

**Checkpoint**: Rollout order of library and monitor does not matter (SC-007).

---

## Phase 6: User Story 4 - Sending the signal never harms the pipeline (Priority: P2)

**Goal**: A slow, failing or unreachable store never changes pipeline results or speed; the heartbeat stops when auditing is cleared and never keeps the process alive.

**Independent Test**: Quickstart scenario 5 (Redis stopped while a pipeline runs) plus the tests below.

### Tests for User Story 4

- [X] T034 [P] [US4] Write failing tests in `packages/waypoint_etl/tests/test_heartbeat.py`: with a store whose `write` raises, `init` and `audited_step` calls complete with identical results and only warnings are printed (throttled to at most one per minute per heartbeat); a step is not delayed by more than 0.2 s when the store blocks 1 s per write (SC-004).
- [X] T035 [P] [US4] Write failing tests in `packages/waypoint_etl/tests/test_heartbeat.py`: after `waypoint_etl.registry.clear()` no further beats are written; a second `init` stops the first run's heartbeat and starts a new one; the thread is a daemon (`thread.daemon is True`) so a process with a running heartbeat can exit; `heartbeat_seconds=None` or `<= 0` starts no thread.

### Implementation for User Story 4

- [X] T036 [US4] Harden `packages/waypoint_etl/src/waypoint_etl/heartbeat.py` and `packages/waypoint_etl/src/waypoint_etl/registry.py`: throttle repeated warnings, `stop()` is idempotent and bounded, `init` replaces and stops a previous heartbeat, `heartbeat_seconds` of `None` or `<= 0` disables it.

**Checkpoint**: Heartbeat is safe by construction (FR-004, FR-005, SC-004).

---

## Phase 7: User Story 5 - Tune how quickly death is declared (Priority: P3)

**Goal**: The death-detection time is a documented setting with a 90 s default.

**Independent Test**: Change `HEARTBEAT_DEAD_SECONDS` and observe `/api/config` and the Died threshold change.

### Tests for User Story 5

- [X] T037 [P] [US5] Write failing tests in `waypoint_monitor/tests/test_config.py`: `HEARTBEAT_DEAD_SECONDS` unset -> 90.0; set to `30` -> 30.0; invalid text -> 90.0.
- [X] T038 [P] [US5] Write failing tests in `waypoint_monitor/tests/test_api.py`: `/api/config` contains `heartbeat_dead_seconds`; with the setting at 30 a beat 40 s old is Died and 20 s old is not; at the default 90 a beat 100 s old is Died and 80 s old is not.

### Implementation for User Story 5

- [X] T039 [US5] Expose `heartbeat_dead_seconds` in the `/api/config` response in `waypoint_monitor/app/api/routes.py` and add `HEARTBEAT_DEAD_SECONDS=90` (commented) to `waypoint_monitor/.env.example`.

**Checkpoint**: All five stories work.

---

## Phase 8: Polish and cross-cutting concerns

**Purpose**: Documentation (FR-015), quality gates and end-to-end validation.

- [X] T040 [P] Update `waypoint_monitor/README.md`: new keys under "What it reads", `HEARTBEAT_DEAD_SECONDS` in the configuration table, the Died state in "Pages" and card status order, the clock-skew limit, and replace the "it never writes or deletes" statement and the Security section with the one permitted write (`SET NX` of `...:died`) and the Redis permissions it needs (contracts/redis-keys.md rule 6).
- [X] T041 [P] Update `packages/waypoint_etl/README.md`: document `heartbeat_seconds` (default 15, `None` disables), the alive item, that it never raises or blocks, and the 0.2.0 version.
- [X] T042 [P] Add a pointer to `specs/009-run-liveness-heartbeat/contracts/redis-keys.md` at the end of `specs/007-rename-to-waypoint/contracts/redis-keys.md`, and note the new library version and the monitor Redis write permission in `deploy/README.md`.
- [X] T043 Run `black . && ruff check . && mypy .` and the full test suites (`python -m unittest discover tests`, `node --test static/tests`) in `packages/waypoint_etl` and `waypoint_monitor`; fix findings; confirm the legacy tests from T001 still pass with the same counts.
- [X] T044 Run the scenarios of `specs/009-run-liveness-heartbeat/quickstart.md` against a throwaway Redis (dead run, hung versus dead, permanent verdict, legacy run, Redis down, read-only account) and record the results with the date in `specs/009-run-liveness-heartbeat/quickstart.md`.

---

## Dependencies and execution order

### Phase dependencies

- Setup (Phase 1) has no dependencies.
- Foundational (Phase 2) depends on Setup and blocks all stories.
- User stories depend only on Foundational; US1 is the MVP. US2 reuses the judgement built in US1 (it adds tests, copy and a distinction check), so do US1 first. US3, US4 and US5 can run in parallel with each other once US1 is complete.
- Polish depends on the stories you ship.

### Within each story

- Tests first and failing, then implementation.
- Domain (`analysis.py`, `overview.py`) before routes; routes before front end; library `heartbeat.py` before `auditor.py`/`registry.py` wiring.
- Tasks that edit the same file are not marked [P] (for example the several tests in `waypoint_monitor/tests/test_analysis.py` and `waypoint_monitor/tests/test_api.py` should be added one task at a time).

### Parallel opportunities

- Phase 2: the key helper (L), data classes, store protocol, fakes and setting touch different files and can run together; parsing, store implementation and their tests are sequential pairs.
- US1: the five test tasks are in different files and run together; then `analysis.py` -> `overview.py` -> `routes.py` in order, while the library work (`heartbeat.py`, version bump) and the front-end tasks proceed in parallel with the monitor back end.
- The library (L) and monitor (M) tracks are independent until quickstart validation.

### Parallel example: User Story 1

```text
Tests together: test_analysis.py, test_overview.py, test_api.py (M), test_heartbeat.py (L), static/tests/*.mjs (M)
Then in parallel: monitor back end (analysis -> overview -> routes) | library (heartbeat.py -> auditor/registry) | front end (api/model -> graph -> pages)
```

---

## Implementation strategy

### MVP first (User Story 1)

1. Phase 1 and Phase 2.
2. Phase 3 (User Story 1): tests fail, then implement.
3. Stop and validate with quickstart scenarios 2 and 4. This already fixes "I can't tell that my run died, and I wait 15 minutes".

### Incremental delivery

1. Add US2 (hung versus dead) and ship: distinction in the UI copy.
2. Add US3 and US4 together: compatibility and safety proofs; ship the library 0.2.0 only after US4 is green.
3. Add US5 (tuning), then Polish and validation.

### Notes

- Deployment: the library (0.2.0) and the monitor can ship in either order; the monitor's Redis account needs write permission on `waypoint:*:died` for the verdict to persist (contracts/redis-keys.md rule 6).
- Commit after each task or logical group; branch `009-run-liveness-heartbeat`.
- Out of scope (spec Assumptions): failure-reason records, buffered writes, a run-finished record, push alerts.
