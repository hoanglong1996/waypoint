---

description: "Task list for Optional Step Metrics"
---

# Tasks: Optional Step Metrics

**Input**: Design documents from `/specs/013-step-metrics/`

**Prerequisites**: plan.md, spec.md, research.md (R1-R10), data-model.md, contracts/{redis-keys,library-api,api,ui}.md, quickstart.md

**Tests**: Included. The constitution (principle IV) requires tests for changed behaviour, and spec FR-021 / SC-007 need regression tests for unchanged old runs.

**Organization**: Grouped by user story. Paths are relative to the repository root. `LIB` = `packages/waypoint_etl`, `MON` = `waypoint_monitor`.

**Conventions**: Python is fully typed (`mypy --strict`), `ruff` + `black` line length 100; the library supports Python 3.10+ and uses only the standard library. Test runners: `python -m unittest discover tests` (in `LIB` and in `MON`), `node --test static/tests/*.test.mjs` (in `MON`). In the front end the old `metric(step)` (output count) is untouched; new code uses `stepMetrics`, `metricTrend`, `metricsOver` and CSS prefix `.xmetric` (research R9).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1-US4 (from spec.md)

Story map: US1 see a step's metrics while it runs and after · US2 choose set / add / max · US3 declare unit and threshold, flags and badges · US4 metric trend in History.

## Phase 1: Setup

- [X] T001 Run the baseline before changing anything: in `packages/waypoint_etl` and in `waypoint_monitor` run `python -m unittest discover tests`, `mypy`, `ruff check .`, `black --check .`; in `waypoint_monitor` run `node --test static/tests/*.test.mjs`. Record the pass counts under "Baseline" at the end of `specs/013-step-metrics/quickstart.md`
- [X] T002 [P] Verify research R10 by test (key patterns covered in `TestParseMetrics`; the older-monitor flow case is inherent: `parse_flow` reads only known fields): add a case to `waypoint_monitor/tests/test_parsing.py` showing that key patterns for step, marker, failed and event keys do not match `waypoint:p:env:20261017T020301Z:metrics:01-load`, and a case to `waypoint_monitor/tests/test_flow.py` showing `parse_flow` ignores an unknown `metrics` field on a step (the flow still parses with no problems). Record any difference in `specs/013-step-metrics/research.md` R10

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: Both sides know the new key and the data shapes; the monitor can read metric records from the store. No behaviour change yet.

### Library

- [X] T003 [P] Add to `packages/waypoint_etl/src/waypoint_etl/keys.py`: `metrics_key(pipeline, env, run_id, index, step)` returning `waypoint:{pipeline}:{env}:{run_id}:metrics:{index:02d}-{step}`, and constants `MAX_METRICS_PER_STEP = 20`, `MAX_METRIC_NAME = 64`, `MAX_METRIC_LABEL = 40`, `MAX_METRIC_UNIT = 16`, `METRICS_VERSION = 1`, `METRIC_FLUSH_SECONDS = 1.0`. Add exact-string tests to `packages/waypoint_etl/tests/test_keys.py` (two-digit padding, index 100 gives `100-`)

### Monitor

- [X] T004 [P] Add to `waypoint_monitor/app/domain/models.py` (frozen dataclasses, fully typed): `StepMetrics` (pipeline, env, run_id, step, index int >= 1, updated_at Optional[datetime], values `Dict[str, Union[int, float]]`: "at most 20 entries; names `^[a-z0-9_]{1,64}$`; values finite numbers, never bool") and `MetricDecl` (name, label Optional[str] at most 40 characters, unit Optional[str] at most 16 characters, warn_above Optional[float], warn_below Optional[float]); add `metrics: Tuple[MetricDecl, ...] = ()` as the last field of `FlowStep` (default keeps every existing construction valid)
- [X] T005 [P] Write failing tests in `waypoint_monitor/tests/test_parsing.py` for `parse_metrics(env, pipeline, raw)` returning `(List[StepMetrics], Dict[str, int])` (records, unreadable count per run id): a valid record parses; wrong `v`, wrong `pipeline`/`env`/`run_id`/`step`/`index` vs the key, non-object, not JSON, `metrics` not an object, or more than 20 entries counts one unreadable for its run; inside a readable record, an entry with an invalid name or a bool, string, null, NaN or infinite value is dropped without making the record unreadable; `updated_at` of the wrong type becomes None; a key with an invalid run id is ignored (not counted)
- [X] T006 Implement `parse_metrics` and the key regex `_METRICS_KEY = rf"^{ROOT}:{_P}:metrics:(?P<idx>\d{{2,}})-(?P<step>.+)$"` in `waypoint_monitor/app/domain/parsing.py`, mirroring `parse_failures`; never raises. Make T005 pass
- [X] T007 [P] Add `list_metrics(env, pipeline) -> List[Tuple[str, str]]` ("Return `(key, raw_json)` pairs for every metrics record. Read only.") to the `RecordStore` protocol in `waypoint_monitor/app/infrastructure/store.py`, implement it in `waypoint_monitor/app/infrastructure/redis_store.py` as `self._scan(f"{ROOT}:{pipeline}:{env}:*:metrics:*")`, and add it to the in-memory store in `waypoint_monitor/tests/fakes.py` (including the unreachable variant raising `StoreUnavailable`); add a `list_metrics` case to `waypoint_monitor/tests/test_redis_store.py` (uses `SCAN` + `MGET` only, no other command)
- [X] T008 Add `metrics: Raw` to the `Window` named tuple in `waypoint_monitor/app/api/routes.py`, read it in `keys_for` with `store.list_metrics(env, pipeline)`, and include `list_metrics` in the cache-drop-on-unavailable path; no output change yet. Extend `waypoint_monitor/tests/test_api.py` so the unreachable-store case still returns 503 and cached windows include metrics

**Checkpoint**: metric records can be written to a fake store and read back through `parse_metrics`; all existing tests pass.

---

## Phase 3: User Story 1 - See a step's metrics while it runs and after (Priority: P1) 🎯 MVP

**Goal**: A pipeline calls `waypoint_etl.metric("rejected", 42)` inside a step; the operator sees it in the step's details, live and after the step, with no declaration.

**Independent Test**: Run a step that records two metrics; open the step's details while it runs and after it finishes; both values are shown and correct. A run with no metrics looks exactly as before.

### Tests for User Story 1

- [X] T009 [P] [US1] Write failing tests in `packages/waypoint_etl/tests/test_metrics.py` (new) for the `set` mode only: inside `StepAuditor.run`/`audited_step`, `metric("rows", 10)` then `metric("rows", 4)` leaves 4; a call without `step` outside any step does nothing and raises nothing; before `init` and after a failed `init` it does nothing; a call with `step="load"` after `load` finished still lands on the same attempt; a call with an explicit step that never began is dropped with exactly one warning; a retried step (second `begin` of the same name) starts from empty metrics at the new index; names not matching `^[a-z0-9_]{1,64}$`, bool, str, None, NaN, infinity values are dropped with one warning per name and never raise; the 21st distinct name is dropped with one warning while the first 20 keep updating
- [X] T010 [P] [US1] Write failing tests in `packages/waypoint_etl/tests/test_metric_writer.py` (new): after a call the record appears in the store at `metrics_key(...)` with `{"v": 1, "pipeline", "env", "run_id", "step", "index", "updated_at", "metrics": {...}}` within one flush interval (use an injected clock/short interval); 1,000 calls to the same metric produce at most a handful of writes (coalesced), never one per call; `submit` never blocks when the store hangs or raises (failing store logs at most one warning per minute and later writes still happen once the store recovers); `stop()` and `flush` deliver pending state within 2 seconds; TTL passed to the store equals the auditor's `ttl_seconds`; with `NoopStepAuditStore` nothing breaks
- [X] T011 [P] [US1] Write failing tests in `waypoint_monitor/tests/test_metrics.py` (new) for `domain/metrics.py::step_metrics(records, step_name, attempt_index, declared)`: returns None when no record has `index == attempt_index` (a record of an older attempt is ignored); returns undeclared metrics sorted by name with `declared: false`, `flag: null`, `label: null`, `unit: null`, `updated_at` ISO string; returns an empty/None result for no records
- [X] T012 [P] [US1] Extend `waypoint_monitor/tests/test_analysis.py`: a running step with a metrics record at its attempt index shows `metrics` (so values are visible before the finish record exists); a done step shows the final values; a retried step shows only the new attempt's record; a failed step keeps the metrics recorded before the failure; a metrics record for a step with no marker, finish record or failure is ignored and creates no run; a run with no metrics records has no `metrics` key on any step and `metrics_over` 0 everywhere (old-run regression)
- [X] T013 [P] [US1] Add front-end tests in `waypoint_monitor/static/tests/metrics.test.mjs` (new) for `stepMetrics(step)` (returns `[]` for a step without `metrics`), `formatMetricValue(value, unit)` (`150` + `rows` gives `150 rows`; `12345` gives `12.3k`; `0.25` stays `0.25`; null gives `not reported`) and `api.js` mapping (`metrics` camelCased as `{name, label, value, unit, declared, flag, updatedAt}`); old payload without `metrics` maps to no metrics

### Implementation for User Story 1

- [X] T014 [US1] Create `packages/waypoint_etl/src/waypoint_etl/metrics.py`: `valid_name(str) -> bool`, `valid_value(object) -> bool` ("`int` or `float`, not `bool`, finite"), and `class MetricState` holding `Dict[Tuple[int, str], Dict[str, Union[int, float]]]` under one `threading.Lock` with `apply(index, step, name, value, mode)` (this task implements `set`; unknown mode returns False), a dirty set, and `take_dirty() -> List[(index, step, values copy)]`. Enforce `MAX_METRICS_PER_STEP` counting only new names. No I/O. Part of making T009 pass
- [X] T015 [US1] Add `class MetricWriter` to `packages/waypoint_etl/src/waypoint_etl/metrics.py`, same pattern as `events.EventWriter`/`Heartbeat`: a daemon thread started on first mark-dirty, waking at most every `METRIC_FLUSH_SECONDS`, writing each dirty attempt as the full record (`v`, `pipeline`, `env`, `run_id`, `step`, `index`, `updated_at` as `%Y-%m-%dT%H:%M:%SZ`, `metrics`) through `store.write(metrics_key(...), record, ttl_seconds)`; failures caught and logged at most once a minute (print `Warning: Waypoint metrics not written: ...`, like events); `flush(timeout=2.0)` and `stop(timeout=2.0)` as in `EventWriter`; `submit`-style marking never blocks and never raises. Make T010 pass
- [X] T016 [US1] In `packages/waypoint_etl/src/waypoint_etl/auditor.py`: remember the latest attempt index per step name in `begin()` (`self._latest_index[name] = index`, kept after the step ends); add `record_metric(name, value, step, mode)` that resolves the step (`step or current_step.get() or self.current_open_step()`; none gives a silent return), resolves the index from `_latest_index` (unknown step gives one warning per step name and returns), applies it to `MetricState`, marks it for the writer, and never raises; create the writer lazily like `_event_writer`; `stop()` and `flush_events()` also stop/flush the metric writer (same 2 s budget, not 2 s each: pass the remaining time). Make T009 pass
- [X] T017 [US1] In `packages/waypoint_etl/src/waypoint_etl/registry.py` add `metric(name, value, *, step=None, mode="set") -> None` that calls `_active.record_metric(...)` inside `try/except Exception: return`, with the docstring from `contracts/library-api.md`; export it from `packages/waypoint_etl/src/waypoint_etl/__init__.py` (`__all__`, module docstring example line). Extend `packages/waypoint_etl/tests/test_unconfigured.py`: `metric(...)` before `init` returns None and raises nothing
- [X] T018 [US1] Create `waypoint_monitor/app/domain/metrics.py` with `step_metrics(records, step_name, attempt_index, declared)` returning the ordered list from `contracts/api.md` ("`metrics` is omitted when the step has none declared and none recorded"; "undeclared by name"); for this story every entry is undeclared (`declared: false`, `label`, `unit`, `flag` null). Make T011 pass
- [X] T019 [US1] In `waypoint_monitor/app/domain/analysis.py`: add parameter `metrics: Sequence[StepMetrics] = ()` to `build_runs` and `_build_run`; group by run and step; in `add_done`, `add_unfinished`, `add_failed` (all three step states) attach `metrics` from `step_metrics(...)` for the step's attempt index (finish record index, marker index, failure index) and set `metrics_over` to 0 for now; add `metrics_over: 0` at run level. Do not let a metrics record create a run (do not touch `by_run`). Make T012 pass
- [X] T020 [US1] In `waypoint_monitor/app/api/routes.py::build`: call `parse_metrics(env, pipeline, window.metrics)`, merge its per-run unreadable counts into `by_run` exactly like failures, pass the records to `build_runs(..., metrics=...)`. Add a case to `waypoint_monitor/tests/test_api.py` that a damaged metrics record adds to the run's `unreadable` and the rest of the run is served
- [X] T021 [P] [US1] Map metrics in `waypoint_monitor/static/js/api.js::mapStep` for every state that can carry them (done/unplanned, running/stalled/waiting, died, failed): `metrics: (s.metrics || []).map(...)` with `updatedAt` as Date or null; add `stepMetrics(step)` and `formatMetricValue(value, unit)` to `waypoint_monitor/static/js/model.js` (compact form via the existing `compact`; exact value in a title). Make T013 pass
- [X] T022 [US1] Add `metricsTableHTML(step)` to `waypoint_monitor/static/js/ui.js` (a `<table class="xmetric">` with columns Metric, Value; name via `esc`, label when declared with the name in a `title`; "not reported" in muted text; returns '' for no metrics) and call it from `stepItemHTML` in `waypoint_monitor/static/js/views/step.js` after the output block and before the events block, for done, running, stalled, failed and died steps (not missing/waiting). The graph's "Selected step" panel in `waypoint_monitor/static/js/views/graph.js` reuses `stepItemHTML`, so no separate change; confirm that in a test. Add styles for `.xmetric` (compact table, muted `not reported`, mono numbers, wraps at phone width) to `waypoint_monitor/static/styles.css`
- [X] T023 [US1] Add a view test in `waypoint_monitor/static/tests/run-view.test.mjs`: a step with two metrics renders both names and values escaped as plain text (`<b>` in a name appears as text), a step without metrics renders no `.xmetric`, and a running step renders its current values. Re-render after a refresh with changed values updates the table (compare with the existing refresh test pattern in that file)

**Checkpoint**: US1 works end to end on its own: a step records a number, it shows in the details while running and after, old runs unchanged.

---

## Phase 4: User Story 2 - Choose how a number is combined (Priority: P1)

**Goal**: `set`, `add` and `max` behave as specified, exactly, from many threads.

**Independent Test**: `retries` add 1,2,3 gives 6; `rows` set 10 then 4 gives 4; `peak` max 5,9,7 gives 9; 8 threads adding 1,000 each gives 8,000.

- [X] T024 [P] [US2] Extend `packages/waypoint_etl/tests/test_metrics.py`: `add` of 1, 2, 3 gives 6 (first call starts from the value); `max` of 5, 9, 7 gives 9; mixing modes on one name applies the latest call's operation to the current value; an unknown mode (`"sum"`, `None`, `3`) is dropped with one warning and never raises; an `add` or `max` whose result would be infinite or NaN (for example `1e308 + 1e308`) is ignored and the old value kept; int + float works and the stored JSON number is valid; 8 threads x 1,000 `add(1)` give exactly 8,000 inside a running step; threads in different asyncio tasks each attach to their own running step name through `current_step`
- [X] T025 [P] [US2] Add a timing test to `packages/waypoint_etl/tests/test_metrics.py`: 100,000 `metric("n", 1, mode="add")` calls inside a step add no more than 5% over a baseline loop that does equivalent trivial work, using a generous bound (assert under 3x a plain dict-update loop, and under 2 s absolute) so CI is not flaky; and no store write per call (store write count under 10)
- [X] T026 [US2] Implement `add` and `max` in `MetricState.apply` in `packages/waypoint_etl/src/waypoint_etl/metrics.py`: `set` replaces; `add` adds to the current value (or stores the value when absent); `max` keeps the larger (or stores when absent); a non-finite result is rejected leaving the old value; unknown mode returns False and the auditor logs one warning (per distinct bad mode); all under the existing lock. Make T024 and T025 pass
- [X] T027 [US2] Add the three-mode example to the sample pipeline `packages/waypoint_etl/examples/sample_pipeline.py` (`rejected` add inside a loop, `peak_batch` max, `rows` set) so the quickstart can run it

**Checkpoint**: US1 and US2 together are the usable feature without declarations.

---

## Phase 5: User Story 3 - Declare a metric with a unit and a warning threshold (Priority: P2)

**Goal**: Authors declare `Metric(...)` on a step; the monitor shows label and unit, flags over-threshold values, and badges the step in list and graph.

**Independent Test**: Declare `rejected` with `warn_above=100`; record 150: flagged in details, list and graph; record 50 in another run: not flagged. Equal to 100: not flagged. Declared but never recorded: `not reported`, no flag.

### Tests for User Story 3

- [X] T028 [P] [US3] Extend `packages/waypoint_etl/tests/test_spec.py` (create if absent, next to the existing spec tests) and `packages/waypoint_etl/tests/test_auditor.py`: `Metric("rejected", label="Rejected rows", unit="rows", warn_above=100)` is valid; invalid: name not matching `^[a-z0-9_]{1,64}$`, duplicate name in one step, more than 20 in a step, label longer than 40 characters, unit longer than 16 characters, threshold bool/NaN/infinite/non-number, `warn_below > warn_above`; an invalid declaration makes `validate_spec` raise `ValueError` naming the step and metric, and `init` then returns False with the usual warning; the flow record written at `start()` carries `metrics` only on steps that declare them, with only the set keys (`label`, `unit`, `warn_above`, `warn_below` omitted when None) and `v` still equals `FLOW_VERSION` (1)
- [X] T029 [P] [US3] Extend `waypoint_monitor/tests/test_flow.py`: `parse_flow` reads step `metrics` into `MetricDecl` tuples; a declaration with a bad name, a non-number threshold, a duplicate name, or beyond 20 per step is dropped and adds a problem string ("a metric declaration of 'step' was dropped"), never failing the flow; labels trimmed and cut to 40, units cut to 16; a flow without `metrics` gives empty tuples
- [X] T030 [P] [US3] Extend `waypoint_monitor/tests/test_metrics.py`: declared metrics come first in declared order, then undeclared alphabetically; a declared metric with no recorded value has `value: null`, `flag: null`; flag is `above` only when `value > warn_above` and `below` only when `value < warn_below` (equal is not flagged, both thresholds checked independently, an int value against a float threshold works); undeclared never flagged; `metrics_over` counts flagged entries; label and unit are carried through
- [X] T031 [P] [US3] Extend `waypoint_monitor/tests/test_analysis.py` and `waypoint_monitor/tests/test_api.py`: step `metrics_over` and run `metrics_over` (sum) are right; the run's `status`, `needs attention` order and `loss_steps` are identical with and without a flagged metric (FR-017); `flow.steps[].metrics` is served as stored with null for absent keys; a step declared but never begun (waiting/missing) carries no `metrics`
- [X] T032 [P] [US3] Extend `waypoint_monitor/static/tests/metrics.test.mjs`: `metricsOver(step)` counts flagged; the flag text helper gives `above 100` / `below 90` using the threshold from the flow definition; `api.js` maps `flow.steps[].metrics` to `def.metrics` (camelCase `warnAbove`, `warnBelow`) and `metrics_over` to `metricsOver`; add a view test in `waypoint_monitor/static/tests/run-view.test.mjs` that a flagged metric row has a text flag cell (not colour only) and the step card header shows the badge text `1 metric over limit` (and `2 metrics over limit` for two), and the graph node carries the same text in its accessible name

### Implementation for User Story 3

- [X] T033 [US3] In `packages/waypoint_etl/src/waypoint_etl/spec.py` add `@dataclass(frozen=True) class Metric` (`name: str`, `label: Optional[str] = None`, `unit: Optional[str] = None`, `warn_above: Optional[float] = None`, `warn_below: Optional[float] = None`), add `metrics: Tuple[Metric, ...] = ()` as the last field of `StepSpec`, and validate in `validate_spec` with the rules of T028: "name `^[a-z0-9_]{1,64}$`, unique within the step", "at most 20 per step", "label at most 40 characters", "unit at most 16 characters", "thresholds finite, not bool", "`warn_below <= warn_above` when both". Export `Metric` from `packages/waypoint_etl/src/waypoint_etl/__init__.py`. Part of making T028 pass
- [X] T034 [US3] In `packages/waypoint_etl/src/waypoint_etl/auditor.py::_flow_value` add the optional `metrics` list to a step entry when it declares any (omit unset keys); leave `FLOW_VERSION` at 1. Make T028 pass
- [X] T035 [US3] In `waypoint_monitor/app/domain/flow.py` parse declarations per step into `FlowStep.metrics` with the constraints of T029 (reuse `_label` for label and unit, a `_threshold(value)` helper accepting finite non-bool numbers), report dropped ones in `problems`, and carry `metrics` through `_drop_cycles` when it rebuilds `FlowStep`. Make T029 pass
- [X] T036 [US3] In `waypoint_monitor/app/domain/metrics.py` extend `step_metrics` with the declarations of the step (`FlowStep.metrics`): declared first in declared order with `value: null` when not reported, `label`, `unit`, `declared: true`; compute `flag` (strict comparisons); add `count_over(metrics) -> int`. Make T030 pass
- [X] T037 [US3] In `waypoint_monitor/app/domain/analysis.py` pass each planned step's `MetricDecl` tuple into `step_metrics`, set the step's `metrics_over`, sum to the run's `metrics_over`, add `metrics` (declarations) to `_flow_json` per step (omit when empty; absent keys null), and make a declared-but-never-recorded metric appear only for steps that have begun. Make T031 pass
- [X] T038 [US3] Front end: `waypoint_monitor/static/js/api.js` maps `flow.steps[].metrics` into the run's `defs[i].metrics` and step `metricsOver`; `waypoint_monitor/static/js/model.js` adds `metricsOver(step)` and `flagText(flag, decl)`; `waypoint_monitor/static/js/ui.js` adds `metricBadgeHTML(n)` (warning icon plus `1 metric over limit` / `N metrics over limit`, `title` and accessible text, not colour alone) and extends `metricsTableHTML` with a flag cell (icon plus `above 100` / `below 90`) and the unit after the value; render the badge in the step card header in `waypoint_monitor/static/js/views/step.js` and on the node in `waypoint_monitor/static/js/views/graph.js` (beside the existing bottleneck marker at line ~107, included in the node's aria-label); add `.xmetric__flag` and badge styles to `waypoint_monitor/static/styles.css` with a distinct shape in both light and dark themes. Make T032 pass

**Checkpoint**: declarations, flags and badges work; US1/US2 still pass.

---

## Phase 6: User Story 4 - Watch a metric trend across runs (Priority: P3)

**Goal**: History shows a declared metric's value per run with the median and the threshold.

**Independent Test**: Ten runs recording `rejected` with rising values; History shows ten points in order, the median, and the threshold line; runs that did not report it are gaps; fewer than the minimum runs shows points but no median; no declarations means no card.

- [X] T039 [P] [US4] Write failing tests in `waypoint_monitor/static/tests/metrics.test.mjs` for `metricTrend(runs, stepName, metricName, window, minRuns)` (runs newest first, as the History view receives them): `points` oldest to newest with `value` or null for runs that did not report; `median` over the newest `window` reported values (even count averages the middle two) only when at least `minRuns` reported, else null; `warnAbove`, `warnBelow`, `unit`, `label` come from the newest run's declaration; a metric undeclared in the newest run falls back to the newest run that declares it; `trendMetricChoices(runs)` lists `{step, metrics:[{name,label}]}` only for steps that declare a metric in any shown run, in the newest run's step order; returns empty when nothing is declared
- [X] T040 [P] [US4] Add a view test in `waypoint_monitor/static/tests/state.test.mjs` (or a new `history-metrics.test.mjs`) that `renderHistory` shows the Metric trend card with step and metric selects only when choices exist, shows no card otherwise, and that changing the step select repopulates the metric select
- [X] T041 [US4] Implement `metricTrend` and `trendMetricChoices` in `waypoint_monitor/static/js/model.js`. Make T039 pass
- [X] T042 [US4] In `waypoint_monitor/static/js/api.js::loadConfig` also map `durationWindowRuns: c.duration_window_runs || 30` (the median window), and pass `cfg` through where History already receives it. Add a case to the config mapping test
- [X] T043 [US4] In `waypoint_monitor/static/js/chart.js` add `drawMetricTrend(box, statEl, tip, trend)` reusing the existing line-chart helpers used by `drawTrend` and `drawDuration`: points oldest to newest, gaps for null, a dashed median line when `trend.median != null`, one threshold line per declared limit with a text label, a distinct marker shape (diamond, as the slow runs use) for points over a threshold, a tooltip with run time, value and unit, keyboard arrow navigation like the other charts, and an `aria-label` summarising the series
- [X] T044 [US4] In `waypoint_monitor/static/js/views/history.js` add the **Metric trend** card after the Step trend card (markup per `contracts/ui.md`: step select, metric select, chart box, small legend) only when `trendMetricChoices(runs)` is non-empty; keep the chosen step and metric in module state like `trendStep`, repopulate the metric select on step change, and redraw from `redrawTrend`. Add the needed styles to `waypoint_monitor/static/styles.css`. Make T040 pass

**Checkpoint**: all four stories work independently.

---

## Phase 7: Polish & cross-cutting

- [X] T045 [P] Regression tests for old data in `waypoint_monitor/tests/test_analysis.py` and `waypoint_monitor/static/tests/run-view.test.mjs`: every existing fixture (library 0.2.0, 0.3.0 and 0.4.0 shaped runs, with and without flows) produces identical output to before apart from the added `metrics_over: 0` (FR-021, SC-007); and a run written by library 0.5.0 read by the previous `parse_flow` (simulate by a flow dict with `metrics`) still parses
- [X] T046 [P] Extend `waypoint_monitor/tests/seed_demo.py` with sample data: a step with undeclared metrics, a step with a declared metric under its limit, over its limit, and declared but not reported, and a pipeline with 12 runs of rising `rejected` values so History shows a trend and a median
- [X] T047 [P] Update documentation: `packages/waypoint_etl/README.md` (the `metric()` call and modes, `Metric` declaration with an example, limits, "merged per process", delivery within about a second, no new Redis permission), `waypoint_monitor/README.md` (Metrics block, badge, History trend, no new permission or setting), the root `README.md` feature list, and `.claude/skills/adopting-waypoint-etl/SKILL.md` (a short "optional metrics" section after the events one)
- [X] T048 (version bumped; install URLs and the `waypoint-etl-v0.4.0` tag mentions in `README.md` and `deploy/README.md` are left until the `v0.5.0` tag exists) Bump `packages/waypoint_etl/pyproject.toml` version and `packages/waypoint_etl/src/waypoint_etl/__init__.py` `__version__` to `0.5.0`; update the install URL/version mentions in `README.md` and `deploy/README.md` where `0.4.0` appears; update `packages/waypoint_etl/tests/test_init.py` if it asserts the version
- [X] T049 Mark roadmap item 5 done in `specs/roadmap.md` (table row ✅, tick the checkboxes of section 5, and mark decision 8 "✅ Đã quyết định (spec 013): key riêng theo từng lần chạy của step"), and note in `specs/013-step-metrics/spec.md` header `Status: Done - released in waypoint-etl 0.5.0`
- [X] T050 Run the full verification: in `packages/waypoint_etl` and `waypoint_monitor` run `python -m unittest discover tests`, `mypy --strict`, `ruff check .`, `black --check .`; in `waypoint_monitor` run `node --test static/tests/*.test.mjs`; then follow `specs/013-step-metrics/quickstart.md` sections 2 and 3 by hand (live run, trend, Redis down, library 0.4.0 data) and record results and the new pass counts in the quickstart. Do not mark the feature done until each command's real output has been read

---

## Dependencies and order

- Phase 1 then Phase 2 (T003 through T008) block everything. T003 is library-only; T004-T008 are monitor-only, so the two halves can proceed in parallel.
- **US1** (T009-T023) needs Phase 2. Library chain: T014 → T015 → T016 → T017. Monitor chain: T018 → T019 → T020. Front end: T021 → T022 → T023. The three chains are independent until the end-to-end check.
- **US2** (T024-T027) needs T014-T016 (it fills in the other two modes) and is otherwise independent of the monitor.
- **US3** (T028-T038) needs US1 (it extends `step_metrics`, `analysis`, `stepItemHTML`). Library (T033, T034) and monitor (T035-T037) halves are independent; T038 needs T037.
- **US4** (T039-T044) needs US3 (declarations) and T042; it does not touch the library.
- Polish (T045-T050) after the stories; T048 and T049 after everything is verified (T050 last).

## Parallel examples

- Foundational: T003 (library) with T004, T005, T007 (monitor) at the same time; T006 after T005; T008 after T007.
- US1 tests: T009, T010, T011, T012, T013 are all different files and can be written together.
- US3 tests: T028, T029, T030, T031, T032 together; then T033/T034 (library) and T035-T037 (monitor) as two parallel lanes.

## Implementation strategy

- **MVP = Phase 1 + 2 + US1 (+ US2 for the other modes, which is small)**: a pipeline can send numbers and the operator sees them live and after. Demo-able without declarations.
- Then US3 (thresholds and badges; the attention signal), then US4 (trend).
- Ship order: monitor first (it works with no pipeline change and ignores unknown flow fields), then the library `0.5.0`.
