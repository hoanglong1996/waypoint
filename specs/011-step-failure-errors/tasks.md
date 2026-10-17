---

description: "Task list for Step Failure Errors"
---

# Tasks: Step Failure Errors

**Input**: Design documents from `/specs/011-step-failure-errors/`

**Prerequisites**: plan.md, spec.md, research.md (R1-R13), data-model.md, contracts/{redis-keys,library-api,api,ui}.md, quickstart.md

**Tests**: Included. The constitution (principle IV) requires tests for changed behaviour, and spec FR-015 needs regression tests for unchanged old runs.

**Organization**: Grouped by user story. Paths are relative to the repository root. `LIB` = `packages/waypoint_etl`, `MON` = `waypoint_monitor`.

**Conventions**: Python is fully typed (`mypy --strict`), `ruff` + `black` line length 100; library supports Python 3.10+ and uses only the standard library. Test runners: `python -m unittest discover tests` (in `LIB` and in `MON`), `node --test static/tests/*.test.mjs` (in `MON`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1-US5 (from spec.md)

## Phase 1: Setup

- [X] T001 Run the baseline before changing anything: in `packages/waypoint_etl` and in `waypoint_monitor` run `python -m unittest discover tests`, `mypy`, `ruff check .`, `black --check .`; in `waypoint_monitor` run `node --test static/tests/*.test.mjs`. Record the pass counts under "Baseline" in `specs/011-step-failure-errors/quickstart.md` so later failures can be attributed

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: The failure item can be written by the library and read (parsed, passed to the analysis) by the monitor. No display change yet.

### Library: record a failure

- [X] T002 [P] Write `packages/waypoint_etl/tests/test_keys.py` additions: `failed_key("callrail", "prod", "20261017T020000Z", 2, "read_x")` == `"waypoint:callrail:prod:20261017T020000Z:failed:02-read_x"`; run and confirm it fails
- [X] T003 Add `failed_key(pipeline, env, run_id, index, step)` to `packages/waypoint_etl/src/waypoint_etl/keys.py` (same format as `step_key` with `failed` in place of `step`) so T002 passes
- [X] T004 [P] Write `packages/waypoint_etl/tests/test_errors.py` for a new `build_error(exc, *, capture_message=True, redact=None) -> dict` in `waypoint_etl/errors.py` (the last two parameters are exercised in US3; here use defaults): `type` is the fully qualified class name (`ValueError`, `json.decoder.JSONDecodeError`; builtins without module) and at most 200 characters; `message` is `str(exc)` cut to 500 characters ("message ≤ 500 characters"); `traceback` contains file, line number, function and source line of each frame, never variable values, never the SDK's own frames (`waypoint_etl`); `traceback` is at most 8192 UTF-8 bytes keeping the **last** frames, dropping whole leading frames and starting with `... (earlier frames omitted)` when cut, and hard-cut from its start if a single frame alone exceeds the cap; a deep recursion error stays within the cap and keeps the innermost frame; chained `__cause__`/`__context__` appear as separate blocks, each with a header line `Type: message`. Confirm it fails
- [X] T005 Implement `packages/waypoint_etl/src/waypoint_etl/errors.py` per research R3 and R5: frames-only text built with `traceback.extract_tb`/`format_list` (never `capture_locals`, never `format_exception`), header line `Type: message` per exception block, the caps above, `str(exc)` guarded (an exception whose `__str__` raises yields message `<unprintable>`). Make T004 pass
- [X] T006 Extend `packages/waypoint_etl/src/waypoint_etl/auditor.py`: remember each attempt's start time in `begin()` (a dict index -> the same `started_at` string written to the marker, removed on finish/fail) and add `fail(name: str, index: int, exc: BaseException) -> None` that writes `failed_key(...)` with `{"v": 1, "pipeline", "env", "run_id", "step", "index", "started_at", "failed_at", "error": build_error(exc)}` and TTL `self.ttl_seconds` ("TTL = the run's `ttl_days`"); it never raises (catch `Exception`, print `Warning: Waypoint failure record failed for {name}: {exc}` like the other writes). Update `StepAuditor.run` to call `fail` in `except Exception` then bare `raise`, and update its docstring (a raise now writes a failure item; the marker is left in place)

### Monitor: read a failure

- [X] T007 [P] Add to `waypoint_monitor/app/domain/models.py`: `ErrorInfo(type: str, message: Optional[str], traceback: str)` and `StepFailure(pipeline, run_id, env, step, index, started_at: datetime, failed_at: datetime, error: ErrorInfo)`, frozen dataclasses with a docstring stating the validation rules of data-model.md ("index: int >= 1", UTC times, `error.type` non-empty and at most 200 characters, `error.message` at most 500 characters or None, `error.traceback` at most 8192 UTF-8 bytes)
- [X] T008 [P] Write `waypoint_monitor/tests/test_parsing.py` additions for `parse_failures(env, pipeline, raw) -> Tuple[List[StepFailure], Dict[str, int]]` (failures, unreadable count by run id): a valid item parses; key/identity mismatch (pipeline, env, run_id, step), `index` not int >= 1 or not equal to the key's `NN`, bad time, missing/empty `error.type`, non-string `traceback`, bad JSON are each skipped and counted for their run; a message longer than 500 characters and a traceback longer than 8192 bytes are shortened (traceback keeps its tail), not rejected; a missing `message` gives `None`; other pipelines' and envs' keys and non-failure keys are ignored (not counted); unknown extra fields are dropped. Confirm it fails
- [X] T009 Implement `_FAILED_KEY` regex (`^waypoint:{_P}:failed:(?P<idx>\d{2,})-(?P<step>.+)$`) and `parse_failures` in `waypoint_monitor/app/domain/parsing.py` following `_validate`/`parse_records`; never raises. Make T008 pass
- [X] T010 Add `list_failures(env, pipeline)` to the `RecordStore` protocol in `waypoint_monitor/app/infrastructure/store.py` ("Return `(key, raw_json)` pairs for every failure item. Read only.") and implement it in `waypoint_monitor/app/infrastructure/redis_store.py` with `self._scan(f"{ROOT}:{pipeline}:{env}:*:failed:*")`; add a test in `waypoint_monitor/tests/test_redis_store.py` that it scans that exact pattern and never writes
- [X] T011 Update `waypoint_monitor/tests/fakes.py`: `FakeStore.list_failures` (items kept in a `.failures` list, helper to add a failure item for a run/step/index with `error` fields) and make the demo seeding in `waypoint_monitor/tests/seed_demo.py` able to write a failure item (used by the manual pass)
- [X] T012 Plumb failures through `waypoint_monitor/app/api/routes.py`: `keys_for` also reads `store.list_failures` (replace the growing tuple with a small `NamedTuple` for the cached window), `build` calls `parse_failures`, adds its per-run counts to `parsed.unreadable_by_run` (so `unreadable` per run and `unreadable_total` include damaged failure items) and passes `failures=` to `build_runs` (new optional parameter, default empty, added in T015). Existing API tests must stay green

**Checkpoint**: A failure item written by the library is stored and read by the monitor; nothing is displayed differently yet.

---

## Phase 3: User Story 1 - See immediately which step failed and why (Priority: P1)

**Goal**: A step that raises an error shows as Failed at once, with its error details, in the API and on every view.

**Independent Test**: Seed or run a pipeline whose second step raises; without waiting for stall/death thresholds the card, run page, graph and step detail show Failed with type, message and stack trace; later steps show Not reached (quickstart steps 2-4).

### Tests (write first, confirm they fail)

- [X] T013 [P] [US1] Write `waypoint_monitor/tests/test_analysis.py` additions for the rules of data-model.md ("Attempt, step and run state"): a failure with the highest attempt index makes the step `failed` (with `started_at`, `failed_at`, `error`) even when its start marker exists and is old (never `running`/`stalled`/`died`); the failure being the highest index of the run makes the run have `failed = {"step", "index", "failed_at"}`, `status == "incomplete"`, `running_step is None`, `died is None`, planned steps after it `missing` (never `waiting`), `first_missing_step` the failed step, `ended_at` equal to `failed_at`; a stopping failure whose run also has a stale heartbeat is not judged Died and `died["recorded"]` machinery is not triggered; a later start marker/finish with a higher index (pipeline continued, or retry) means the step is not the stopping failure; a retry that finishes gives `done` for that step; a retry that is running gives `running`; a retry that fails again shows the latest failure; a handled failure with later steps finishing leaves `failed is None`, the failed planned step in `missing` (run `incomplete`), and no died judgement; a failure for a step outside the flow is shown (`failed`) as an extra step; a run with no flow still shows the failed step in index order
- [X] T014 [P] [US1] Write `waypoint_monitor/tests/test_overview.py` additions: `card_status` is `failed` for a stopping-failure run, ranked `running` > `failed` > `died` > `stale` > `incomplete` > `lost` > `ok`; `needs_attention` true; failed cards lead the attention group, every other card keeps the by-label order; `latest.failed_step`, `latest.failed_at`, `latest.error` (`type`, `message`, no `traceback`) set only for a Failed run, `null` otherwise
- [X] T015 [P] [US1] Write `waypoint_monitor/tests/test_api.py` additions: `/api/runs` returns the `failed` object and `steps[].state == "failed"` with `error` (`message` omitted when not stored); `/api/overview` returns `card_status: "failed"` and the summary fields; a damaged failure item raises `unreadable` and `unreadable_total` and does not hide the rest of the run; no `record_died` call is made for a stopping-failure run whose heartbeat is old
- [X] T016 [P] [US1] Write front-end tests in `waypoint_monitor/static/tests/model.test.mjs`, `graph-model.test.mjs`, `overview.test.mjs`, `run-view.test.mjs`: `mapStep` maps a failed step (`state 'failed'`, `startedAt`, `failedAt`, `error {type, message, traceback}`, empty `inputs`, null `output`); `mapRun` maps `failed`; the card maps `failedStep`/`error`; `cardStatus` gives `Failed` (tone bad, attention); `cardReason` gives `{kind:'failed', step, errorType}`; `cardWhen` gives `{kind:'failed', hours}`; `groupCards` puts Failed first in the attention group; `analyse` exposes `failed`; `heroTitle` returns `A step failed` for a Failed run; `nodeStates` treats `failed` as a stop point (later missing steps are `unreached`)

### Implementation

- [X] T017 [US1] Implement the failure rules in `waypoint_monitor/app/domain/analysis.py` (`build_runs` gets `failures: Sequence[StepFailure] = ()`; `_build_run` gets the run's failures): per step, current failure only if its `index` exceeds the `index` of that step's finish record and is not below the `index` of its start marker (research R7); `live()` returns no marker for a failed step; failed steps are excluded from `unfinished` for the heartbeat rule; `add_failed` emits `{"name","state":"failed","started_at","failed_at","error":{"type", "message"?, "traceback"}}` and appends a planned step to `missing`; stopping failure = current failure whose `index` is greater than every other finish/marker/failure `index` in the run (research R8): then skip `_judge_died` (`died = None`, no verdict recorded) and set `failed`; `ended_at` is the latest of finish times and current failures' `failed_at`; runs that exist only because of a failure item are included (`by_run.setdefault`). Make T013 pass
- [X] T018 [US1] Implement card status in `waypoint_monitor/app/domain/overview.py`: `ATTENTION = ("failed", "died", "stale", "incomplete", "lost")`, `card_status` returns `failed` right after `running`, `_summary` adds `failed_step`, `failed_at`, `error` (`{"type", "message"?}` only), failed cards first within the attention group, otherwise by label (research R11). Make T014 and T015 pass
- [X] T019 [P] [US1] Update `waypoint_monitor/static/js/api.js`: `mapStep` handles `state === 'failed'` (fields as T016, `Date` objects), `mapRun` gains `failed: r.failed ? { step, index, failedAt: new Date(...) } : null`, the overview card `latest` gains `failedStep`, `failedAt`, `error`
- [X] T020 [P] [US1] Update `waypoint_monitor/static/js/model.js`: `CARD_STATUS.failed = { text: 'Failed', tone: 'bad', attn: true }`, `cardReason`/`cardWhen` cases, `groupCards` puts Failed cards first in the attention group, others by label, `analyse` returns `failed`, `heroTitle` returns `A step failed` first (before the died case only when `a.failed`), and a `stoppedAt` text helper for "Stopped at <step>"
- [X] T021 [P] [US1] Update `waypoint_monitor/static/js/graph-model.js` `nodeStates`: `failed` is a stop point like `stalled`/`died` (`st[i] = 'failed'`, later missing steps `unreached`); update the header comment. Make T016 pass together with T019-T020
- [X] T022 [P] [US1] Add a `bug`-style cross-in-octagon icon `I.failed` (distinct from `I.xCircle` used by Incomplete and `I.power` used by Died) and a `Failed` pill to `statusPill` (before the died case) in `waypoint_monitor/static/js/ui.js`; add an escape-safe `copyButtonHTML` helper and a delegated click handler `wireCopy(root)` that copies text from a JS-side map (never by reading HTML back) using `navigator.clipboard.writeText` with a `textarea` fallback, and shows `Copied` for 2 s
- [X] T023 [US1] Update `waypoint_monitor/static/js/views/step.js`: `failed` is its own state (class `step--failed`, node shows an icon, status text `failed`, "Started hh:mm:ss · Failed hh:mm:ss"), inputs chip `input not recorded`, and an **Error** block: type, message when present, the trace in `<pre class="step__trace">` (every value through `esc()`), and the Copy button (copies type, message and trace); `compact` mode shows type and message only
- [X] T024 [P] [US1] Update `waypoint_monitor/static/js/views/graph.js`: `failed` entries in the state label map ("Failed"), the note ("failed - the step raised an error, the run stopped here"), the icon map (`I.failed`), node count text `failed hh:mm:ss`, and the run summary line `failed at <step>` (like the died one), plus a `gpill--failed` pill
- [X] T025 [P] [US1] Update `waypoint_monitor/static/js/views/home.js`: status icon for `failed`, reason line `Failed at <code>step</code>: <error type>` with the message shortened to one line (both escaped), time line `failed N ago`
- [X] T026 [P] [US1] Update `waypoint_monitor/static/js/views/run.js`: hero for a Failed run (`A step failed`, `Stopped at <step>`, status pill), step markers for `failed`, `Not reached` wording for later missing steps of a Failed run; call `wireCopy`
- [X] T027 [US1] Add styles in `waypoint_monitor/static/styles.css` after the Died block: `.gpill--failed`, `.step--failed .step__node/.step__card`, `.gnode--failed`, `.flow__cell--failed` (error colour + solid border + the icon so colour is not the only cue), `.step__error`, `.step__trace` (monospace, `max-height: 16rem; overflow: auto; white-space: pre`, no horizontal page scroll at phone width), copy button; support dark mode like the existing tokens
- [X] T028 [US1] Run all suites (library, monitor Python, `node --test`), `mypy`, `ruff`, `black --check`; fix failures; then do quickstart manual steps 2-4 and 12 against a seeded Redis and note results in `specs/011-step-failure-errors/quickstart.md`

**Checkpoint**: US1 works end to end (SC-001, SC-002, SC-007).

---

## Phase 4: User Story 2 - The pipeline behaves exactly as before (Priority: P1)

**Goal**: Recording a failure never changes a step's outcome.

**Independent Test**: Failing step with Redis up and down: identical exception both times; succeeding step returns its normal value (SC-003).

- [X] T029 [P] [US2] Write `packages/waypoint_etl/tests/test_failure.py` (confirm failing first): with a recording store, a plain function decorated with `audited_step` that raises `ValueError("x")` writes exactly one `failed` item for that index and the caller catches the **same object** (`assertIs`), same `args`, same `__cause__`/`__context__`, same traceback frames except the added wrapper frame; the same for an `async def` step run with `asyncio.run`; `StepAuditor.run` the same; a step that returns writes no failure item and the same finish record as 0.2.x; a second attempt (a retry) of the same step gets index + 1 and its own failure key; a step with no active auditor (no `init`) behaves like the bare function
- [X] T030 [US2] Update `packages/waypoint_etl/src/waypoint_etl/decorator.py`: in both wrappers `try: result = fn(...) / await async_fn(...)`, `except Exception: auditor.fail(name, index, exc)` (the exception bound once), then a bare `raise`; keep the success path unchanged; update the module and `audited_step` docstrings. Make T029 pass
- [X] T031 [P] [US2] Add to `packages/waypoint_etl/tests/test_failure.py` the safety cases and make them pass: a store whose `write` raises `ConnectionError` for the failure write (and for all writes) leaves the original exception unchanged and prints one warning; an exception whose `__str__` raises is still recorded (message `<unprintable>`) and re-raised; a `KeyboardInterrupt`, `SystemExit` and `asyncio.CancelledError` from a step are re-raised and no failure item is written (research R1); an exception in `build_error` itself never replaces the step's exception; `heartbeat` and flow writes unaffected (existing tests green)
- [X] T032 [US2] Update `packages/waypoint_etl/tests/test_unconfigured.py` and `test_second_pipeline.py` if they assume "if a step raises, no record is written" (change to the new behaviour); update the `StepAuditor.run` docstring accordingly

**Checkpoint**: US1 and US2 together are the MVP (SC-003).

---

## Phase 5: User Story 3 - Keep sensitive data out of error reports (Priority: P2)

**Goal**: The author can omit or clean messages; traces never carry values.

**Independent Test**: Message capture off with a marker string in the message: the marker is absent from Redis and from the API output; with `redact` it is replaced (SC-004).

- [X] T033 [P] [US3] Extend `packages/waypoint_etl/tests/test_errors.py` (confirm failing): `capture_message=False` omits the `message` field entirely and the traceback's header lines contain the type only (the message text appears nowhere in the payload, including chained exceptions); `redact` is applied to the message and to chained header lines before the 500-character cut, so a cleaner that expands text stays within 500; a `redact` that raises or returns a non-string drops the message (field absent), never stores the raw text; no payload field ever contains a local variable value (a local `secret = "S3CR3T"` used in the failing frame does not appear)
- [X] T034 [US3] Implement the `capture_message` and `redact` behaviour in `packages/waypoint_etl/src/waypoint_etl/errors.py` (research R4); store both settings on `StepAuditor` (`capture_error_message: bool = True`, `redact: Optional[Callable[[str], str]] = None` constructor arguments) and pass them in `fail()`; make T033 pass
- [X] T035 [US3] Add `capture_error_message: bool = True` and `redact: Optional[Callable[[str], str]] = None` keyword-only parameters to `init` in `packages/waypoint_etl/src/waypoint_etl/registry.py` and pass them to the auditor; document them in the docstring; add cases to `packages/waypoint_etl/tests/test_init.py` (defaults, both set, invalid `redact` value such as a non-callable prints a warning and behaves as `None`)
- [X] T036 [P] [US3] Add a monitor test in `waypoint_monitor/tests/test_analysis.py` and `static/tests/model.test.mjs` that a failure without `message` produces a step with no `message` key and a UI that shows the type and trace and no "message" label or `undefined`; make the code handle it (`step.js`, `home.js`)

---

## Phase 6: User Story 4 - Failed runs stand out in History (Priority: P2)

**Goal**: Failed runs are labelled in History and can be filtered.

**Independent Test**: A pipeline with completed, failed and died runs: failed rows show `Failed`; "Failed only" lists exactly them.

- [X] T037 [P] [US4] Write tests in `waypoint_monitor/static/tests/state.test.mjs` for a pure `filterRuns(runs, mode)` in `static/js/model.js` (`'all'` returns all; `'failed'` returns only runs whose `failed` is not null; empty result stays empty) and for the status pill text of a Failed run; confirm they fail
- [X] T038 [US4] Implement `filterRuns` in `waypoint_monitor/static/js/model.js`; in `waypoint_monitor/static/js/views/history.js` add the "All runs / Failed only" radio group beside the environment filter (research R10), apply it client side to the list, keep the choice in a module variable (not in the address: the filter is a view preference), show an `emptyHTML` message "No failed runs" when empty
- [X] T039 [US4] Confirm History rows use the `Failed` pill from `statusPill` (T022) and that the trend/deltas ignore failed steps' missing counts without error (`series`, `metric` return null for a failed step); add a test for that in `waypoint_monitor/static/tests/model.test.mjs`

---

## Phase 7: User Story 5 - Older pipelines keep working (Priority: P1)

**Goal**: Runs without failure items look exactly as before; damaged items are tolerated.

**Independent Test**: Existing fixtures give identical API output before and after.

- [X] T040 [P] [US5] Add a regression test in `waypoint_monitor/tests/test_analysis.py`: for each existing run scenario (running, stalled, died, complete, incomplete, lost data, no flow, unplanned step) the `build_runs` output with `failures=()` equals the output of the pre-feature code (compare against stored literal expectations from the current tests; run and confirm no existing assertion needed change) and contains `"failed": None`; the only new key on old runs is `failed`
- [X] T041 [P] [US5] Add a test in `waypoint_monitor/tests/test_api.py` with a `FakeStore` that has no failure items: `/api/runs` and `/api/overview` succeed and `failed`/`failed_step` are null; a failure item with garbage JSON is counted in `unreadable_total` and the run still renders (FR-016)
- [X] T042 [US5] Confirm by test (`waypoint_etl` side, `packages/waypoint_etl/tests/test_failure.py`) that records written by 0.3.0 for successful steps are byte-identical to 0.2.x finish records (same keys and fields), so a pre-0.3 monitor needs no change; the monitor never calls any write for failure data (assert `record_died` is the only write in `fakes.py`)

---

## Phase 8: Polish & cross-cutting

- [X] T043 [P] Update `packages/waypoint_etl/README.md`: the failure item (fields, caps), `capture_error_message`, `redact`, "if a step raises, a failure item is written and the exception is re-raised unchanged" (replace the 0.2.0 sentence "its start marker stays and no finish record is written"), BaseException not recorded, a note that Failed needs 0.3.0 (the install pin stays `v0.2.0` until the `waypoint-etl-v0.3.0` tag exists); set `version = "0.3.0"` in `packages/waypoint_etl/pyproject.toml` and `__version__ = "0.3.0"` in `packages/waypoint_etl/src/waypoint_etl/__init__.py`
- [X] T044 [P] Update `waypoint_monitor/README.md`: the Failed state and its priority, Failed vs Died, the `failed` fields in the API, "no new Redis permission is needed", how handled errors are shown; update the root `README.md` with one line about Failed
- [X] T045 [P] Update `.claude/skills/adopting-waypoint-etl/SKILL.md` if it describes behaviour when a step raises or the `init` arguments, so adopters learn about `capture_error_message` and `redact`
- [X] T046 Run the full automated set from `specs/011-step-failure-errors/quickstart.md` (library, monitor Python, `node --test`, `mypy`, `ruff`, `black --check` in both packages) and record the counts under "Results"
- [X] T047 Run the quickstart manual pass steps 1-12 (real Redis, Playwright at desktop 1440 and phone 390 widths), including the `<img onerror>` message check, the capture-off grep and the old-library run; record outcomes in `specs/011-step-failure-errors/quickstart.md`
- [X] T048 Re-check the constitution table in `specs/011-step-failure-errors/plan.md` against the final code (typing, tests, PII, resilience) and tick the checklist `specs/011-step-failure-errors/checklists/requirements.md` notes if any decision changed

---

## Dependencies & Execution Order

- Phase 1 first. Phase 2 blocks everything: library tasks (T002-T006) and monitor tasks (T007-T012) are independent of each other and can proceed in parallel.
- US1 (Phase 3) needs Phase 2 monitor parts (T007-T012). Its library input needs T006 only through the manual/end-to-end check (T028); unit tests use `fakes.py`.
- US2 (Phase 4) needs T003-T006 and delivers the decorator wiring; with US1 it is the MVP. T028's end-to-end pass needs T030.
- US3 (Phase 5) needs T005, T006 and T030. US4 (Phase 6) needs T020 and T022. US5 (Phase 7) needs Phase 2 and T017.
- Polish last.

Story order: US1 and US2 (P1) together → US5 (P1, tests only) → US3 and US4 (P2, independent of each other).

### Parallel examples

```text
Phase 2:  T002 + T004 (library tests) | T007 + T008 (monitor model + parsing tests)
US1:      T013 + T014 + T015 + T016 (tests) ; then T019 + T020 + T021 + T022 (front-end modules)
          then T024 + T025 + T026 (views, different files)
US3/US4:  Phase 5 (library) and Phase 6 (front end) at the same time
Polish:   T043 + T044 + T045
```

## Implementation Strategy

1. **MVP**: Phases 1, 2, 3 and 4 (US1 + US2): failures are recorded safely and shown. Stop here and demo with quickstart steps 2-4 and 8.
2. Add US5 (compatibility proof) before releasing the library 0.3.0.
3. Add US3 (privacy controls) before enabling in a pipeline that handles sensitive data; add US4 (History) any time after US1.
4. Release order: monitor first (works with any library), then library 0.3.0 pipeline by pipeline.
