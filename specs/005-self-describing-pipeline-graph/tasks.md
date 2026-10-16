---

description: "Task list for Self-Describing Pipeline Graph"
---

# Tasks: Self-Describing Pipeline Graph

**Input**: `/specs/005-self-describing-pipeline-graph/` (spec, plan, research, data-model, contracts/redis-keys.md, contracts/api.md, quickstart.md)

**Tests**: Included. Constitution principle IV requires tests for changed behaviour; no live Redis, CallRail or Google Ads calls in tests.

**Organization**: Grouped by user story. Paths are relative to `integrations/callraill/`; **MONITOR** = `performance_monitoring_app/`. Run pipeline checks from `integrations/callraill` (`python -m unittest discover tests`, `black --check .`, `ruff check .`, `mypy .`), monitor checks from `performance_monitoring_app` (`python -m unittest discover tests`, `node --test static/tests`).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Rewrite the fake store in `performance_monitoring_app/tests/fakes.py` for the new layout: `FakeStore` holds raw `(key, json)` pairs; methods `list_pipelines(env)`, `list_flows(env, pipeline)`, `list_records(env, pipeline)`, `list_markers(env, pipeline)`, `ping()` (each raises `StoreUnavailable` when `fail`). Add builders `make_flow(pipeline, env, run_id, steps, groups=None, v=1)`, `make_record(pipeline, env, run_id, index, step, inputs, output, finished_at)` and `make_marker(pipeline, env, run_id, index, step, started_at)` that emit keys exactly per `contracts/redis-keys.md` (`etl-audit:{pipeline}:{env}:{run_id}:flow|step:NN-step|running:NN-step`) and records with the added `"pipeline"` field. Keep a `callrail_flow()` helper returning the nine-step flow used by existing analysis tests

## Phase 2: Foundational (key layout, spec model, flow parsing; blocks all stories)

**Purpose**: the pipeline can declare and write a flow, and the monitor can read keys, discover pipelines and parse a flow. No UI yet.

### Pipeline side

- [X] T002 In `src/application/step_audit.py` add frozen dataclasses `GroupSpec(key, label)`, `StepSpec(name, inputs, label=None, group=None, returns_nothing=False, col=None, row=None)` with `inputs: Tuple[Tuple[str, str], ...]` of `(input name, producing step)`, and `PipelineSpec(name, steps, label=None, groups=())`, plus `validate_spec(spec) -> None` raising `ValueError` with a message naming the problem. Rules, quoted from data-model.md: pipeline name `[a-z0-9][a-z0-9_-]{0,39}`; label ≤60 chars; steps ≥1, ≤100; step name unique, `[a-z0-9_]+`, ≤64; step label ≤40 chars; `group` must be a key of a declared group; each input's `from` must be another step of the spec declared earlier; `col`, `row` ≥0. Keep the module free of any CallRail import
- [X] T003 In `src/application/step_audit.py` replace `KEY_PREFIX`/`START_KEY_PREFIX` with key helpers per `contracts/redis-keys.md`: `ROOT = "etl-audit"`, `flow_key(pipeline, env, run_id)`, `step_key(pipeline, env, run_id, index, step)`, `marker_key(...)` (`{ROOT}:{pipeline}:{env}:{run_id}:flow|step:{NN:02d}-{step}|running:{NN:02d}-{step}`). Change `StepAuditor.__init__` to `(store, spec, env, ttl_seconds, run_id=None)`; add `start()` that writes the flow value `{"v": 1, "pipeline", "env", "run_id", "label", "groups", "steps": [{name, label, group, inputs: [{name, from}], returns_nothing, col, row}]}` (omit `None` optionals) with the finish-record TTL, inside its own try/except printing `Warning: step audit flow failed: {exc}`; `run()` calls `start()` first if it has not run. Add `"pipeline"` to both the marker and the finish record. A step name not in the spec logs `Warning: step {name} is not in pipeline spec {spec.name}` and still runs unrecorded for flow purposes (never raises). If `validate_spec` fails in `__init__`, print a warning and write no flow; the pipeline still runs. Labels and names come only from the spec, never from data
- [X] T004 [P] Update `tests/application/test_step_audit.py`: adapt existing tests to the new constructor and keys (finish records under `etl-audit:...:step:`, markers under `...:running:`, TTLs unchanged: marker 86400, records `ttl_seconds`). Add tests: `validate_spec` accepts a valid spec and rejects each rule above (bad name, duplicate step, input from unknown or later step, unknown group, empty steps, over-long label, negative `row`); `start()` writes the flow JSON with the exact fields and `v == 1`, TTL = `ttl_seconds`, before any marker; flow written only once per auditor; a store that raises on the flow write still runs steps; an invalid spec runs steps and writes no flow; unknown step name logs and still returns `fn`'s result; no field in any written value contains an input item (counts only)
- [X] T005 Create `src/application/pipeline_spec.py` with `CALLRAIL_PIPELINE = PipelineSpec(name="callrail", label="CallRail", groups=(callrail, gads, merge, persist) labelled `CallRail`, `Google Ads`, `Merge`, `Persist`, steps=...)` for the nine steps of `performance_monitoring_app/app/domain/steps.py` (same names, inputs, producers, `returns_nothing` on the two persist steps) with friendly labels (`Accounts`, `Calls`, `Partners`, `Instances`, `Campaigns`, `Click views`, `Merged calls`, `Record stats`, `Save stats`) and the group of each step. Do not add `col`/`row` hints (auto layout is the reference case)
- [X] T006 Wire the spec: in `src/application/application.py` and wherever `StepAuditor(` is constructed (grep `StepAuditor(`; likely `main.py`) pass `CALLRAIL_PIPELINE` and call `self.auditor.start()` as the first statement of `run_pipeline`'s `try`. The default no-op auditor in `Application.__init__` takes the spec too
- [X] T007 [P] Add `tests/application/test_pipeline_spec.py`: `validate_spec(CALLRAIL_PIPELINE)` passes; running `Application.run_pipeline` with mock use cases and a fake store records exactly the step names declared in the spec, in the same order (so the spec cannot drift from the `audit(...)` calls); a flow key exists before the first marker. Update `tests/application/test_application.py` for the changed constructor

### Monitor side

- [X] T008 In `performance_monitoring_app/app/domain/models.py` add `pipeline: str` to `StepRecord` and `StartMarker`; add frozen dataclasses `GroupDef(key, label)`, `FlowStep(name, label, group, inputs, returns_nothing, col, row)` (replacing `StepDefinition`) and `Flow(pipeline, label, groups, steps, problems)`; `problems: Tuple[str, ...]`
- [X] T009 Create `performance_monitoring_app/app/domain/flow.py` with `parse_flow(pipeline, env, run_id, raw) -> Tuple[str, Optional[Flow]]` returning status `"ok"`, `"invalid"` (not JSON, not an object, `v` not 1, no valid steps, `pipeline`/`env`/`run_id` not equal to the key's) or `"ok"` with `problems` for dropped parts. Keep the valid part: drop a step with a bad or duplicate name, keep an input whose `from` names an unknown step but add `"input 'x' of 'b' names unknown step 'z'"` to `problems` and mark it dangling, flag a cycle in `problems` (drop the closing edge), truncate label to 40 chars and flow label to 60, ignore unknown fields, cap at 100 steps. Never raises
- [X] T010 [P] Add `performance_monitoring_app/tests/test_flow.py` covering: valid flow; unknown `v` -> invalid; non-JSON -> invalid; empty steps -> invalid; key/value mismatch -> invalid; dangling input kept and reported; cycle reported and rendered acyclic; duplicate step dropped; long label truncated; unknown fields ignored; 100+ steps capped
- [X] T011 Rewrite `performance_monitoring_app/app/domain/parsing.py` for the new keys: regexes `^etl-audit:(?P<pipeline>[a-z0-9][a-z0-9_-]{0,39}):(?P<env>[^:]+):(?P<run>\d{8}T\d{6}Z):step:(?P<idx>\d{2,})-(?P<step>.+)$` (and `running`, `flow` variants); remove the `STEP_NAMES` whitelist and the import of `app.domain.steps`; records/markers must now also carry `pipeline` equal to the key's; `parse_records(env, pipeline, raw)`, `parse_markers(env, pipeline, raw)` keep their never-raise behaviour; keys in the old `callrail:audit:`/`callrail:running:` layout match no regex and are skipped without being counted as unreadable (FR-014). Add `pipeline_from_flow_key(key) -> Optional[str]`
- [X] T012 [P] Update `performance_monitoring_app/tests/test_parsing.py`: new-key records and markers parsed; wrong env/pipeline/run id/index/time dropped; step names are no longer whitelisted; old-layout keys ignored and not counted unreadable; a pipeline name with a colon or uppercase is rejected
- [X] T013 Change the `RecordStore` protocol in `performance_monitoring_app/app/infrastructure/store.py` to `list_pipelines(env) -> List[str]`, `list_flows(env, pipeline) -> List[Tuple[str, str]]`, `list_records(env, pipeline)`, `list_markers(env, pipeline)`, `ping()`, and implement them in `app/infrastructure/redis_store.py`: `list_pipelines` = `SCAN etl-audit:*:{env}:*:flow` and collect the pipeline segment (dedup, sorted); the others `SCAN etl-audit:{pipeline}:{env}:*:flow|step:*|running:*` with the existing batched `mget`; map `redis.RedisError` to `StoreUnavailable`; still read-only (only `SCAN`, `MGET`, `PING`)
- [X] T014 [P] Update `performance_monitoring_app/tests/test_redis_store.py` for the four new methods (pairs returned, expired `None` skipped, pipeline dedup, `RedisError` wrapped, no write commands issued)

**Checkpoint**: `python -m unittest discover tests` passes in both projects (monitor analysis/API tests are expected red until Phase 3 lands; mark them skipped only if blocking).

## Phase 3: User Story 1 - Graph is drawn from what a run records (P1) 🎯 MVP

**Goal**: any pipeline's graph (nodes, arrows with counts, groups, labels, order) comes only from the stored flow.

**Independent Test**: store a run for a made-up pipeline (steps the monitor has never seen); open the monitor: full graph appears with no monitor change. Rename a CallRail step, run, and see the change.

- [X] T015 [US1] In `performance_monitoring_app/app/domain/analysis.py` change `build_runs(parsed, env, pipeline, now, stale_hours, flows, markers, stall_seconds)` so each run's step list comes from its own flow (`flows: Dict[run_id, Tuple[status, Optional[Flow]]]`), not `EXPECTED_STEPS`: `_ordered_inputs` uses the flow step's inputs; step states `done`, `running`, `stalled`, `waiting`, `missing` as today, evaluated in the flow's step order; each run gets `pipeline`, `flow_status`, `flow_problems`, and `flow` (label, groups, steps with name/label/group/inputs[name,from]/returns_nothing/col/row) per `contracts/api.md`; existing run-level fields unchanged. Each run uses only its own flow (no comparison with other runs)
- [X] T016 [US1] Delete `performance_monitoring_app/app/domain/steps.py` and every import of `EXPECTED_STEPS`/`STEP_NAMES`; remove `expected_steps` from `/api/config` in `app/api/routes.py`; change `/api/runs` to require `pipeline` (validated against `^[a-z0-9][a-z0-9_-]{0,39}$`, else 400), read flows/records/markers for `(env, pipeline)` in one cached window keyed by `(env, pipeline)`, and pass them to `build_runs`
- [X] T017 [P] [US1] Update `performance_monitoring_app/tests/test_analysis.py` and `tests/test_api.py` to the new signatures using `callrail_flow()`: the nine-step results match the previous expectations; a made-up pipeline `demo` with steps `a -> b -> c` yields three nodes with the declared labels and groups; renaming a step in the flow changes the response with no code change; `/api/config` has no `expected_steps`; `/api/runs` without `pipeline` or with a bad name is 400
- [X] T018 [US1] In `performance_monitoring_app/static/js/api.js` drop `c.expected_steps` from `loadConfig`; make `loadRuns(env, pipeline)` pass `pipeline` and map each run's `flow` (label, groups, steps) and `flowStatus`/`flowProblems`; each run now carries its own `steps` definitions, so `model.js`/`ui.js` read names, labels and groups from the run, not from config
- [X] T019 [US1] Replace the `POSITIONS`/`GROUP_NAME` tables in `performance_monitoring_app/static/js/graph-model.js` with a generic layout engine `computeLayout(flowSteps, edges)` per research R5: layer = longest path from sources over hand-off edges (cycle edges dropped), rows within a layer ordered by barycenter of producers, ties by declared order; optional `col`/`row` hints override; return `{col, row, lane, layer, order}` per step. Remove `partition`'s "Other steps" split (every flow step is placed; only `unplanned` steps from US3 go to "Other steps"). Update `edgesOf`, `layoutLR`, `layoutTB`, `readingOrder` to use the computed layout, delete the hardcoded step-name checks (`read_instances`, `read_campaigns`, `read_gads_clickview`, merge special cases) and generalise: an edge spanning more than one layer runs through its source row and bends only in the last gap; chips on edges sharing a gap are staggered by edge index; group bands only for groups whose steps occupy contiguous layers, otherwise colour/tag only
- [X] T020 [P] [US1] Add `performance_monitoring_app/static/tests/layout.test.mjs`: linear chain, fan-out, fan-in (the CallRail shape), skip edge, cycle input (no infinite loop), hints override, 50-step graph lays out in under 100 ms and produces no overlapping node rectangles; update `static/tests/graph-model.test.mjs` for removed tables
- [X] T021 [US1] In `performance_monitoring_app/static/js/ui.js` and `app.js` take node label, group tag and colour from the run's flow groups (colour assigned by group order from a fixed palette in `static/styles.css`); remove any use of the old `GROUP_NAME`; rerender when the selected run's flow differs (signature includes flow steps)
- [X] T022 [US1] Update `performance_monitoring_app/README.md` sections "Steps view" and "What it reads" for the new graph source and keys (no more "add a row in graph-model.js"), and the config table is unchanged (no new variable)

**Checkpoint**: CallRail run in QA shows the same nine-step graph from stored data; a hand-written `demo` flow renders with no monitor edit.

## Phase 4: User Story 2 - A new pipeline adopts the audit and monitor (P1)

**Goal**: another pipeline declares its steps once and appears in the monitor beside CallRail, never mixed.

**Independent Test**: wire a three-step sample pipeline to the shared facility, run it, see it in the monitor picker with a correct graph.

- [X] T023 [US2] Add `GET /api/pipelines?env=` to `performance_monitoring_app/app/api/routes.py` per `contracts/api.md`: names from `store.list_pipelines(env)`, `label` and `last_run_id` from the newest flow of each (fall back to name / newest record run id), sorted by `last_run_id` desc; 400 for unknown env, 503 `Data store unavailable` on `StoreUnavailable`; cached with the same window
- [X] T024 [P] [US2] Add API tests in `performance_monitoring_app/tests/test_api.py`: two pipelines (`callrail`, `demo`) in one fake store: `/api/pipelines` lists both; `/api/runs?pipeline=demo` contains only demo runs/steps/counts, same step name in both pipelines never mixes (SC-003); old-layout keys add no pipeline; 503 and 400 cases
- [X] T025 [US2] Add a pipeline picker to `performance_monitoring_app/static/index.html`, `static/js/api.js` (`loadPipelines(env)`) and `static/js/app.js`: next to the environment switcher, options from `/api/pipelines`, selection remembered in `localStorage['pm-pipeline']` (try/catch around storage), default = first pipeline; changing env or pipeline reloads runs; if the remembered pipeline no longer exists fall back to the first; if there are none show an empty state "No pipelines have reported to this environment"
- [X] T026 [P] [US2] Add `performance_monitoring_app/static/tests/picker.test.mjs` for the pure selection rule (remembered missing -> first, none -> empty state) extracted into `static/js/model.js` as `choosePipeline(list, remembered)`
- [X] T027 [US2] Add a second sample pipeline as an adoption proof: `tests/application/test_second_pipeline.py` defines a three-step `PipelineSpec(name="sample", ...)`, runs it through `StepAuditor` against a fake store and asserts the keys written under `etl-audit:sample:...` match `contracts/redis-keys.md` and contain no CallRail names; it imports only `src/application/step_audit.py` (guards that the facility stays copyable)
- [X] T028 [US2] Add `performance_monitoring_app/tests/seed_demo.py` (a small script, not a test) that writes the `demo` flow, records and markers from quickstart step 2 into a Redis given by `REDIS_URL`, and prints the keys it wrote
- [X] T029 [US2] Document adoption in `README.MD` (pipeline) and `performance_monitoring_app/README.md`: "Add a pipeline" steps (declare `PipelineSpec`, build `StepAuditor`, call `start()`, wrap steps with `audit(...)`), the key layout, and a link to `specs/005-self-describing-pipeline-graph/contracts/redis-keys.md`. Constitution: new settings must be documented; none are added, state that explicitly

**Checkpoint**: both pipelines appear and stay separate; the sample pipeline test passes without touching the monitor.

## Phase 5: User Story 3 - Not-yet-run and failed steps still appear (P2)

**Goal**: a run that stops partway still shows the whole planned flow with the stopping point.

**Independent Test**: six-step flow, records for three steps: six nodes, last three not reached.

- [X] T030 [US3] In `performance_monitoring_app/app/domain/analysis.py` add state `unplanned` for a record or marker whose step name is not in the run's flow: kept after the planned steps in `index` order, never counted in `missing_count`, `first_missing_step` or `loss_steps`; a run whose flow exists but has no records yet shows every planned step `waiting`/`missing` per the existing rules and exists as a run
- [X] T031 [P] [US3] Add analysis tests in `performance_monitoring_app/tests/test_analysis.py`: six planned steps with three finished -> remaining three `missing`, `first_missing_step` correct, `status == "incomplete"`; flow only (run just started) -> run present, all planned steps present; an unplanned recorded step is `unplanned` and not counted missing; a planned step with a running marker and later steps `waiting`
- [X] T032 [US3] In `performance_monitoring_app/static/js/graph-model.js`, `model.js` and `ui.js` render `unplanned` steps in an "Other steps" strip under the graph (reusing the existing section) with a visible "not in this run's flow" tag, and keep `missing`/`waiting` node styling as today
- [X] T033 [P] [US3] Add `performance_monitoring_app/static/tests/state.test.mjs` cases for `unplanned` (not an edge endpoint, not counted as missing, listed in reading order after planned steps)

## Phase 6: User Story 4 - Bad or missing descriptions never break the page (P2)

**Goal**: a run with no flow, or a malformed one, opens without error and says what is wrong.

**Independent Test**: one run with records but no flow key, one with a malformed flow: both open, with a visible explanation.

- [X] T034 [US4] In `performance_monitoring_app/app/domain/analysis.py` when a run has no usable flow (`flow_status` `"missing"` or `"invalid"`) build `steps` from the records and markers in `index` order (state as today; no inputs from the flow, so only the record's own input counts are listed), set `flow` to `null`, and keep run-level fields working (`first_missing_step` = `None`, since nothing is planned). Do not read or keep any built-in step list (FR-008)
- [X] T035 [P] [US4] Add tests in `performance_monitoring_app/tests/test_analysis.py` and `tests/test_api.py`: records without a flow key -> `flow_status == "missing"`, steps in index order, no exception; invalid flow (`v: 9`, non-JSON) -> `"invalid"`, same fallback; partially valid flow (dangling input, cycle) -> `"ok"` with `flow_problems` and the valid part drawn; a run key with a flow but no records -> shown
- [X] T036 [US4] In `performance_monitoring_app/static/js/graph-model.js` and `ui.js` draw the simplified graph when `flow` is `null`: nodes in a single row (wrap at the panel width), no arrows, count shown on each node, and a banner "No flow description for this run, showing steps in the order they reported" (or "Flow description unreadable" for `invalid`); show `flowProblems` for a partly valid flow in a collapsible "Problems in this run's description (n)" under the graph. All text set via `textContent` (never `innerHTML`) so stored labels cannot inject markup
- [X] T037 [P] [US4] Add `performance_monitoring_app/static/tests/simplified.test.mjs`: layout for `flow == null` has no edges and one node per step; problems list rendered escaped (a label containing `<script>` stays text); a dangling input is drawn as a flagged edge stub, not a crash

## Phase 7: Polish & Cross-Cutting

- [X] T038 [P] Add a 30-step sample flow fixture to `performance_monitoring_app/static/tests/layout.test.mjs` and verify no overlapping nodes or edge/node crossings through node centres (SC-006); record the figure and date in `research.md` R5
- [X] T039 [P] Update `specs/001-pipeline-step-audit/contracts/step-record.md` and `specs/004-step-running-indicator/contracts/start-marker.md` with a "Superseded key layout: see 005 contracts/redis-keys.md" note; do not rewrite history
- [X] T040 Run `black .`, `ruff check .`, `mypy .` and `python -m unittest discover tests` in `integrations/callraill`; `python -m unittest discover tests`, `node --test static/tests` and the same linters in `performance_monitoring_app`; fix findings
- [X] T041 Run the quickstart (`specs/005-self-describing-pipeline-graph/quickstart.md`) steps 2-5 against a local Redis, including the real CallRail job on QA and the step-rename check (SC-001); record the date and result at the bottom of `quickstart.md`
- [X] T042 Review stored keys from a QA run (`redis-cli --scan --pattern 'etl-audit:*'` then `GET` a flow, step and marker): confirm no item contents or caller data appear (SC-007, constitution II); note the outcome in the PR description

## Dependencies & Execution Order

- Phase 1 -> Phase 2 -> Phases 3-6 -> Phase 7.
- Phase 2: T002 -> T003 -> T004/T005; T005 -> T006 -> T007. Monitor side T008 -> T009 (T010 parallel), T011 (T012 parallel), T013 (T014 parallel). Pipeline side and monitor side are independent until the quickstart.
- US1 (P1) is the MVP and blocks the others (they extend `build_runs`, the API and the layout). US2 needs T016. US3 and US4 each need T015-T016 and can run in parallel after US1; both touch `analysis.py` and `graph-model.js`, so merge T030 before T034.
- Within a story: tests before or alongside the code they cover; `[P]` tasks touch different files.

### Parallel examples

- After T003: T004 and T005 in parallel (different files).
- Phase 2 monitor side while pipeline side is in progress: T008-T014 touch only `performance_monitoring_app/`.
- US1: T017 (Python tests), T020 (JS layout tests) and T022 (README) in parallel once T015, T019 land.
- US3 and US4 after US1: T031 and T035 (tests) in parallel; T032 and T036 (UI) in parallel if T030/T034 are merged.

## Implementation Strategy

1. **MVP**: Phases 1-3 (US1). CallRail declares itself, the monitor draws from stored flow, hardcoded list gone. Validate with quickstart steps 2 and 5.
2. Add US2 (picker + second pipeline), then US3 and US4 in either order.
3. Finish with Phase 7. Deploy order: pipeline first (writes new keys), monitor second; until both are live the monitor shows the empty state, which is acceptable since old data is deleted (spec FR-014).
