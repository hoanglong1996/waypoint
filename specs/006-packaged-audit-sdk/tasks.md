---

description: "Task list for Packaged Pipeline Monitoring Product"
---

# Tasks: Packaged Pipeline Monitoring Product

**Input**: Design documents from `/specs/006-packaged-audit-sdk/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/library-api.md, quickstart.md

**Tests**: Included. Constitution principle IV requires tests for changed behaviour; no live Redis, CallRail, Google Ads or Sentry in tests (use the fake store pattern from `tests/application/test_second_pipeline.py`).

**Organization**: grouped by user story. All paths are relative to `integrations/callraill/`. Library code goes under `packages/step_audit/src/step_audit/`, tests under `packages/step_audit/tests/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 adopt with minimal edits · US2 one-place config · US3 deploy together · US4 CallRail migrated

## Phase 1: Setup

- [X] T001 Create `packages/step_audit/pyproject.toml` (distribution `etl-step-audit`, version `0.1.0`, `src/` layout, optional extra `redis` = `redis==5.0.8`, `requires-python >=3.10`, `mypy --strict`, ruff and black line length 100 config) and empty `packages/step_audit/src/step_audit/py.typed`
- [X] T002 [P] Create `packages/step_audit/README.md` stub and `packages/step_audit/tests/__init__.py`
- [X] T003 [P] Create `deploy/` directory with `deploy/README.md` stub

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: move the existing audit code into the package unchanged in behaviour, split into the modules named in plan.md.

- [X] T004 [P] Create `packages/step_audit/src/step_audit/spec.py` with `GroupSpec`, `StepSpec`, `PipelineSpec`, `validate_spec` and the limits (`MAX_STEPS = 100`, `MAX_PIPELINE_LABEL = 60`, `MAX_STEP_LABEL = 40`), moved from `src/application/step_audit.py`. Keep the rules verbatim: pipeline name `^[a-z0-9][a-z0-9_-]{0,39}$`, step name `^[a-z0-9_]{1,64}$`, 1–100 steps, producer must be an earlier step, group must be declared, `col`/`row` >= 0
- [X] T005 [P] Create `packages/step_audit/src/step_audit/keys.py` with `ROOT = "etl-audit"`, `FLOW_VERSION = 1`, `START_MARKER_TTL_SECONDS = 86400`, `flow_key`, `step_key`, `marker_key` (formats must stay byte-identical to `specs/005-self-describing-pipeline-graph/contracts/redis-keys.md`)
- [X] T006 [P] Create `packages/step_audit/src/step_audit/stores.py` with the `StepAuditStore` Protocol, `NoopStepAuditStore`, and `RedisStepAuditStore` (moved from `src/infrastructure/audit/redis_step_audit.py`; `redis` imported lazily inside `__init__` so the package imports without the extra; keep `socket_connect_timeout=2, socket_timeout=2`)
- [X] T007 Create `packages/step_audit/src/step_audit/auditor.py` with `StepAuditor`, `count_items`, `_flow_value`, moved from `src/application/step_audit.py`, importing from `spec.py`, `keys.py`, `stores.py` (depends on T004–T006). Keep the docstring rule: only names and counts, never item contents
- [X] T008 [P] Move the existing tests into the package: `tests/application/test_step_audit.py` → `packages/step_audit/tests/test_auditor.py`, `tests/application/test_pipeline_spec.py` spec-validation cases → `packages/step_audit/tests/test_spec.py`, `tests/application/test_second_pipeline.py` → `packages/step_audit/tests/test_second_pipeline.py`, `tests/infrastructure/audit/test_redis_step_audit.py` → `packages/step_audit/tests/test_stores.py`; fix imports to `step_audit.*`. Leave the CallRail-specific spec-vs-steps test in place for now (US4)
- [X] T009 Run `pip install -e "packages/step_audit[redis]"` then `python -m unittest discover packages/step_audit/tests`; all moved tests must pass before continuing

**Checkpoint**: package exists, behaviour identical to today, old `src/` copy still in place.

---

## Phase 3: User Story 1 - Adopt with minimal edits (P1) 🎯 MVP

**Goal**: marking a step with one decorator line is enough; calling code is untouched.

**Independent Test**: `packages/step_audit/examples/sample_pipeline.py` has no audit code in its orchestration function and still writes flow, markers and records (quickstart step 2).

### Tests

- [X] T010 [P] [US1] Create `packages/step_audit/tests/test_decorator.py` covering: decorated function returns the same value; `functools.wraps` keeps `__name__`/signature; exceptions propagate and no finish record is written; marker written before and record after; input counts come from parameter names (None→None, list→len, other→1); a parameter not in the step's spec inputs is ignored; `inputs={"param": "input_name"}` renames; methods work (`self` skipped); `async def` steps work; a step name missing from the spec is still recorded after a warning; no item contents appear in `repr(store.writes)`
- [X] T011 [P] [US1] Create `packages/step_audit/tests/test_unconfigured.py`: with no `init` call, a decorated step behaves as undecorated and nothing is written; with a store whose `write` raises, the step result is identical and only a warning is printed (FR-009, SC-003)

### Implementation

- [X] T012 [US1] Create `packages/step_audit/src/step_audit/registry.py` holding the active `StepAuditor | None` with `get_active()`, `set_active()`, `clear()` (module-level state per data-model.md)
- [X] T013 [US1] Create `packages/step_audit/src/step_audit/decorator.py`: `audited_step(name, inputs=None)` using `ParamSpec`/`TypeVar` so signatures stay typed. Detect coroutine functions and return an async wrapper. Bind args with `inspect.signature(fn).bind`, drop `self`/`cls`, map to input counts. Call `registry.get_active()` at call time; if `None`, return `fn(*args, **kwargs)` directly. Delegate to a new `StepAuditor.run_bound(name, call, input_values)` (add to `auditor.py`) that keeps the existing record format and swallow-store-errors behaviour
- [X] T014 [US1] Add `step_audit.wrap(obj, method_name, *, step, inputs=None)` in `packages/step_audit/src/step_audit/decorator.py` (fallback from contracts/library-api.md) and a test in `packages/step_audit/tests/test_decorator.py`
- [X] T015 [US1] Create `packages/step_audit/src/step_audit/testing.py` with `assert_spec_matches(spec, *objects)` (fails on a decorated step missing from the spec or a spec step with no decorated function); decorator must tag wrapped functions with a `__audited_step__` attribute so this can find them; add a test
- [X] T016 [US1] Create `packages/step_audit/examples/sample_pipeline.py`: a 3-step pipeline (`extract` → `clean` → `load`, `load` with `returns_nothing=True`), one `init(...)` block reading `REDIS_URL` from the environment, three `@audited_step` lines, and an orchestration function containing no audit code

**Checkpoint**: US1 passes tests and quickstart step 2 on its own.

---

## Phase 4: User Story 2 - One-place configuration (P1)

**Goal**: pipeline name, label, Redis URL, env and TTL are set in one `init(...)` call in `main.py`.

**Independent Test**: change only the `init` values and records appear under the new name/address (quickstart step 2 with a different name).

- [X] T017 [P] [US2] Create `packages/step_audit/tests/test_init.py` covering: valid init returns `True` and registers an auditor; invalid spec returns `False` with a printed warning and leaves the registry empty; empty `redis_url` returns `False` (no-op store, pipeline unaudited); malformed `redis_url` returns `False` with a warning and does not raise; second `init` replaces the first and prints a warning; keys use `pipeline.name`, `env` and the given or generated `run_id`; `ttl_days` is converted to seconds (default 7)
- [X] T018 [US2] Create `packages/step_audit/src/step_audit/__init__.py` exporting `init`, `audited_step`, `wrap`, `PipelineSpec`, `StepSpec`, `GroupSpec`, `FLOW_VERSION`, `__version__ = "0.1.0"`, and implement `init(*, pipeline, redis_url, env, ttl_days=7, run_id=None) -> bool` in `packages/step_audit/src/step_audit/registry.py` per `contracts/library-api.md`. `init` must call `auditor.start()` so the flow description is stored once per run and must never raise
- [X] T019 [US2] Document in `packages/step_audit/README.md` the full adoption steps (install, declare `PipelineSpec`, `init` in `main.py`, decorate steps, `assert_spec_matches` test), the sequential-steps limitation, the PII rule, and the `wrap` fallback (FR-014)

**Checkpoint**: US1 + US2 together deliver the adopter experience.

---

## Phase 5: User Story 4 - CallRail migrated (P2)

**Goal**: CallRail uses the package; `run_pipeline` calls steps plainly; stored output identical.

**Independent Test**: before/after comparison of stored keys and counts (quickstart step 4); `python -m unittest discover tests` passes.

**Capture baseline first**

- [X] T020 [US4] Before changing anything, run the current pipeline's audit against a fake store (extend `tests/application/test_application.py` or a scratch script) and save the written keys and the `flow`/`step` records (without PII, counts only) to `specs/006-packaged-audit-sdk/baseline-records.json` for comparison in T026

**Migrate**

- [X] T021 [P] [US4] Add `@audited_step("<name>")` (import from `step_audit`) to each step method, step names exactly as in `src/application/pipeline_spec.py`: `src/application/use_cases/extract/callrail_account_uc.py` `execute` → `read_callrail_account`; `callrail_call_uc.py` → `read_callrail_call`; `partner_uc.py` → `read_partners`; `instance_uc.py` → `read_instances`; `campaign_uc.py` → `read_campaigns`; `gads_clickview.py` → `read_gads_clickview`; `src/application/use_cases/transform/calls_statistics_uc.py` `merge_calls_clickview` → `merge_calls_clickview`; `recording_call_statistics_uc.py` → `record_call_statistics`; `src/application/use_cases/load/call_statistics.py` → `save_call_statistics`. Use the `inputs=` rename only where a parameter name differs from the spec's input name (spec inputs: `accounts`, `partners`, `instances`, `calls`, `campaigns`, `clickview`, `call_statistics`)
- [X] T022 [US4] Edit `src/application/pipeline_spec.py` to import `GroupSpec, PipelineSpec, StepSpec` from `step_audit`
- [X] T023 [US4] Edit `src/application/application.py`: remove the `auditor` constructor parameter and its default, the `NoopStepAuditStore`/`StepAuditor` imports, `self.auditor.start()`, `audit = self.auditor.run`, and every `audit(...)`/`inputs={...}` wrapper; call `self.<uc>.execute(...)` directly. Keep all `print` lines and the `dealing_location_code` call between `record_call_statistics` and `save_call_statistics`
- [X] T024 [US4] Edit `main.py`: replace the `audit_store`/`StepAuditor` block with `step_audit.init(pipeline=CALLRAIL_PIPELINE, redis_url=Config.REDIS_URL, env=config, ttl_days=Config.AUDIT_TTL_DAYS)`, and stop passing `auditor=` to `EtlApplication`
- [X] T025 [US4] Update `requirements.txt` and `Dockerfile` to install `packages/step_audit[redis]` (Dockerfile: `COPY packages/step_audit /tmp/step_audit` and `pip install` it before `COPY . .`; remove the now-redundant pinned `redis` line only if the extra pins the same version). Per the repo README, note the Dockerfile change for system support in the PR description
- [X] T026 [US4] Update `tests/application/test_application.py` for the new constructor, add a test in `tests/application/test_pipeline_spec.py` calling `step_audit.testing.assert_spec_matches(CALLRAIL_PIPELINE, <all use case classes>)`, and a test that runs `run_pipeline` with a fake store via `step_audit.init` and compares keys and records with `specs/006-packaged-audit-sdk/baseline-records.json` (ignoring timestamps and run id) (SC-006)
- [X] T027 [US4] Delete `src/application/step_audit.py`, `src/infrastructure/audit/` and `tests/infrastructure/audit/`, and the old `tests/application/test_step_audit.py`, `test_second_pipeline.py` (moved in T008). Confirm `grep -rn "src.application.step_audit\|infrastructure.audit" .` returns nothing
- [X] T028 [US4] Run `black .`, `ruff check .`, `mypy .` and `python -m unittest discover tests` from `integrations/callraill`; fix findings (constitution workflow)

**Checkpoint**: CallRail runs on the package with identical records.

---

## Phase 6: User Story 3 - Deploy together (P2)

**Goal**: one command brings up Redis + dashboard (+ sample pipeline); other pipelines can install the library without this repo's source.

**Independent Test**: quickstart steps 3 and 5.

- [X] T029 [P] [US3] Create `deploy/docker-compose.yml`: service `redis` (image `redis:7-alpine`, named volume, `redis-cli ping` healthcheck, no published port by default), service `monitor` (build `../performance_monitoring_app`, `REDIS_URL=redis://redis:6379/0`, `ENVIRONMENTS=prod,qa`, port `8080:8080`, `depends_on` redis healthy), service `sample` under `profiles: ["sample"]` (build context `..`, Dockerfile `deploy/Dockerfile.sample` installing `packages/step_audit[redis]`, runs `examples/sample_pipeline.py` with `REDIS_URL=redis://redis:6379/0`, `ENV_NAME=qa`)
- [X] T030 [P] [US3] Create `deploy/Dockerfile.sample` (python:3.12-slim, install the package with the `redis` extra, copy `packages/step_audit/examples`)
- [X] T031 [US3] Make the dashboard distinguish an unsupported record version: in `performance_monitoring_app/app/domain/flow.py` `parse_flow` currently returns `"invalid"` when `data.get("v") != SUPPORTED_VERSION`; return a new status `"unsupported"` for a well-formed JSON object whose `v` is an int different from `SUPPORTED_VERSION`, keep `"invalid"` for everything else; propagate the status through the run model and `/api/runs` response (see `specs/005-self-describing-pipeline-graph/contracts/api.md`) and show "Unsupported record version" instead of the generic note in the front end under `performance_monitoring_app/static/`. Add backend cases to `performance_monitoring_app/tests/test_flow.py` and `test_api.py`, and a front-end case under `performance_monitoring_app/static/tests/`
- [X] T032 [US3] Write `deploy/README.md`: bring-up commands, how to point an existing pipeline at the Redis (`REDIS_URL`), how to install the library from a tagged git URL (`pip install "etl-step-audit[redis] @ git+ssh://git@bitbucket.org/<workspace>/<repo>.git@step-audit-v0.1.0#subdirectory=integrations/callraill/packages/step_audit"`; fill the real workspace/repo when tagging), release steps (bump `version` in `pyproject.toml`, tag `step-audit-vX.Y.Z`), and the no-auth warning from `performance_monitoring_app/README.md`
- [X] T033 [US3] Verify on this machine: `docker compose -f deploy/docker-compose.yml --profile sample up --build`, open http://localhost:8080, confirm the `sample` pipeline graph; stop `redis`, rerun the sample, confirm exit code 0 and a warning (quickstart step 3). Record results with the date in `specs/006-packaged-audit-sdk/quickstart.md` under a "Verified" heading

---

## Phase 7: Polish

- [X] T034 [P] Update `README.MD` (repo root of callraill): remove the "copy `step_audit.py`" instructions, document `step_audit.init`, `@audited_step`, and any new environment variables (constitution: document new env vars)
- [X] T035 [P] Update `performance_monitoring_app/README.md` "Add a pipeline" section to the package-based steps (install `etl-step-audit`, `init`, decorate) and link `deploy/README.md`
- [X] T036 [P] Run `black`, `ruff check`, `mypy --strict` inside `packages/step_audit` and fix findings
- [X] T037 Walk through every step of `specs/006-packaged-audit-sdk/quickstart.md` and tick off SC-001…SC-006; note any deviation in the spec's checklist notes

---

## Dependencies & Execution Order

- Setup (T001–T003) → Foundational (T004–T009) → everything else.
- **US1 (T010–T016)** needs Foundational. **US2 (T017–T019)** needs T012–T013 (it implements `init`, which US1's tests exercise by calling `registry.set_active` directly; T018 can land right after T013).
- **US4 (T020–T028)** needs US1 and US2. T020 (baseline) MUST run before T023/T024.
- **US3 (T029–T033)** compose/Dockerfile (T029–T030) need only the sample from T016 and T018; T031 is independent of the library and can start any time after Setup.
- Polish last.

```text
Setup → Foundational → US1 → US2 → US4
                          ↘ US3 (T029–T030 after T018; T031 anytime)
```

## Parallel opportunities

- Foundational: T004, T005, T006 together, then T007; T008 alongside T007.
- US1: T010 and T011 together; T014 and T015 together after T013.
- US4: T021 touches nine different files and can be split.
- US3: T029, T030 and T031 are in different trees and can run in parallel.
- Polish: T034, T035, T036.

## Implementation Strategy

- **MVP = Phase 1 + 2 + US1 + US2** (T001–T019): an installable library with decorator and `init`, proven by the sample pipeline. Stop and validate with quickstart steps 1–2.
- Then **US4** to prove the migration with identical output (the riskiest change, guarded by the T020 baseline).
- Then **US3** for the packaged deployment and the dashboard's unsupported-version state.
- Each phase ends at a checkpoint where the full unit suite passes.
