# Implementation Plan: Pipeline Step Audit Trail

**Branch**: `001-pipeline-step-audit` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-pipeline-step-audit/spec.md`

## Summary

Each step in `EtlApplication.run_pipeline` is wrapped so that, after it runs, a small record
(step name, named input counts, output count, finish time) is written to Redis with a 30-day TTL.
Records are keyed by environment and run start time so runs never overwrite each other. Only counts
are stored. Any Redis error is logged as a warning and swallowed, so the pipeline behaves exactly as
before. Redis is optional: with no `REDIS_URL` the auditor is a no-op (same pattern as Sentry).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: `redis` (redis-py, new, pinned in `requirements.txt`); existing stack otherwise

**Storage**: Redis (new). One string key per step record, value is JSON, TTL 2,592,000 s

**Testing**: `unittest` with `MagicMock`; fake in-memory store, no live Redis

**Target Platform**: Docker container run as a scheduled job (CronJob)

**Project Type**: Single-project batch ETL

**Performance Goals**: Negligible overhead: ~9 small writes per run

**Constraints**: Must never fail or slow the pipeline noticeably; short Redis socket timeouts; counts only (no PII)

**Scale/Scope**: ~9 records per run, a few runs per day, 30-day retention

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Layered Architecture | Pass | Auditor and `StepAuditStore` protocol in `application/`; Redis client in `infrastructure/audit/`; domain untouched |
| II. Caller PII Protection | Pass | Only integer counts and step names are stored; helper never serialises item contents |
| III. Type Safety | Pass | Fully typed; passes `mypy` strict |
| IV. Test Coverage | Pass | Unit tests for count summarising, auditor, failure swallowing, and `run_pipeline` wiring |
| V. Resilient Execution | Pass | Store errors caught and logged; re-runs add new keys, no duplicate-data risk |

Re-check after design: still passes. No complexity violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-pipeline-step-audit/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── step-record.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── application/
│   ├── application.py            # run_pipeline: wrap each step with the auditor
│   └── step_audit.py             # NEW: StepAuditStore protocol, count_items(), StepAuditor
├── infrastructure/
│   └── audit/
│       ├── __init__.py           # NEW
│       └── redis_step_audit.py   # NEW: RedisStepAuditStore (setex + JSON)
└── utils/
    └── config.py                 # + REDIS_URL, AUDIT_TTL_DAYS

main.py                           # build store (or no-op) and pass to EtlApplication
tests/
├── application/test_step_audit.py            # NEW
├── application/test_application.py           # extended
└── infrastructure/audit/test_redis_step_audit.py  # NEW (fake client)
requirements.txt                  # + redis
README.MD                         # document new env vars and key layout
```

**Structure Decision**: Single project, existing layers. `EtlApplication` takes an optional
`auditor` argument (default no-op) so existing construction and tests keep working.

## Complexity Tracking

No violations.
