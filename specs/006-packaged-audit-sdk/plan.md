# Implementation Plan: Packaged Pipeline Monitoring Product

**Branch**: `006-packaged-audit-sdk` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-packaged-audit-sdk/spec.md`

## Summary

Turn the three pieces (dashboard, Redis, step-audit) into a shippable product. The step-audit code
moves out of `src/application/step_audit.py` into an installable package, `etl-step-audit` (import
name `step_audit`). It gains a single `step_audit.init(...)` call (pipeline name, Redis URL, spec) for
`main.py`, and a `@audited_step` decorator for use-case methods, so orchestration code like
`EtlApplication.run_pipeline` calls steps plainly and no longer passes `audit(...)` wrappers or
`inputs={...}` dicts. The Redis key layout and record format from feature 005 are unchanged. A
compose file brings up Redis + dashboard (+ an optional sample pipeline). CallRail migrates to the
package with identical output.

## Technical Context

**Language/Version**: Python 3.12+ (library supports 3.10+ so older consumers can adopt; CI-less repo, tested on 3.12)

**Primary Dependencies**: `redis` (optional extra `redis`); standard library otherwise

**Storage**: Redis, keys `etl-audit:{pipeline}:{env}:{run}:...` (contract 005, unchanged)

**Testing**: `python -m unittest discover tests` (constitution IV); package has its own `tests/`

**Target Platform**: Linux containers; local `python main.py -c <env>`

**Project Type**: library + web service (dashboard) + deployment bundle

**Performance Goals**: decorator overhead negligible next to a step (a few Redis writes per step)

**Constraints**: audit failures never alter pipeline results; only names and counts recorded (PII rule, constitution II); Redis timeouts 2 s

**Scale/Scope**: ≤100 steps per pipeline, tens of pipelines, sequential steps within one run

## Constitution Check

| Principle | Status |
|---|---|
| I. Layered architecture | PASS with note. The library is infrastructure-neutral and lives outside `src/`; callrail `src/` imports it. Use cases gain a decorator (an application concern, no infrastructure import). Redis store stays in the package's infrastructure module, wired from `main.py`. |
| II. Caller PII | PASS. Counts and names only; test asserts no item content is serialised (carried over from 005). |
| III. Type safety | PASS. Package typed (`py.typed`), `mypy --strict`, ruff, black 100. Decorator uses `ParamSpec` to keep signatures. |
| IV. Test coverage | PASS. Tests move with the package; callrail tests updated; no live services. |
| V. Resilient execution | PASS. Missing config or Redis error → no-op/warning (FR-009). Sentry untouched. |

No violations; Complexity Tracking not needed. Re-checked after Phase 1: still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/006-packaged-audit-sdk/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── library-api.md
└── tasks.md          # /speckit-tasks
```

### Source Code

```text
packages/step_audit/                 # NEW: installable distribution "etl-step-audit"
├── pyproject.toml
├── README.md                        # adoption guide (FR-014)
├── src/step_audit/
│   ├── __init__.py                  # public API: init, audited_step, PipelineSpec, StepSpec, GroupSpec
│   ├── spec.py                      # PipelineSpec/StepSpec/GroupSpec + validate_spec
│   ├── keys.py                      # key builders, FLOW_VERSION
│   ├── auditor.py                   # StepAuditor (moved from src/application/step_audit.py)
│   ├── decorator.py                 # audited_step (sync + async), reads the active auditor
│   ├── registry.py                  # init(), active auditor, no-op when unconfigured
│   ├── stores.py                    # StepAuditStore protocol, Noop, RedisStepAuditStore
│   └── py.typed
├── examples/sample_pipeline.py      # minimal adopter (3 steps)
└── tests/                           # moved + new tests

deploy/
├── docker-compose.yml               # redis + monitor (+ sample profile)
└── README.md

src/application/application.py       # CHANGED: plain calls, no audit()/inputs
src/application/pipeline_spec.py     # CHANGED: imports from step_audit
src/application/use_cases/**         # CHANGED: one decorator line per step method
main.py                              # CHANGED: step_audit.init(...)
requirements.txt / Dockerfile        # CHANGED: install the package
performance_monitoring_app/          # CHANGED: reject unsupported flow version (FR-013)
```

**Structure Decision**: a new `packages/step_audit/` distribution inside this repo, installed by
callrail via a path/editable dependency and by other pipelines via a tagged git dependency. The
old `src/application/step_audit.py` and `src/infrastructure/audit/` are deleted (no shim; the one
consumer is migrated in the same change).
