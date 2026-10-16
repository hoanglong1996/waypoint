# Implementation Plan: Self-Describing Pipeline Graph

**Branch**: `005-self-describing-pipeline-graph` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-self-describing-pipeline-graph/spec.md`

## Summary

Make the monitor pipeline-agnostic. Today the step list, hand-offs and groups are hardcoded in the monitor
backend (`app/domain/steps.py`, served by `/api/config`) and node positions and labels in a front-end table
(`static/js/graph-model.js` `POSITIONS`). Four changes:

1. **Pipeline side**: the shared audit facility (`src/application/step_audit.py`) takes a declared
   `PipelineSpec` (pipeline name + full step list with inputs, producers, optional label/group/layout hints) and
   writes it to Redis as a **flow description** when the run starts. Step records and start markers move under
   a pipeline-scoped key layout.
2. **Key layout**: `etl-audit:{pipeline}:{env}:{run_id}:{flow|step|running}[:NN-step]`. The old `callrail:*`
   keys are ignored (data already deleted, spec FR-014).
3. **Monitor backend**: discovers pipelines from keys, parses flow descriptions, and builds each run from its
   own description (missing steps = not reached, absent/invalid description = simplified graph). `EXPECTED_STEPS`
   and `expected_steps` in `/api/config` are removed. New `/api/pipelines`; `/api/runs` takes `pipeline`.
4. **Monitor front end**: pipeline picker; graph layout computed from the run's hand-offs (layered, with
   optional hints) instead of the `POSITIONS` table. CallRail becomes the reference pipeline that declares itself.

## Technical Context

**Language/Version**: Python 3.12 (pipeline `src/` and monitor backend); vanilla ES2020 modules, CSS3 (front end)

**Primary Dependencies**: none new (existing `redis`, `fastapi`)

**Storage**: Redis. New key family `etl-audit:*` (flow, step, running); same TTLs as today (`AUDIT_TTL_DAYS` for flow and step, 24 h for markers)

**Testing**: pipeline `python -m unittest discover tests` (`tests/application/test_step_audit.py`, `tests/infrastructure/audit/`); monitor `python -m unittest discover tests` (parsing, analysis, api, discovery, redis store); front end `node --test static/tests` (layout engine, simplified graph); manual run per [quickstart.md](quickstart.md)

**Target Platform**: Docker images on Linux (pipeline job, monitor); modern desktop/mobile browsers

**Project Type**: web application (existing monitor) plus the batch pipeline that feeds it

**Performance Goals**: one `/api/runs` request per refresh interval per open page; pipeline discovery adds no extra full scan (one `SCAN etl-audit:*:{env}:*` per env, shared with the record scan); layout of 50 steps computed in under 100 ms in the browser

**Constraints**: audit never changes pipeline behaviour (failures swallowed); structure and counts only, no PII; monitor stays read-only; no new env var in the pipeline (pipeline name and step list are code, declared once); monitor needs no new setting (discovery is automatic)

**Scale/Scope**: up to ~50 steps per pipeline, a handful of pipelines, 2 environments, ~30 days retention

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Layered architecture | Pass | `PipelineSpec` and the auditor stay in `application/` with no CallRail imports; Redis I/O stays in `infrastructure/audit/`; the CallRail spec constant sits beside the pipeline wiring in `application/` |
| II. Caller PII protection | Pass | Flow description holds names, labels, groups, hints only; contract forbids item data; labels come from developer code, never from data |
| III. Type safety | Pass | New code fully typed; `mypy --strict`, `ruff`, `black` run before merge |
| IV. Test coverage | Pass | Unit tests for spec validation, flow write/failure swallowing, parsing, discovery, analysis, layout; no live services |
| V. Resilient execution | Pass | Flow write failure is logged and swallowed; rewriting the same flow key on re-run is idempotent |
| Technical constraints | Pass | No new pipeline env var; README gains the new contract and the removed `expected_steps` |

Post-design re-check: no violations; Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-self-describing-pipeline-graph/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── redis-keys.md     # flow description + key layout, the cross-pipeline contract
│   └── api.md            # monitor endpoints (changed)
└── tasks.md              # /speckit-tasks, not created here
```

### Source Code

```text
src/
├── application/
│   ├── step_audit.py          # + PipelineSpec/StepSpec, validation, StepAuditor writes flow at start, new keys
│   ├── application.py         # builds the CallRail spec, passes it to the auditor
│   └── pipeline_spec.py       # CALLRAIL_PIPELINE declaration (reference example)
└── infrastructure/audit/redis_step_audit.py   # unchanged protocol; key helpers live in step_audit.py

performance_monitoring_app/
├── app/
│   ├── domain/
│   │   ├── steps.py           # REMOVED (EXPECTED_STEPS)
│   │   ├── flow.py            # NEW: parse/validate flow description into FlowSpec
│   │   ├── models.py          # StepRecord/StartMarker gain pipeline; FlowSpec/StepDefinition built from data
│   │   ├── parsing.py         # new key regexes; no STEP_NAMES whitelist
│   │   └── analysis.py        # build_runs(flow per run); simplified fallback
│   ├── infrastructure/        # list_flows/list_records/list_markers per (pipeline, env); list_pipelines
│   └── api/routes.py          # /api/pipelines, /api/runs?pipeline=, /api/config without steps
├── static/js/
│   ├── api.js, app.js         # pipeline picker; per-run steps from the response
│   ├── graph-model.js         # POSITIONS removed; auto layered layout + hints
│   └── model.js, ui.js        # group labels/colours from data
└── tests/, static/tests/      # extended as listed under Testing

tests/application/test_step_audit.py, tests/application/test_pipeline_spec.py
```

**Structure Decision**: keep the existing two-part layout (pipeline `src/` + `performance_monitoring_app/`). The
shared facility stays one dependency-free module so another pipeline can copy `step_audit.py` (spec assumption:
no separate package).

## Complexity Tracking

No violations.
