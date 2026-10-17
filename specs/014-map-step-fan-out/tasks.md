---

description: "Task list for Map Step (Loop Inside a Pipeline)"
---

# Tasks: Map Step (Loop Inside a Pipeline)

**Input**: Design documents from `/specs/014-map-step-fan-out/`

**Prerequisites**: plan.md, spec.md, research.md (R1-R13), data-model.md, contracts/{redis-keys,library-api,api,ui}.md, quickstart.md

**Tests**: Included. The constitution (principle IV) requires tests for changed behaviour, and spec FR-028 / SC-008 need regression tests for unchanged old runs.

**Organization**: Grouped by user story. Paths are relative to the repository root. `LIB` = `packages/waypoint_etl`, `MON` = `waypoint_monitor`.

**Conventions**: Python is fully typed (`mypy --strict`), `ruff` + `black` line length 100; the library supports Python 3.10+ and uses only the standard library. Test runners: `python -m unittest discover tests` (in `LIB` and in `MON`) and `node --test static/tests/*.test.mjs` (in `MON`). Test names and fixtures follow the neighbouring files (`test_metrics.py`, `test_metric_writer.py`, `fakes.py`).

**UI note**: The user will provide a visual design (made with Claude Design) before the UI tasks are built. UI tasks (marked `UI`) implement that design; until it arrives, `contracts/ui.md` is the behavioural contract. Model, API and library tasks do not wait for it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1-US6 (from spec.md)

Story map: US1 live progress and the exact failing item · US2 declare a loop and record per-item steps · US3 find slow and failing items (filter, search, sort, page, percentiles) · US4 inspect one item (steps, counts, errors, events, metrics) · US5 huge loops stay bounded · US6 old pipelines and libraries unchanged.

Build order: US2 produces the data and US1 shows it; both are independently testable (US1 against seeded records, US2 against a fake store) and together are the MVP. US6 is a regression gate that runs after both.

## Phase 1: Setup

- [X] T001 Run the baseline before changing anything: in `packages/waypoint_etl` and in `waypoint_monitor` run `python -m unittest discover tests`, `mypy`, `ruff check .`, `black --check .`; in `waypoint_monitor` run `node --test static/tests/*.test.mjs`. Record the passing counts in the PR description so later regressions are visible.
- [X] T002 [P] Verify research R3 by test: in `waypoint_monitor/tests/test_parsing.py` add a case asserting that none of the existing key patterns (`_KEY`, `_MARKER_KEY`, `_FLOW_KEY`, `_FAILED_KEY`, `_EVENTS_KEY`, `_METRICS_KEY`, `_ALIVE_KEY`, `_DIED_KEY`) match `waypoint:callrail:prod:20261017T020301Z:map:accounts` or `waypoint:callrail:prod:20261017T020301Z:item:accounts:acct-7`, and that `pipeline_of_key("prod", <either key>)` still returns `callrail`. Also add the same two keys to the fake store's glob matching test so `list_records`, `list_markers`, `list_failures` and `list_metrics` return neither.

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: Both sides know the new keys, the declaration and the data shapes; the monitor can read map aggregates and item records from the store. No behaviour change yet.

### Library

- [X] T003 [P] Add to `packages/waypoint_etl/src/waypoint_etl/keys.py`: `map_key(pipeline, env, run_id, map_name)` returning `waypoint:{pipeline}:{env}:{run_id}:map:{map_name}` and `item_key(pipeline, env, run_id, map_name, key)` returning `waypoint:{pipeline}:{env}:{run_id}:item:{map_name}:{key}`; and constants `MAP_VERSION = 1`, `MAP_DETAIL_LIMIT = 1000`, `MAP_EXTRA_FAILED_LIMIT = 1000`, `MAP_SLOWEST_KEPT = 50`, `MAX_ITEM_KEY = 64`, `MAX_INNER_STEPS = 20`, `MAP_FLUSH_SECONDS = 1.0`, `ITEM_TRACE_BYTES = 2048`, `COMPACT_MESSAGE = 200`, `MAP_FAILED_LISTED = 20`, `MAP_SLOWEST_LISTED = 5`, `HIST_RATIO = 1.1`, `EVICT_TTL_SECONDS = 1`. Extend `packages/waypoint_etl/tests/test_keys.py` with the two key shapes.
- [X] T004 Add `MapStepSpec` to `packages/waypoint_etl/src/waypoint_etl/spec.py` (frozen dataclass: `name`, `steps: Tuple[StepSpec, ...]`, `over: Optional[str] = None`, `max_concurrency: Optional[int] = None`, `label`, `group`, `col`, `row`, `inputs: Tuple[Tuple[str, str], ...] = ()`); change `PipelineSpec.steps` to `Tuple[Union[StepSpec, MapStepSpec], ...]`; extend `validate_spec` per data-model.md "Declaration": map name matches `^[a-z0-9_]{1,64}$` and is unique across all steps and inner steps; `steps` has 1 to `MAX_INNER_STEPS` (20) entries; an inner step may not be a `MapStepSpec`; an inner step's inputs may name only an earlier inner step or an earlier top-level step; `over`, when given, names an earlier top-level step; `max_concurrency` is an int >= 1 (not bool) when given; inner steps follow all `StepSpec` rules including metric declarations. Each rule raises `ValueError` naming the map and the problem. Write `packages/waypoint_etl/tests/test_spec_map.py` (new) first covering every rule above (duplicate name against a top-level step and against another map's inner step, empty `steps`, 21 inner steps, nested map, input from a later inner step, `max_concurrency=0`, `max_concurrency=True`, `over` naming a later step, and one fully valid spec). Depends on T003.
- [X] T005 In `packages/waypoint_etl/src/waypoint_etl/auditor.py` add `step_spec(name) -> Optional[StepSpec]` that finds a top-level or inner step by name, and make `_flow_value` write a map step as `{"name", "kind": "map", "inputs", "over"?, "max_concurrency"?, "label"?, "group"?, "col"?, "row"?, "steps": [inner step entries in the existing step-entry shape, including declared metrics]}` with optional fields omitted when unset (contracts/redis-keys.md "Extended: flow record"; `FLOW_VERSION` stays 1). Change `_input_values` in `packages/waypoint_etl/src/waypoint_etl/decorator.py` to use `auditor.step_spec(step)` so inner steps get input counts. The `begin` warning "not in pipeline spec" must also accept inner step names. Add cases to `packages/waypoint_etl/tests/test_auditor.py` (flow record for a map spec; a pipeline with no map step produces a byte-identical flow record to 0.5.0) and `packages/waypoint_etl/tests/test_decorator.py` (inner step inputs). Depends on T004.

### Monitor

- [X] T006 [P] Add to `waypoint_monitor/app/domain/models.py` (frozen dataclasses, fully typed): `MapDecl` (`over: Optional[str]`, `max_concurrency: Optional[int]`, `steps: Tuple[FlowStep, ...]`); `FlowStep.map: Optional[MapDecl] = None`; `MapCounts` (`started`, `running`, `done`, `failed`, all int >= 0); `MapInner` (`name`, `running`, `done`, `failed`, `inputs_total`, `output_total`); `MapAggregate` (`pipeline`, `env`, `run_id`, `map`, `index` int >= 1, `started_at`, `ended_at: Optional`, `updated_at: Optional`, `counts`, `in_total`, `out_total`, `lost_items`, `inner: Tuple[MapInner, ...]`, `count`, `sum_ms`, `hist: Dict[int, int]`, `slowest: Tuple[Tuple[str, int], ...]` at most 5, `failed_items: Tuple[Tuple[str, str, str], ...]` at most 20 as `(key, step, error_type)`, `kept`, `failed_without_record`, `slow_kept`); `ItemStepResult` (`step`, `attempt` int >= 1, `state` in `running|done|failed`, `inputs: Dict[str, int]`, `output: Optional[int]`, `started_at`, `duration_ms: Optional[int]`, `error: Optional[ErrorInfo]`); `ItemRecord` (`pipeline`, `env`, `run_id`, `map`, `key`, `index` int >= 1, `state` in `running|done|failed`, `started_at`, `finished_at: Optional`, `duration_ms: Optional[int]`, `steps: Tuple[ItemStepResult, ...]` at most 20, `metrics: Dict[str, Dict[str, MetricNumber]]`, `error: Optional[ErrorInfo]`, `compact: bool`). Document each field's constraint verbatim in the docstring as the neighbouring models do.
- [X] T007 [P] Write failing tests in `waypoint_monitor/tests/test_flow.py` for map parsing: a step with `kind: "map"` becomes a `FlowStep` with `map` set and its inner steps are not top-level steps; inner steps parse like ordinary steps (labels, metric declarations, inputs); `max_concurrency` below 1, a bool or a non-int is dropped with a problem and the map step stays; a duplicate of a top-level step name, a nested `kind: "map"`, more than 20 inner steps and an input from an unknown inner step are each dropped or flagged with a problem (never raise); a flow with no map step parses exactly as before.
- [X] T008 Implement map parsing in `waypoint_monitor/app/domain/flow.py` (`MAX_INNER_STEPS = 20`, reuse `_STEP_NAME`, `_label`, `_metric_decls`): read `kind`, `over` (must be a top-level step name, else dropped with a problem), `max_concurrency`, `steps`; keep `_drop_cycles` carrying `map` through its rebuilt `FlowStep` objects. Depends on T006 and T007.
- [X] T009 [P] Write failing tests in `waypoint_monitor/tests/test_maps_parsing.py` (new) for `parse_maps(env, pipeline, raw)` returning `(List[MapAggregate], Dict[str, int])` (aggregates, unreadable count per run id) and `parse_items(env, pipeline, run_id, map_name, raw)` returning `(List[ItemRecord], int)`: a valid aggregate and a valid full and compact item parse; `v` other than 1, `counts.started != running + done + failed`, a negative count, a bool count, a `hist` key that is not an int, more than 5 `slowest`, more than 20 `failed_items`, a run id, env or pipeline that differs from the key, a map name that differs from the key, an item key outside `^[A-Za-z0-9_.-]{1,64}$`, a state other than `running|done|failed`, more than 20 `steps`, and invalid JSON each make the record unreadable (counted for its run, others kept); wrong-typed optional fields (`ended_at`, `duration_ms`, `updated_at`) are treated as absent; a traceback over 2048 bytes is cut keeping the last frames; keys of other pipelines or environments and non-map keys are ignored.
- [X] T010 Implement `parse_maps` and `parse_items` in `waypoint_monitor/app/domain/parsing.py` with `_MAP_KEY = rf"^{ROOT}:{_P}:map:(?P<map>[a-z0-9_]{{1,64}})$"` and `_ITEM_KEY = rf"^{ROOT}:{_P}:item:(?P<map>[a-z0-9_]{{1,64}}):(?P<key>[A-Za-z0-9_.-]{{1,64}})$"`, mirroring `parse_metrics`; never raise. Depends on T006 and T009.
- [X] T011 [P] Add `list_maps(env, pipeline) -> List[Tuple[str, str]]` ("Return `(key, raw_json)` pairs for every map aggregate. Read only.") and `list_items(env, pipeline, run_id, map_name) -> List[Tuple[str, str]]` ("Return `(key, raw_json)` pairs for the item records of one map step of one run. Read only.") to the `RecordStore` protocol in `waypoint_monitor/app/infrastructure/store.py`, and implement both in `waypoint_monitor/app/infrastructure/redis_store.py` with the existing `_scan`: patterns `waypoint:{pipeline}:{env}:*:map:*` and `waypoint:{pipeline}:{env}:{run_id}:item:{map_name}:*`. Extend `waypoint_monitor/tests/test_redis_store.py` with both calls (including `StoreUnavailable` on `RedisError`).
- [X] T012 [P] Teach `waypoint_monitor/tests/fakes.py` `FakeStore`/`FakeRedis` the two new calls and let seed helpers add aggregates and item records (`add_map(...)`, `add_item(...)`), counting calls so tests can assert item keys are never read by `/api/runs`.
- [X] T013 Add `maps: Raw` to the `Window` named tuple in `waypoint_monitor/app/api/routes.py`, read it in `keys_for` with `store.list_maps(env, pipeline)`, and keep the cache-drop-on-unavailable behaviour. Item records are never part of the window. In `build`, parse maps with `parse_maps`, add their unreadable counts into the per-run unreadable map like metrics do, and pass the aggregates to `build_runs` (parameter added in T018). Depends on T010, T011 and T012.

**Checkpoint**: map aggregates and item records can be written to a fake store and read back through `parse_maps` / `parse_items`; map steps parse in flows; all existing tests pass.

---

## Phase 3: User Story 1 - Live progress and the exact failing item of a loop (Priority: P1) 🎯 MVP (with US2)

**Goal**: With map data in the store, the operator sees the map step as one node with live progress, a correct state, and the failing item with its inner step and error, without logs.

**Independent Test**: Seed a run with a map step of 10 items (concurrency 5): while running the progress is right; after the block ends with one item failed in its second inner step, the node is failed, the item is listed with failed step and error, and the other nine show done.

### Tests for User Story 1

- [X] T014 [P] [US1] Write failing tests in `waypoint_monitor/tests/test_maps_domain.py` (new) for `waypoint_monitor/app/domain/maps.py`: `map_state(aggregate, run_state)` per research R6 (block open and no failures: running; block open with failures: running; block ended with 0 failed: done, including 0 started; block ended with failed >= 1: failed; run stalled or died: that state); `summarize(aggregate, decl, settings)` produces the `map` object of contracts/api.md (counts, in/out totals, `lost_items`, `concurrency_limit`, `over`, `loop_seconds` from the step timing, `slowest`, `failed_items`, `inner` in declared order with an entry per declared inner step even when no item reached it, `detail.partial = started > kept`, `unreadable`); the synthetic failure for `failed >= 1` has type `ItemsFailed`, message `"{failed} of {started} items failed"` and an empty traceback; items stored as `running` in a stalled or died map are reported with that state (R12).
- [X] T015 [P] [US1] Write failing tests in `waypoint_monitor/tests/test_analysis.py` for the overlay in `build_runs`: a map step with an aggregate carries `map`; a map whose block ended with failed items and a normal step record is `failed` with the synthetic error, the run is `incomplete` and `loss_steps` unchanged; the same map is not `failed` while its start marker is still open; a real failure item for the same attempt replaces the synthetic one; a later step still shows its own state; a flow with a map step and no aggregate (older library) renders as an ordinary step with no `map` and no error; `flow.steps[i].map` carries `over`, `max_concurrency` and the inner steps; the History and overview inputs (`failed`, `missing_count`, `status`) treat a map failed through items exactly like a failed step.
- [X] T016 [P] [US1] Write failing tests in `waypoint_monitor/tests/test_api.py` for `/api/runs` (a step's `map` object shape and values, unreadable aggregate counted in the run, item keys never read: the fake store's call log has no `list_items`) and for the first version of `GET /api/runs/{pipeline}/{env}/{run_id}/maps/{map}/items` (default sort by arrival number, default `limit` 50, response shape of contracts/api.md including `total`, `with_record`, `counts`, `matched`, `has_more`, `next`; 400 for a bad env, pipeline, run id or map name; unknown run or map gives 200 with `total: 0`; `StoreUnavailable` gives 503).
- [X] T017 [P] [US1] Write failing front-end tests in `waypoint_monitor/static/tests/map-model.test.mjs` (new) for helpers in `static/js/model.js`: `mapProgress(map)` returns `6 done · 4 running · 0 failed` and never contains `of`; `mapPillText(map)` for a failed item count; state text for 0 started and 0 items; `mapPartialNotice(map)`; `itemFlowStrip(map)` text per inner step (`fetch · 10 done`, `transform · 7 done · 1 running · 1 failed`); all text built from keys and names is returned raw (escaping happens at render).

### Implementation for User Story 1

- [X] T018 [US1] Implement `waypoint_monitor/app/domain/maps.py` (new, pure functions, fully typed): `map_state`, `summarize`, `synthetic_failure`, `percentile_ms(hist, count, q)` (nearest rank over buckets, geometric midpoint `1.1 ** (bucket + 0.5)`; None when `count < min_items`), and `items_with_run_state(items, state)`. Percentiles are only reported when `count >= duration_min_runs`; mark `approx` true. Depends on T006 and T014.
- [X] T019 [US1] In `waypoint_monitor/app/domain/analysis.py` add a `maps: Sequence[MapAggregate] = ()` parameter to `build_runs` and `_build_run` (keep latest aggregate per run and map name by `index`); in `_build_run` add `map` to the step entry when an aggregate exists; add the synthetic failure to `current` (see `_current_failures`) when the aggregate has `failed >= 1`, its block ended and no real failure item exists for the same attempt; make `_flow_json` write `map: {over, max_concurrency, steps}` for a map step. A map step whose block is still open stays running. Depends on T015, T018.
- [X] T020 [US1] Add the first version of `GET /api/runs/{pipeline}/{env}/{run_id}/maps/{map}/items` in `waypoint_monitor/app/api/routes.py`: validate env, `PIPELINE_NAME`, `_RUN_ID` and the map name regex; read `store.list_items`, parse with `parse_items`, build the response of contracts/api.md ordered by arrival number then key, `limit` 1 to 200 (default 50), items of a stalled or died map reported with that state, an unknown run or map answered with an empty result; cache items per `(env, pipeline, run_id, map)` for `settings.cache_seconds` (separate from `Window`). Filters, sorting and the cursor come in US3. Depends on T013, T016, T018.
- [X] T021 [P] [US1] `UI` Map data in the front end: in `waypoint_monitor/static/js/api.js` map `step.map` (camelCase like the other fields) and `flow.steps[i].map` into the run's `defs`, and add `fetchItems(pipeline, env, runId, map, params)`; in `static/js/model.js` implement `mapProgress`, `mapPillText`, `mapPartialNotice`, `itemFlowStrip` and treat a map step's state through the existing `stepState`. Make `static/tests/map-model.test.mjs` (T017) pass.
- [X] T022 [US1] `UI` Draw the map node in `waypoint_monitor/static/js/views/graph.js` and `static/js/graph-model.js` per the design (or contracts/ui.md "Graph and step list"): state pill with label and icon, progress line, failed-items pill, data-loss pill text `items lost data`, `aria-label` text `Accounts, map step. State: running. 6 done, 4 running, 0 failed. Concurrency limit 5.`, `aria-expanded` reflecting the panel, selection kept across refresh like steps. A map step with no aggregate is drawn as an ordinary step. Add the styles to `static/styles.css`. Depends on T021.
- [X] T023 [US1] `UI` Create `waypoint_monitor/static/js/views/map.js` with the map panel: summary line (state, loop duration, in and out sums, concurrency limit; percentiles and slowest arrive in US3), item flow strip with aggregate state per inner step, the `failed_items` list from the aggregate shown first when the map failed, and a plain item list fed by `fetchItems` (key, state pill, duration, failed inner step and error type, in → out) with "No items started." and "No items match." empty states. Mount it from the "selected step" area in `views/graph.js` and from the step's item in `views/run.js` / `views/step.js`. Plain text only (use `esc`). Depends on T021, T022.
- [X] T024 [US1] Make the previous tests pass and add the missing cases found while wiring (empty `failed_items`, a map with no inner steps in the flow, a map whose aggregate names an inner step the flow does not declare, shown as unplanned). Run the monitor test suites and `node --test`.

**Checkpoint**: seeded map runs show the correct progress, state and failing item in the API and the browser; older runs unchanged.

---

## Phase 4: User Story 2 - Declare a loop and record per-item steps (Priority: P1) 🎯 MVP (with US1)

**Goal**: An author adds a declaration and two `with` lines to an existing loop, whether it is a plain loop, a thread pool or asyncio, and every item and inner step reaches the store with the right key.

**Independent Test**: Convert a plain `for` loop and a thread-pool loop; against a fake store, every item and inner step record has the correct key and no records mix across items; invalid keys, duplicate keys, missing scopes and a down store never raise.

### Tests for User Story 2

- [X] T025 [P] [US2] Write failing tests in `packages/waypoint_etl/tests/test_maps.py` (new) for `packages/waypoint_etl/src/waypoint_etl/maps.py` pure parts: `sanitise_key(raw, arrival)` (allowed set `^[A-Za-z0-9_.-]{1,64}$`; any other character becomes `_`; longer keys cut to `MAX_ITEM_KEY` (64); empty or non-string becomes `item_{arrival}`; the returned flag says whether the raw key had to change); `bucket(ms)` (`floor(ln(ms)/ln(1.1))` for `ms >= 1`, bucket 0 below) and `bucket_value(b)`; `MapTracker` counters: start, finish, fail transitions keep `started = running + done + failed`; an item with an inner step failed is `failed` unless a later attempt of the same inner step succeeds; an exception through `item()` with no failed inner step marks it failed with an item-level error; item in is the first inner step's input sum, out is the last inner step's output; loss is `output == 0` with some input > 0 on any inner step and bumps `lost_items` once per item; `inner` counts follow each inner step across items; per-item metrics merge with the spec 013 rules (set, add, max, 20 names, same validation) and appear in the item's snapshot; duplicate key: first record kept, second pass returns a discard scope that records nothing; histogram `count`, `sum_ms`, `slowest` (top 5, exact) and `failed_items` (first 20 in arrival order) update on finish.
- [X] T026 [P] [US2] Write failing tests in `packages/waypoint_etl/tests/test_map_scopes.py` (new) for `map_step()` and `item()`: sequential loop; `ThreadPoolExecutor(5)` with `item()` inside the worker over 50 items repeated 20 times (every record's inner steps match its key, no mixing); `asyncio.gather` of 20 coroutines each in `with item(id)` and `async with item(id)`; `item()` with `map=` explicit, with the enclosing `map_step`, and with only the one open block (worker thread); no open block, unknown map name and a name that is not a map step each do nothing and warn once; inside an ignored (duplicate) item the decorated inner steps run but write no step, marker or failure records at run level; an exception through `item()` and through `map_step()` propagates unchanged; `map_step` entering writes the ordinary start marker, leaving normally writes the ordinary step record with `output` = items started and `inputs` from `over` when given, leaving with an exception writes the failure item; without `init`, after a failed `init` and with a store whose `write` raises, every call is a no-op and nothing raises.
- [X] T027 [P] [US2] Write failing tests in `packages/waypoint_etl/tests/test_map_writer.py` (new) for `MapWriter`: 1,000 item changes inside one interval become one `write_many` call; the aggregate is written with every pass that changed anything; `flush` and `stop` skip the wait and deliver within 2 s; a failing store logs at most once a minute and the changed records are rewritten in full on their next change; a store without `write_many` is served by a `write` loop; leaving the map block flushes before the step record is written; the writer thread is a daemon and `stop` is safe to call twice.
- [X] T028 [P] [US2] Extend `packages/waypoint_etl/tests/test_events.py` and `packages/waypoint_etl/tests/test_metrics.py`: inside `item()` an event carries `item` (the sanitised key) and `step` (the inner step's name); outside `item()` events are unchanged byte for byte; `waypoint_etl.metric` inside an inner step merges into the item's metrics for that inner step and creates no `...:metrics:...` record.

### Implementation for User Story 2

- [X] T029 [US2] Create `packages/waypoint_etl/src/waypoint_etl/maps.py`: `sanitise_key`, `bucket`, `bucket_value`, `ItemState` (key, arrival, state, times, inner results, per-item `MetricState` from `waypoint_etl/metrics.py`, item error, compact flag), `MapTracker` (one per map block, one lock; `start_item`, `begin_inner`, `finish_inner`, `fail_inner`, `record_metric`, `end_item`, `snapshot_dirty()`, `aggregate()`; counts, `inner` counts, in/out sums, `lost_items`, histogram, `slowest`, `failed_items`, duplicate detection with a bounded set of seen keys, one warning per distinct raw key bounded to 100). Add `MetricState.snapshot()` to `packages/waypoint_etl/src/waypoint_etl/metrics.py` returning a copy of `{attempt: values}` without clearing dirty flags. Retention limits come in US5: here every item gets a record. Depends on T003, T025.
- [X] T030 [US2] Add `MapWriter` to `packages/waypoint_etl/src/waypoint_etl/maps.py`, same loop shape as `MetricWriter` (wake at most once per `MAP_FLUSH_SECONDS`, `flush`, `stop`, once-a-minute warnings); it writes the dirty item records and the aggregate (`map_key`, `item_key`, `MAP_VERSION`, TTL = the run's `ttl_seconds`, record shapes of contracts/redis-keys.md) through one `write_many` when the store has it, else `write` in a loop. Add an optional `write_many(items, ttl_seconds)` to `RedisStepAuditStore` and `NoopStepAuditStore` in `packages/waypoint_etl/src/waypoint_etl/stores.py` using a non-transactional pipeline of `SETEX`. Depends on T029, T027.
- [X] T031 [US2] Create `packages/waypoint_etl/src/waypoint_etl/scopes.py`: `current_item` and `current_map` context variables; `MapScope` (`__enter__`, `__exit__`, `__aenter__`, `__aexit__`) and `ItemScope` (same four) as in contracts/library-api.md "Recording"; `ItemScope` resolves its map as `map=`, then `current_map`, then the auditor's one open map block, else does nothing with one warning; an item that is a duplicate sets a discard scope in `current_item` so inner steps run without any run-level recording; neither scope ever suppresses an exception or raises. Depends on T029, T026.
- [X] T032 [US2] Wire the auditor in `packages/waypoint_etl/src/waypoint_etl/auditor.py`: `open_map(name)` calls `begin(name)` (ordinary start marker, index `NN`), creates the `MapTracker` and starts the `MapWriter`; `close_map(name, index, exc)` ends the block, flushes the writer (at most 2 s), then calls `finish(...)` with `output` = items started and `inputs` from `over` (count of the source step's output when known) or `fail(...)` for an exception; `begin`, `finish`, `fail` check `current_item` first and route to the tracker (the returned inner index is the per-item attempt counter, passed back by the decorator unchanged); `record_metric` and `send_event` route to the item when set (events get the `item` field via `build_event` in `packages/waypoint_etl/src/waypoint_etl/events.py`, optional and omitted otherwise); `stop` and `flush_events` also stop and flush every open map writer. Unknown inner step names are recorded on the item after one warning. Depends on T030, T031, T028.
- [X] T033 [US2] Add `map_step(name)` and `item(key, *, map=None)` entry points to `packages/waypoint_etl/src/waypoint_etl/registry.py` (no-op returning an inert scope before `init`, after a failed `init`, and for a name that is not a declared map step), export `MapStepSpec`, `map_step`, `item` in `packages/waypoint_etl/src/waypoint_etl/__init__.py`, update the module docstring example, and set `__version__ = "0.6.0"` there and in `packages/waypoint_etl/pyproject.toml`. Make T025 to T028 pass. Depends on T032.
- [X] T034 [US2] Add a worked example to `packages/waypoint_etl/examples/sample_pipeline.py` (declaration, `map_step`, `item`, thread-pool variant and an item that fails) and run it against a fake store as a smoke test; document in the example that keys are ids or indices only.

**Checkpoint**: a map loop writes the aggregate and item records of contracts/redis-keys.md under threads, asyncio and plain loops; all library tests pass; behaviour without map scopes is unchanged.

---

## Phase 5: User Story 6 - Existing pipelines and older libraries keep working unchanged (Priority: P1)

**Goal**: Pipelines without a map step, runs from older libraries and an older monitor are unaffected.

**Independent Test**: Open runs recorded before this feature, runs from library 0.5.0 and a pipeline with no map step; display and JSON are identical to before and nothing logs an error.

### Tests for User Story 6

- [X] T035 [P] [US6] Add golden tests to `waypoint_monitor/tests/test_api.py` and `waypoint_monitor/tests/test_analysis.py`: the JSON of `/api/runs` for a run with no map step and for a run written by library 0.5.0 (fixtures copied from the spec 013 seed) equals the stored golden output, with no `map` key anywhere and `flow.steps[i]` without `map`; `unreadable_total` is 0.
- [X] T036 [P] [US6] Add library regression tests in `packages/waypoint_etl/tests/test_second_pipeline.py` and `packages/waypoint_etl/tests/test_unconfigured.py`: a spec with no map step produces the same records (step, marker, failed, flow, events, metrics) as before for a sequential run; code that never calls `map_step` or `item` writes no `...:map:...` or `...:item:...` key; `audited_step` outside `item()` is unchanged when a map block is open elsewhere in another thread's context.
- [X] T037 [P] [US6] Add to `waypoint_monitor/static/tests/state.test.mjs` and `run-view.test.mjs` cases proving a run with no `map` data renders the same node, list and step markup as before (snapshot of the current output kept as the expected value).

### Implementation for User Story 6

- [ ] T038 [US6] Fix whatever T035 to T037 reveal (expected: none). Confirm by hand against the quickstart section 5: new monitor with the 0.5.0 library, old monitor build (spec 013 tag) with the 0.6.0 library showing the map step as one ordinary step, rollback to 0.5.0 with no cleanup. Record the three observations in the PR description. *Not done: the golden tests cover a 0.5.0-shaped run on the new monitor; the old-monitor-build and rollback checks were not run by hand.*

**Checkpoint**: P1 stories complete (US1, US2, US6). This is the MVP.

---

## Phase 6: User Story 3 - Find slow and failing items in a big loop (Priority: P2)

**Goal**: Filter, search, sort and page the item list, and see loop duration, median, 95th percentile and the slowest item.

**Independent Test**: A map of 200 items with three failed and five slow: filter failed (3), slow (the five), sort by duration slowest first, search a key; the summary durations are right; paging repeats nothing.

### Tests for User Story 3

- [X] T039 [P] [US3] Extend `waypoint_monitor/tests/test_maps_domain.py` for `select_items(items, aggregate, settings, state, slow, q, sort, order, limit, after)`: `state` filters; `slow=1` uses `slow_run_multiple × median` with the aggregate's histogram median and requires `count >= duration_min_runs` (fewer finished items: nothing is slow; a running item is never slow); `q` is a case-sensitive substring of the key (<= 64 characters); sort `index` (default asc), `duration` (default desc, running items last), `key`; the order is always sort value, then arrival number, then key; the cursor continues strictly after the last item (no repeats while items change between calls, an item whose duration appeared between pages is not shown twice); `counts` are over all records read and `matched` over the filtered set; invalid `state`, `sort`, `order`, `limit` or `after` raise a validation error mapped to 400.
- [X] T040 [P] [US3] Extend `waypoint_monitor/tests/test_api.py` for the items route with `state`, `slow`, `q`, `sort`, `order`, `limit` and `after` (three pages over 120 items with no repeats and no gaps, 400 cases, `next` null on the last page) and for `map.duration` in `/api/runs` (`median_ms`, `p95_ms` within 5% of the true values for a seeded histogram, `enough` false and values null below the minimum, `approx` true).
- [X] T041 [P] [US3] Extend `waypoint_monitor/static/tests/map-model.test.mjs` for `durationLine(map)` (`median ≈3.9 s`, `p95 ≈9.1 s`, `percentiles need 5 finished items` when not enough), `slowestLabel(map)`, `itemQuery(state)` building the query string (reset of the cursor when a filter changes) and `mergePages(pages)` keeping order and dropping an item already shown.

### Implementation for User Story 3

- [X] T042 [US3] Implement `select_items` in `waypoint_monitor/app/domain/maps.py` and an opaque cursor codec (base64 of `sort value|arrival number`, rejected when malformed); mark each returned item's `slow`, `failed_step`, `error_type`, `in`, `out`, `loss`. Depends on T039.
- [X] T043 [US3] Extend the items route in `waypoint_monitor/app/api/routes.py` with the query parameters of contracts/api.md (`state`, `slow`, `q`, `sort`, `order`, `limit`, `after`) using `select_items`; 400 on invalid input with the existing `_error` shape. Depends on T042, T040.
- [X] T044 [US3] Make `summarize` return `duration: {count, median_ms, p95_ms, approx, enough}` using `percentile_ms` and `settings.duration_min_runs`, and `slowest` (<= 5). Depends on T018.
- [X] T045 [P] [US3] `UI` Add `durationLine`, `slowestLabel`, `itemQuery` and `mergePages` to `waypoint_monitor/static/js/model.js` so `map-model.test.mjs` (T041) passes.
- [X] T046 [US3] `UI` Extend `waypoint_monitor/static/js/views/map.js` per the design (or contracts/ui.md "Map panel"): summary line with median, p95 and the `slowest` button; search box, state chips with counts (`aria-pressed`), a `Slow` chip, sort select with direction, "Show more" using `next`, restart from the first page on any filter change, refresh re-reads the pages already shown, `aria-live="polite"` match count, failed chip selected by default when the map failed. Depends on T045.
- [X] T047 [US3] Make T039 to T041 pass and run all suites. Depends on T042 to T046.

**Checkpoint**: filters, search, sort, paging and duration numbers work against seeded data in the API and the browser.

---

## Phase 7: User Story 4 - Inspect one item's own steps, counts, errors, events and metrics (Priority: P2)

**Goal**: One item's detail: inner steps in order with counts, durations, errors, loss, metrics and events.

**Independent Test**: An item whose last inner step outputs fewer records than it received shows the loss at the item and the map; its events and metrics are only its own; a failed item shows `not run` for later steps.

### Tests for User Story 4

- [X] T048 [P] [US4] Extend `waypoint_monitor/tests/test_maps_domain.py` for `item_detail(record, decl, settings, flow)`: steps follow the declared item flow in order; a declared step with no result is `not_run` when the item is failed or done and `waiting` when running; a result for an undeclared step is added with `unplanned: true`; inputs are ordered by the declared input names like `_ordered_inputs`; an inner step with `output == 0` and an input above 0 has `loss: true`; metrics use the spec 013 shape (declared label, unit, threshold flags via `step_metrics`) per inner step; the error block keeps type, message and trace (compact records have none); an item-level `error` is passed through.
- [X] T049 [P] [US4] Extend `waypoint_monitor/tests/test_api.py` and `waypoint_monitor/tests/test_timeline.py`: `GET .../maps/{map}/items/{key}` returns the shape of contracts/api.md, 404 `{"error": "Item not found"}` for a key with no record and 400 for an invalid key; `GET .../events?item=acct-7` returns only events with that `item` and totals follow the filtered set; events with `item` parse (`parse_events` keeps an `item` matching `^[A-Za-z0-9_.-]{1,64}$`, drops other values); an event without `item` is unchanged; `select(...)` takes an optional `item` filter.
- [X] T050 [P] [US4] Extend `waypoint_monitor/static/tests/map-model.test.mjs` for `itemStepsView(detail)` (states, `not run` and `waiting` labels, loss marker, error presence) and the item URL state in `static/tests/router.test.mjs` (`item=` query round trip, unknown item key ignored).

### Implementation for User Story 4

- [X] T051 [US4] Implement `item_detail` in `waypoint_monitor/app/domain/maps.py` (reuse `_is_loss` and `_ordered_inputs` from `analysis.py` by moving them to a shared module only if importing them would create a cycle) and the detail route in `waypoint_monitor/app/api/routes.py`. Depends on T048, T049.
- [X] T052 [US4] Add the optional `item` field to the event model and parser in `waypoint_monitor/app/domain/models.py` (`RunEvent.item: Optional[str]`) and `waypoint_monitor/app/domain/parsing.py`; add the `item` filter to `select` in `waypoint_monitor/app/domain/timeline.py` and the `item` query parameter to the events route in `waypoint_monitor/app/api/routes.py` (empty result for an unknown key; the public event JSON includes `item` when present). Depends on T049.
- [X] T053 [P] [US4] `UI` Add `itemStepsView` and the `item` query support to `waypoint_monitor/static/js/model.js`, `static/js/router.js` and `static/js/api.js` (`fetchItem`, `fetchEvents` with `item`), so T050 passes.
- [X] T054 [US4] `UI` Build the item view in `waypoint_monitor/static/js/views/map.js` per the design (or contracts/ui.md "Item view"): header, inner steps in order with in/out counts and durations, the existing `errorBlockHTML` for failed steps, `not run` and `waiting` labels, step data-loss pill, the metrics table through the existing metrics renderer in `static/js/ui.js`, the item's events through `static/js/views/events.js` with the `item` filter, "This item has no record of its own (item detail is partial)." for a 404, refresh without losing scroll or selection, Escape closes and focus returns to the row, the URL carries the item. Add styles to `static/styles.css`. Depends on T051, T052, T053.
- [X] T055 [US4] Show `items lost data` on the map node and in the summary when `lost_items > 0` (spec SC-007) and make the loss visible on item rows (`data lost` marker). Depends on T054, T022.

**Checkpoint**: an item can be opened from the list or the `slowest` button, with its own steps, counts, errors, metrics and events.

---

## Phase 8: User Story 5 - Keep a huge loop from flooding the store or the screen (Priority: P2)

**Goal**: A 10,000-item loop stays within the fixed storage bound and the page stays fast and honest about partial detail.

**Independent Test**: Run a 10,000-item map (with failures and a few slow items): the aggregate counts all items, item records stay within 1,000 + 1,000 compact failed + 50 slow, the run page opens under 3 s, and the screen states what is partial.

### Tests for User Story 5

- [X] T056 [P] [US5] Extend `packages/waypoint_etl/tests/test_maps.py` for retention (research R5): the first `MAP_DETAIL_LIMIT` (1000) items keep full records; a later item that fails keeps a compact record (no `metrics`, no traceback, message at most `COMPACT_MESSAGE` (200) characters) until `MAP_EXTRA_FAILED_LIMIT` (1000) is reached, then only `failed_without_record` grows; a later item that finishes among the `MAP_SLOWEST_KEPT` (50) slowest later items keeps a compact record and the displaced one is queued for rewrite with `EVICT_TTL_SECONDS` (1); later items that neither fail nor are slow leave no record; running items beyond the limit are never written; counts, `inner`, in/out sums, histogram and `lost_items` cover every item; a full record's traceback is cut to `ITEM_TRACE_BYTES` (2048 bytes, last frames kept).
- [X] T057 [P] [US5] Add to `packages/waypoint_etl/tests/test_map_writer.py` a bound test: 10,000 items with 1 in 20 failing and rising durations leave at most 1,000 + 1,000 + 50 live item keys in the fake store (evicted keys are rewritten with a 1-second TTL), the aggregate is under 4 KB, and total written bytes stay under a documented ceiling asserted in the test; and an all-fail run leaves 2,000 failed records and a correct `failed_without_record` of 8,000.
- [X] T058 [P] [US5] Extend `waypoint_monitor/tests/test_maps_domain.py` and `waypoint_monitor/tests/test_api.py`: `detail.partial` is true when `started > kept`, `failed_without_record` is passed through, the items route reports `total`, `with_record` and `partial`, and an item-less run page performs no `list_items` call (fake store call log) even for a 10,000-item aggregate.
- [X] T059 [P] [US5] Extend `waypoint_monitor/static/tests/map-model.test.mjs` for `mapPartialNotice` (`Showing items with a record: 1,050 of 10,000. Totals cover every item.`, `37 further failed items have no record of their own.`, nothing when not partial, thousands separators via the existing `fmt`).

### Implementation for User Story 5

- [X] T060 [US5] Implement retention in `MapTracker` (`packages/waypoint_etl/src/waypoint_etl/maps.py`): arrival-number based detail slots, compact record build at item end, the bounded top-50 slowest set (heap) with eviction, failed counters (`kept`, `failed_without_record`, `slow_kept`) written into the aggregate's `detail`, traces cut to 2048 bytes in full records, and `MapWriter` writing an evicted slow record with `EVICT_TTL_SECONDS`. Depends on T056, T057, T030.
- [X] T061 [US5] Monitor side: expose `detail.partial`, `kept` and `failed_without_record` in `summarize` and the items route (`partial`, `failed_without_record`); no extra reads. Depends on T058, T018.
- [X] T062 [US5] `UI` Show the partial-detail notices in the map panel (`mapPartialNotice`) and keep the node text unchanged; confirm no per-item DOM beyond one page for 10,000 items. Depends on T059, T023.
- [X] T063 [P] [US5] Extend `waypoint_monitor/tests/seed_demo.py` with: a running map run (6 done, 4 running), a failed map run (one item failing in the second inner step), a 10,000-item run (aggregate plus 1,050 records, 188 failed with 37 without a record), a map run with item-level data loss, a run from the pre-map library and a stalled map run, so the browser pass in the quickstart has data.
- [X] T064 [US5] Measure and record in the PR description (not as a test threshold): the 10,000-item run's `/api/runs` time versus a run without a map, the items first page time for 1,000 records, the key count and bytes of the all-fail run, and the hot-loop overhead of recording (spec SC-004, SC-005, SC-009). Fix anything outside the success criteria. *Measured locally: /api/runs 28 ms with the 10,000-item run, item list first page 38 ms, 1,050-record page 28 ms; 10,000 items recorded in 0.34 s; 100,000 metric calls in an item 0.20 s.*

**Checkpoint**: huge loops are bounded and honest; the page stays fast.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T065 [P] Document `map_step()`, `item()`, `MapStepSpec`, the item-key rule ("ids or indices only, never names or contact data"), the retention limits, the per-process limit and the write interval in `packages/waypoint_etl/README.md`; add a map step section (key families, no new permission, new API routes, the `item` event filter, how Failed is derived) to `waypoint_monitor/README.md`; update the root `README.md` feature list.
- [X] T066 [P] Update the `adopting-waypoint-etl` skill (`.claude/skills/adopting-waypoint-etl/`) with the loop recipe: when to use a map step, declaration, `map_step` and `item`, thread-pool and asyncio patterns, key rules and what the operator sees.
- [X] T067 Run all quality gates in both packages (`mypy --strict`, `ruff check .`, `black --check .`, all unit tests, `node --test static/tests/*.test.mjs`) and fix findings. Check the constitution table of plan.md once more: no new Redis permission, no new dependency, item keys sanitised, all text escaped.
- [ ] T068 Run the quickstart end to end: sections 1 to 5 (automated suites, library scenarios, monitor scenarios, browser pass with screenshots at 1280 px and 390 px in light and dark, compatibility), and tick every success criterion SC-001 to SC-010 against a passing check; note any gap in the PR description. *Partly done: automated suites, library scenarios, API checks against a real Redis and a browser pass (dark, one mobile light screenshot, keyboard open/Esc/focus) were run; the full Tab-order pass, screen-reader labels, light theme on every state and the 100,000-call hot-loop timing at 5% were not.*
- [X] T069 Update `specs/roadmap.md`: mark item 7 done with the spec number, the library version `0.6.0` and the answer to open decision 12 (N up to about 10,000, no per-item retry control, fan-in is "all items succeeded" with partial results shown). Release tag and install URLs are updated at release time, as for earlier versions.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup; blocks every story. Library tasks (T003 to T005) and monitor tasks (T006 to T013) are independent of each other.
- **US1 (Phase 3, monitor read side)** and **US2 (Phase 4, library write side)**: both start after Phase 2 and can run in parallel; each is testable alone (US1 on seeded records, US2 on a fake store). Together they are the MVP.
- **US6 (Phase 5)**: after US1 and US2 (it checks that nothing regressed).
- **US3, US4, US5 (Phases 6 to 8)**: after US1 and US2. US3 and US4 are independent of each other and of US5; US5 touches the tracker and writer from US2 and the summary from US1.
- **Polish (Phase 9)**: after the stories wanted for the release.

### Task Dependencies Inside Stories

- T004 → T005; T006 → T007/T008, T009/T010; T010, T011, T012 → T013.
- US1: T014 to T017 (tests, parallel) → T018 → T019 → T020 → UI tasks T021 → T022 → T023 → T024.
- US2: T025 to T028 (tests, parallel) → T029 → T030 → T031 → T032 → T033 → T034.
- US3: T039 to T041 (tests) → T042 → T043; T044 after T018; UI T045 → T046 → T047.
- US4: T048 to T050 (tests) → T051, T052 → UI T053 → T054 → T055.
- US5: T056 to T059 (tests) → T060 (library), T061 (monitor), T062 (UI) → T063 → T064.
- UI tasks wait for the design that the user will supply; the model, API and library tasks do not.

### Parallel Opportunities

- Foundational library (T003) and monitor (T006, T009, T011, T012) in parallel; US1 and US2 in parallel after Phase 2.
- All test-writing tasks inside a story are marked [P] (different files).
- `LIB` and `MON` never touch the same files except through the data contracts.

## Parallel Example: US2 and US1 together

```bash
# After Phase 2, one developer on the library (US2), one on the monitor (US1):
Task: "Create maps.py: sanitise_key, MapTracker ... in packages/waypoint_etl/src/waypoint_etl/maps.py"      # T029
Task: "Implement domain/maps.py: map_state, summarize ... in waypoint_monitor/app/domain/maps.py"         # T018
# Then meet at the checkpoint: run the library example against Redis and open it in the monitor.
```

## Implementation Strategy

### MVP First (US2 + US1 + US6)

1. Phase 1 and Phase 2.
2. US2 (library recording) and US1 (monitor display) in parallel.
3. US6 regression gate.
4. **Stop and validate**: run `packages/waypoint_etl/examples/sample_pipeline.py` with a map step against local Redis and watch progress and the failing item in the browser.

### Incremental Delivery

1. MVP above (progress, state, failing item).
2. US3: filters, search, sort, paging, durations.
3. US4: item view with metrics and events.
4. US5: retention bounds and partial-detail notices (ship together with or before any use on loops over 1,000 items; until then document the 1,000-item expectation).
5. Polish and release `0.6.0`.

## Notes

- [P] tasks = different files, no dependencies.
- [Story] labels map tasks to spec stories for traceability.
- Tests first: confirm each new test fails before its implementation task.
- Commit after each task or logical group.
- Avoid: reading item keys from `/api/runs`; adding a total item count anywhere; any new Redis permission; storing data content in item keys.
