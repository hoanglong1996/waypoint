# Implementation Plan: Live Step Running Indicator

**Branch**: `004-step-running-indicator` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-step-running-indicator/spec.md`

## Summary

Show which pipeline step is running right now, and keep the monitor current without a manual refresh. Three
changes: (1) the pipeline's `StepAuditor` writes a small **start marker** to Redis before each step runs
(today it only writes after a step finishes, so a busy step is indistinguishable from a missing one);
(2) the monitor's run analysis merges markers with finish records and gives every step a `state`
(`done`, `missing`, `running`, `stalled`, `waiting`), plus a run-level `running` status; (3) the front end
draws a spinner, an indeterminate progress bar and an elapsed timer on running steps (graph node and list
card), shows "Waiting" for steps not yet started, and reloads every 5 seconds. The reload skips redrawing
when nothing but elapsed/age counters changed, so animations and selection do not restart.

## Technical Context

**Language/Version**: Python 3.12 (pipeline `src/` and monitor backend); vanilla ES2020 modules, CSS3 (front end)

**Primary Dependencies**: none new (existing `redis`, `fastapi`)

**Storage**: Redis, new key family `callrail:running:<env>:<run_id>:<NN>-<step>` with a 24 h TTL; existing `callrail:audit:*` records unchanged

**Testing**: `python -m unittest discover tests` (pipeline: `tests/application/test_step_audit.py`); monitor `pytest` in `performance_monitoring_app/tests` (analysis, parsing, api, config, redis store); `node --test` in `static/tests` (state model, signature/no-op redraw, edge state); manual run per [quickstart.md](quickstart.md)

**Target Platform**: Docker image on Linux (pipeline job and monitor); modern desktop/mobile browsers

**Project Type**: web application (existing monitor) plus the batch pipeline that feeds it

**Performance Goals**: completion visible within 5 s of a step finishing; one `/api/runs` request per 5 s per open page; server cache coalesces concurrent viewers

**Constraints**: audit must never change pipeline behaviour (failures swallowed); counts and timestamps only (no PII); monitor stays read-only; reduced-motion respected; no new env var in the pipeline (marker TTL is a constant)

**Scale/Scope**: 9 steps, 2 environments, ~270 audit keys per env at 30-day retention

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Layered architecture | Pass | Start-marker write lives in `application/step_audit.py` through the existing `StepAuditStore` protocol; Redis I/O stays in `infrastructure/audit/` |
| II. Caller PII protection | Pass | Marker holds run id, env, step name, index, start time only; no item contents, no new entity |
| III. Type safety | Pass | New code fully typed; `mypy --strict`, `ruff`, `black` run before merge |
| IV. Test coverage | Pass | Unit tests for marker write, failure swallowing, analysis states; no live services |
| V. Resilient execution | Pass | Marker write failure is logged and swallowed; re-running a step rewrites the same key (idempotent) |
| Technical constraints | Pass | New monitor env var `STALL_SECONDS` and changed `REFRESH_SECONDS`/`CACHE_SECONDS` defaults documented in the monitor README |

Post-design re-check: no violations; Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/004-step-running-indicator/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── start-marker.md   # Redis key + record the pipeline writes
│   └── api.md            # /api/runs and /api/config additions
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks (not created here)
```

### Source Code

```text
src/application/step_audit.py                 # write start marker before fn(); constants
src/infrastructure/audit/                     # unchanged (Redis store reused via write())
tests/application/test_step_audit.py          # marker written first, key/TTL, swallowed failure, fn raising

performance_monitoring_app/
├── app/domain/models.py                      # StartMarker dataclass; StepDefinition unchanged
├── app/domain/parsing.py                     # parse_markers(); marker key regex
├── app/domain/analysis.py                    # merge markers -> step.state, run.status "running"
├── app/infrastructure/store.py               # RecordStore.list_markers(env)
├── app/infrastructure/redis_store.py         # list_markers via SCAN callrail:running:<env>:*
├── app/api/routes.py                         # pass markers + stall_seconds to build_runs
├── app/config.py                             # refresh_seconds 5, cache_seconds 2, stall_seconds 900
├── static/js/model.js                        # stepState(), runSignature(), elapsed helpers
├── static/js/graph-model.js                  # running/waiting nodes; edges inactive unless both done
├── static/js/views/graph.js                  # spinner + "Running · 42 s" on node
├── static/js/views/step.js                   # list card: spinner, progress bar, Waiting/Stalled
├── static/js/views/latest.js                 # headline/summary treat running run as in progress
├── static/js/app.js                          # skip redraw on unchanged signature; 1 s elapsed tick; refetch on tab focus
├── static/styles.css                         # .step--running/.step--waiting/.step--stalled, spinner, bar, reduced motion
├── tests/                                    # fakes.py FakeStore.list_markers + make_markers; test_analysis/api/config/redis_store
├── static/tests/                             # model.test.mjs, graph-model.test.mjs additions
└── README.md                                 # env var table
```

**Structure Decision**: extend the existing two-part layout (pipeline `src/`, monitor `performance_monitoring_app/`); no new modules beyond a parser function and a dataclass.

## Complexity Tracking

No constitution violations to justify.
