---

description: "Task list for Pipeline Step Audit Trail"
---

# Tasks: Pipeline Step Audit Trail

**Input**: Design documents from `/specs/001-pipeline-step-audit/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/step-record.md

**Tests**: Included because the constitution (principle IV) requires unit tests for changed behaviour. Tests use `unittest` and a fake in-memory store; no live Redis.

**Organization**: Grouped by user story. Paths are relative to the repository root (`integrations/callraill`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3 from spec.md

## Phase 1: Setup

- [X] T001 Add pinned `redis` dependency to `requirements.txt` (next to `sentry-sdk`)
- [X] T002 [P] Add `REDIS_URL = os.getenv("REDIS_URL", "")` and `AUDIT_TTL_DAYS` (int, default 30, falls back to 30 on invalid value) to `Config` in `src/utils/config.py`, with a comment that an empty `REDIS_URL` disables auditing

---

## Phase 2: Foundational (blocking)

**Purpose**: The auditor and store contract that every story uses.

- [X] T003 Create `src/application/step_audit.py` with a `StepAuditStore` Protocol (`write(key: str, record: dict[str, object], ttl_seconds: int) -> None`), a `NoopStepAuditStore`, and `count_items(value: object) -> int | None` per data-model.md: `None` → `None`, list/tuple/set → `len`, any other object → `1`. Never serialise item contents.
- [X] T004 Add `StepAuditor` to `src/application/step_audit.py`: constructor `(store, env, ttl_seconds, run_id=None)` where `run_id` defaults to UTC now formatted `YYYYMMDDTHHMMSSZ`; method `run(name: str, fn: Callable[..., T], *args: object, inputs: dict[str, object] | None = None) -> T` — see T005 for the exact semantics
- [X] T005 Implement `StepAuditor.run` semantics in `src/application/step_audit.py`: increment a 1-based step index; call `fn(*args)`; on exception re-raise unchanged with no record written; on success build the record `{run_id, env, step, index, inputs: {name: count_items(v)}, output: count_items(result), finished_at: UTC ISO-8601 "Z"}` and write it under key `callrail:audit:{env}:{run_id}:{index:02d}-{step}`; wrap the build and `store.write` in `try/except Exception` that prints `Warning: step audit failed for {name}: {exc}` and continues; return the result. Positional `args` are passed to `fn`; the `inputs` dict (name → value) is used only to build the record's input counts and is NOT passed to `fn`
- [X] T006 [P] Create `src/infrastructure/audit/__init__.py` (empty) and `src/infrastructure/audit/redis_step_audit.py` with `RedisStepAuditStore(url: str)` implementing `StepAuditStore`: build `redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)`, and `write` does `setex(key, ttl_seconds, json.dumps(record))`
- [X] T007 [P] Create `tests/infrastructure/audit/__init__.py` and `tests/infrastructure/audit/test_redis_step_audit.py` using a fake client: `write` calls `setex` once with the key, the TTL, and valid JSON equal to the record

**Checkpoint**: Auditor can record a step with any store.

---

## Phase 3: User Story 1 - Inspect step input/output counts (Priority: P1) 🎯 MVP

**Goal**: After a run, every step has a record with named input counts and an output count.

**Independent Test**: Run `run_pipeline` with mocked use cases and a fake store; verify one record per step with the counts in data-model.md.

### Tests for User Story 1

- [X] T008 [P] [US1] Create `tests/application/test_step_audit.py` with `count_items` cases: `None` → `None`; `[]` → `0`; list of 10 → `10`; tuple and set; a single object → `1`
- [X] T009 [P] [US1] In `tests/application/test_step_audit.py` add `StepAuditor.run` cases using a fake in-memory store: record fields and key format match `contracts/step-record.md`; no-input step has `inputs == {}`; multi-input step has one named count per input; step returning `None` has `output is None`; step indices are sequential
- [X] T010 [US1] In `tests/application/test_application.py` extend `test_run_pipeline` (and fix its `EtlApplication(...)` call, which is currently missing `recording_call_statistics_uc`) so a fake store receives 9 records in the order listed in data-model.md, e.g. `read_callrail_account` has `inputs == {}` and `output == 10` when the mock returns 10 accounts

### Implementation for User Story 1

- [X] T011 [US1] Add an optional `auditor: StepAuditor | None = None` last parameter to `EtlApplication.__init__` in `src/application/application.py`, defaulting to a `StepAuditor(NoopStepAuditStore(), env="", ttl_seconds=0)` so existing callers and tests keep working
- [X] T012 [US1] In `EtlApplication.run_pipeline` (`src/application/application.py`) route each call through `self.auditor.run(...)` with these names and inputs, keeping the existing `print` lines and the call order unchanged: `read_callrail_account` (no input); `read_callrail_call` (`inputs={"accounts": ...}`); `read_partners` (none); `read_instances` (`partners`); `read_campaigns` (`instances`); `read_gads_clickview` (`instances`); `merge_calls_clickview` (`calls`, `campaigns`, `clickview`); `record_call_statistics` (`call_statistics`); `save_call_statistics` (`call_statistics`). Do not record `dealing_location_code` separately; it stays a plain call before the save step
- [X] T013 [US1] In `main.py` `_run_etl`, build the store: `RedisStepAuditStore(Config.REDIS_URL)` when `Config.REDIS_URL` is non-empty, else `NoopStepAuditStore()`; create `StepAuditor(store, Config.SENTRY_ENVIRONMENT or config env, Config.AUDIT_TTL_DAYS * 86400)` using the `-c` value as `env` (reuse the `config` name already in `src/utils/config.py`), and pass it as `auditor=` to `EtlApplication`

**Checkpoint**: MVP; counts recorded for all 9 steps.

---

## Phase 4: User Story 2 - Records expire after 30 days (Priority: P2)

**Goal**: Each record expires 30 days after being written.

**Independent Test**: A written record carries a TTL of 2,592,000 s.

- [X] T014 [P] [US2] In `tests/application/test_step_audit.py` assert the fake store receives `ttl_seconds == 30 * 86400` when `StepAuditor` is built with the default configuration, and a different TTL when `AUDIT_TTL_DAYS` is overridden
- [X] T015 [US2] In `main.py` confirm the TTL passed to `StepAuditor` is `Config.AUDIT_TTL_DAYS * 86400` (done in T013; only adjust if T014 shows a mismatch)

---

## Phase 5: User Story 3 - Audit failures never break the pipeline (Priority: P2)

**Goal**: Storage problems or step failures do not change pipeline behaviour.

**Independent Test**: Run with a store that raises on every write; pipeline completes and the save step is called.

- [X] T016 [P] [US3] In `tests/application/test_step_audit.py` add: a store whose `write` raises → `run` returns the step result and prints the warning, without raising
- [X] T017 [P] [US3] In `tests/application/test_step_audit.py` add: a step function that raises → exception propagates unchanged and no record is written for it, while earlier records remain
- [X] T018 [US3] In `tests/application/test_application.py` add a test running `run_pipeline` with a raising store and asserting `save_call_statistics_uc.execute` is still called once
- [X] T019 [P] [US3] In `src/infrastructure/audit/redis_step_audit.py` make sure construction does not connect (redis-py is lazy) so a bad `REDIS_URL` surfaces only inside `write`, where `StepAuditor` catches it; if `from_url` itself can raise on a malformed URL, catch it in `main.py` T013 and fall back to `NoopStepAuditStore` with a warning

---

## Phase 6: Polish

- [X] T020 [P] Document `REDIS_URL`, `AUDIT_TTL_DAYS`, the key layout, and a `redis-cli` inspection example in `README.MD` (new "Step Audit (Redis)" section, same table style as Sentry)
- [X] T021 [P] Add `REDIS_URL` and `AUDIT_TTL_DAYS` examples to the `.env.qa`/`.env.prod` documentation only if such templates exist in the repo; otherwise skip
- [X] T022 Run `black .`, `ruff check .`, `mypy .` and `python -m unittest discover tests`; fix any findings in the new files
- [ ] T023 Follow `specs/001-pipeline-step-audit/quickstart.md` against a local Redis and check the 9 records, TTL, second-run behaviour, and the Redis-down case

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 → US2 / US3 (independent after US1) → Polish
- T003 → T004 → T005 (same file); T006 and T007 can run in parallel with them once T003 exists
- Within US1: tests T008–T010 first (they fail), then T011 → T012 → T013
- US2 and US3 depend only on the auditor (Phase 2) plus T013 wiring for end-to-end checks

### Parallel examples

- After T003: T006 and T007 together
- US1 tests: T008 and T009 together
- After US1: T014, T016, T017, T019 together

## Implementation Strategy

- **MVP**: Phases 1–3 (counts recorded, Redis optional). Stop and validate with the quickstart.
- Then US2 (TTL verification) and US3 (failure tolerance) tests; most behaviour already exists in the auditor, so these mostly add tests.
- Finish with docs and the lint/type/test gate.
