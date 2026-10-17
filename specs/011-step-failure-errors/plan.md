# Implementation Plan: Step Failure Errors

**Branch**: `011-step-failure-errors` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-step-failure-errors/spec.md`

## Summary

Make a step that raises an error visible as **Failed**, with the error type, a shortened message and a shortened
stack trace, in both halves of Waypoint: the pipeline library (`packages/waypoint_etl`, writes the data) and
Waypoint Monitor (`waypoint_monitor`, reads and shows it).

Read from the code on 2026-10-17:

- `audited_step` (`decorator.py`) and `StepAuditor.run` call `begin()` (writes a `:running:` start marker, TTL 24 h),
  run the function, then `finish()` (writes a `:step:` record). If the function raises, nothing more is written and
  the marker is left behind, so the monitor shows the step as Running, then Stalled, then (with the heartbeat of
  spec 009) Died.
- The monitor (`app/domain/analysis.py::_build_run`) builds each run from finish records, start markers, the flow
  and the alive item. It has no concept of a failure. The front end maps step states in `static/js/api.js::mapStep`
  and renders them in `model.js`, `graph-model.js`, `views/{home,run,step,graph,history}.js`, `ui.js`.

Approach, following the pattern of spec 009 (new item type, new `died`-like run field, same read-only store):

1. **Library**: on `Exception` in a step, write one `...:failed:{NN}-{step}` item (error type, shortened message,
   shortened frames-only traceback, `started_at`, `failed_at`) and re-raise the original exception untouched.
   New `init(capture_error_message=True, redact=None)`. Release as `waypoint-etl` 0.3.0.
2. **Monitor domain**: scan and parse the new key; per run, decide which steps are currently Failed (by attempt
   `index`), whether the failure **stopped the pipeline** (the run is then Failed), and surface `error` data. Add
   Failed to the run/card priority between Running and Died.
3. **Monitor API**: `steps[].state = "failed"` with `error`; run gains `failed`; overview cards gain
   `card_status: "failed"` and `failed_step` / `error`.
4. **Front end**: Failed state in the model, Home card (ranked first), graph node (own icon + label), step detail
   with scrollable, copyable trace, run pill, History row label and a small "Failed only" filter.

No new Redis permission is needed (the monitor stays read-only for failure data) and no existing key or record
changes, so older libraries and older monitors keep working.

## Technical Context

**Language/Version**: Library: Python 3.10+ (`requires-python >=3.10`), standard library only. Monitor: Python 3.12, FastAPI. Front end: ES modules, no build step.

**Primary Dependencies**: none added anywhere (`traceback` from the standard library).

**Storage**: Redis. One new item per failed attempt: `waypoint:{pipeline}:{env}:{run_id}:failed:{NN}-{step}`, JSON, TTL = the run's `ttl_days`. Written only by the library; the monitor never writes it.

**Testing**: Library `python -m unittest discover tests` (`packages/waypoint_etl`); monitor `python -m unittest discover tests` (`waypoint_monitor`); front end `node --test static/tests/*.test.mjs`; manual browser pass from [quickstart.md](quickstart.md).

**Target Platform**: Pipelines in Docker on any host; monitor container; modern desktop and phone browsers.

**Project Type**: Python library + web application (small API plus static front end), both already in this repository.

**Performance Goals**: Failure visible within one dashboard refresh (`REFRESH_SECONDS`, 5 s) plus the 2 s server cache, so under 10 s (SC-001). Recording a failure adds at most one Redis write (≤ 2 s socket timeout) before the original error propagates.

**Constraints**: Monitoring never changes a step's outcome (FR-002/003); no variable values and no data content stored (FR-006, FR-019); message ≤ 500 chars, traceback ≤ 8 KB (FR-005); old and new library/monitor combinations interoperate (FR-015); monitor writes nothing new (FR-018).

**Scale/Scope**: About 3 to 20 pipelines, 2 environments, tens of steps, up to 100 runs per request; at most a few failure items per run, each ≤ ~9 KB.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the CallRail ETL constitution copied into this repository, not a Waypoint
one (the same situation as specs 009 and 010). Its principles are applied by analogy:

| Principle | Status |
|---|---|
| I. Layered architecture | Pass. Monitor keeps `domain/` (pure parsing and analysis), `infrastructure/` (Redis reads) and `api/`; domain gains no I/O. Library keeps keys, auditor, decorator, registry separate. |
| II. PII protection (non-negotiable) | Pass by design. Frames-only traceback (no locals, no exception text unless message capture is on); message capture can be turned off or redacted; both sides cap sizes; front end escapes all error text. See [research.md](research.md) R3, R4, R9. |
| III. Type safety and quality | Pass by plan: all new Python fully typed; `mypy --strict`, `ruff`, `black` (line length 100) on both packages. |
| IV. Test coverage | Pass by plan: unit tests for every new behaviour in both packages and for front-end model rules, including regression tests for "old runs unchanged". |
| V. Resilient, observable execution | Pass. Recording errors are caught, logged and swallowed; the original error is re-raised unchanged; failure items expire with the run; no duplicate-data concern (items are overwritten per attempt key). |

Gate result: pass, no violations to justify. Re-checked after Phase 1 design: still pass.

## Project Structure

### Documentation (this feature)

```text
specs/011-step-failure-errors/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── redis-keys.md      # the new failed item
│   ├── library-api.md     # init(...) additions and behaviour guarantees
│   ├── api.md             # /api/runs and /api/overview additions
│   └── ui.md              # what the operator sees
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
packages/waypoint_etl/
├── pyproject.toml                 # version 0.3.0
├── README.md                      # document failure records, capture_error_message, redact
├── src/waypoint_etl/
│   ├── keys.py                    # failed_key()
│   ├── errors.py                  # NEW: build the error payload (type, message, traceback, caps, redaction)
│   ├── auditor.py                 # fail(); remember each attempt's start time; run() records failures
│   ├── decorator.py               # sync and async wrappers: except Exception -> fail() -> bare raise
│   ├── registry.py                # init(capture_error_message=True, redact=None)
│   └── __init__.py                # __version__ = "0.3.0"
└── tests/
    ├── test_errors.py             # NEW: caps, no locals, message off, redact, chained causes
    ├── test_failure.py            # NEW: record written, re-raise identical, sync + async, store down
    └── test_auditor.py / test_decorator.py / test_keys.py   # extended

waypoint_monitor/
├── app/
│   ├── domain/models.py           # StepFailure, ErrorInfo; ParseResult gains nothing (kept separate)
│   ├── domain/parsing.py          # parse_failures(); failed key regex
│   ├── domain/analysis.py         # failed steps, stopped-failure rule, run `failed`, priority, ended_at
│   ├── domain/overview.py         # card_status "failed", ATTENTION, summary failed_step/error
│   ├── infrastructure/store.py    # RecordStore.list_failures
│   ├── infrastructure/redis_store.py  # list_failures (SCAN + MGET, read only)
│   └── api/routes.py              # read failures, merge unreadable counts, pass to build_runs
├── static/js/
│   ├── api.js                     # mapStep 'failed', run.failed, card failedStep/error
│   ├── model.js                   # CARD_STATUS failed, cardReason/cardWhen, analyse, heroTitle, card ranking
│   ├── graph-model.js             # failed is a stop point (like stalled/died)
│   ├── ui.js                      # Failed pill, copy-button helper
│   ├── views/{home,run,step,graph,history}.js
│   └── ../styles.css, ../index.html (only if markup is needed)
├── static/tests/                  # model, graph-model, overview, run-view tests extended
├── tests/                         # fakes (list_failures), parsing, analysis, overview, api, redis_store
└── README.md                      # Failed state, no new permission
README.md (root)                   # one line pointing at the new state
```

**Structure Decision**: Extend the two existing components in place. No new service, package or dependency.

## Complexity Tracking

No constitution violations. One justified addition: a small status filter on History (see [research.md](research.md)
R10), because the spec asks for filtering by Failed and History has only an environment filter today.
