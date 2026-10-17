# Implementation Plan: Optional Step Metrics

**Branch**: `013-step-metrics` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/013-step-metrics/spec.md`

## Summary

Named numbers per step, recorded by the pipeline library (`packages/waypoint_etl`, writes) and shown by Waypoint
Monitor (`waypoint_monitor`, reads and shows). Read from the code on 2026-10-17:

- A step's finish record is written **once, when the step returns** (`auditor.py::finish`). A running step has no
  record, so metrics visible while the step runs (FR-007) cannot live in it. **Decision (roadmap open decision 8):
  one separate record per step attempt**, `waypoint:{pipeline}:{env}:{run_id}:metrics:{NN}-{step}`, holding the whole
  current state of that attempt's metrics as one JSON value ([research.md](research.md) R1).
- The library merges calls **in memory** (set / add / max under a lock) and a background writer rewrites the
  changed records at most once a second with the existing `store.write` (`SETEX`). Same shape as the event writer
  and the heartbeat. Hot loops cost a dictionary update, not a Redis call (FR-006, SC-003).
- `{NN}` is the step attempt's index, so a retry writes a different key and the monitor shows only the newest attempt's
  metrics, exactly like failures (spec 011, "latest attempt").
- Declarations ride in the run's own **flow record** as an optional `metrics` list on each step (`FLOW_VERSION`
  stays 1: old monitors ignore the field), so labels, units and thresholds are known before any value arrives and
  each run is judged by the thresholds it was started with (FR-011).
- The monitor needs **no new permission**: it already `SCAN`s and `MGET`s `waypoint:*`. It parses metric records
  like step records (damaged ones skipped and counted per run), merges them into each step of `/api/runs`, computes
  the over-threshold flag, and exposes a per-step and per-run count of flagged metrics for alerting (#6).
- History trend, the median and the threshold line are computed in the front end from the runs it already loads,
  using the existing `duration_window_runs` / `duration_min_runs` settings (FR-019). No new endpoint.

Library ships as `0.5.0`. Monitor works before any pipeline is upgraded (FR-021).

## Technical Context

**Language/Version**: Library: Python 3.10+, standard library only (`redis` stays an optional extra). Monitor: Python 3.12, FastAPI. Front end: ES modules, no build step.

**Primary Dependencies**: none added anywhere.

**Storage**: Redis. New per step attempt: one JSON string `...:{run_id}:metrics:{NN}-{step}` (TTL = the run's `ttl_days`, refreshed on every write). Flow record gains optional `metrics` per step. Written only by the library.

**Testing**: Library `python -m unittest discover tests`; monitor `python -m unittest discover tests`; front end `node --test static/tests/*.test.mjs`; manual browser pass from [quickstart.md](quickstart.md).

**Target Platform**: Pipelines in Docker on any host; monitor container; modern desktop and phone browsers.

**Project Type**: Python library + web application (small API plus static front end), both already in this repository.

**Performance Goals**: `metric()` is a locked dictionary update (microseconds, no I/O); 100,000 calls add at most 5% run time (SC-003). One record write per changed step per second at most. Monitor adds one `SCAN` and one pipelined `MGET` pass per pipeline per cache window (the same cost class as the failure items). 30-run trend opens in under 2 s (SC-008): data is already in `/api/runs`.

**Constraints**: Recording never changes a step's outcome and never waits on the network (FR-005/006); only names, numbers and times are stored (FR-009); monitor read-only toward metric data (FR-023); old and new library/monitor combinations interoperate (FR-021, FR-024).

**Scale/Scope**: 3 to 20 pipelines, 2 environments, tens of steps, at most 20 metrics per step (a record under ~2 KB), up to 100 runs per request.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the CallRail ETL constitution copied into this repository, not a Waypoint one
(as in specs 009 to 012). Its principles are applied by analogy:

| Principle | Status |
|---|---|
| I. Layered architecture | Pass. Monitor: pure parsing, threshold flags and merge in `domain/`, Redis reads in `infrastructure/`, HTTP in `api/`. Library: merge state and writer in their own module (`metrics.py`), separate from keys, auditor and decorator. |
| II. PII protection (non-negotiable) | Pass by design. Values are finite numbers only (no text, no booleans); names are restricted to `[a-z0-9_]{1,64}` and labels/units to short capped text from the author's *declaration* (code, not data); the front end escapes everything. Nothing from pipeline items is read. See R7. |
| III. Type safety and quality | Pass by plan: all new Python fully typed; `mypy --strict`, `ruff`, `black` (line length 100) on both packages. |
| IV. Test coverage | Pass by plan: unit tests for every new behaviour in both packages (modes, limits, threads, no-op cases, parsing, flags, retry, old-run regressions) and front-end model tests. |
| V. Resilient, observable execution | Pass. `metric()` cannot raise or block; writer errors are caught and logged at most once a minute; state and record size are bounded; keys expire with the run; nothing changes the exit code or a step's result. |

Gate result: pass. Re-checked after Phase 1 design: still pass. No new Redis permission, no new dependency, no new
service. One departure to justify below.

## Project Structure

### Documentation (this feature)

```text
specs/013-step-metrics/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── redis-keys.md      # metrics record, flow-record addition
│   ├── library-api.md     # metric(), Metric, StepSpec(metrics=...), guarantees
│   ├── api.md             # metrics on steps in /api/runs, flag counts
│   └── ui.md              # what the operator sees
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
packages/waypoint_etl/
├── pyproject.toml                 # version 0.5.0
├── README.md                      # metric(), Metric declaration, per-process note, limits
├── src/waypoint_etl/
│   ├── keys.py                    # metrics_key(pipeline, env, run_id, index, step); METRIC_LIMITS
│   ├── spec.py                    # Metric dataclass; StepSpec.metrics; validation
│   ├── metrics.py                 # NEW: validate name/value, merge (set/add/max), per-attempt state, writer thread
│   ├── auditor.py                 # flow record carries declared metrics; latest attempt index per step; record_metric(); owns writer; stop/flush
│   ├── registry.py                # metric() entry point
│   └── __init__.py                # exports metric, Metric; __version__ = "0.5.0"
└── tests/
    ├── test_metrics.py            # NEW: modes, validation, limits, threads, no-op cases, retry attempts, explicit step
    ├── test_metric_writer.py      # NEW: coalescing, non-blocking, store down, flush at stop/exit
    └── test_spec.py / test_auditor.py / test_keys.py   # extended (declaration validation, flow record)

waypoint_monitor/
├── app/
│   ├── domain/models.py           # StepMetrics, MetricValue; FlowStep/MetricDecl gain declarations
│   ├── domain/flow.py             # parse optional step `metrics` declarations (bad ones dropped + reported)
│   ├── domain/parsing.py          # METRICS key regex; parse_metrics() -> records + unreadable per run
│   ├── domain/metrics.py          # NEW: pick latest attempt, merge declarations, threshold flag, counts
│   ├── domain/analysis.py         # each step gains `metrics`, `metrics_over`; run gains `metrics_over`
│   ├── infrastructure/store.py    # RecordStore.list_metrics
│   ├── infrastructure/redis_store.py  # SCAN + MGET of `*:metrics:*`
│   └── api/routes.py              # Window.metrics, unreadable counted per run, nothing else new
├── static/js/
│   ├── api.js                     # map step.metrics and flow metric declarations
│   ├── model.js                   # metricsOf(step), metricTrend(runs, step, name, window, min), flag helpers, value formatting
│   ├── ui.js                      # metric badge (label + icon, not colour alone), metric table HTML
│   ├── chart.js                   # reuse drawTrend-style line chart for a metric trend with median and threshold lines
│   └── views/{step,graph,history}.js
├── static/styles.css, static/tests/
├── tests/                         # fakes (list_metrics), seed_demo (sample metrics), test_parsing, test_metrics, test_analysis, test_flow, test_api, test_redis_store
└── README.md                      # metrics section; no new permission
README.md (root), packages/waypoint_etl/README.md, adopting-waypoint-etl skill   # document metric()
```

**Naming note**: the monitor front end already has a function `metric(step)` meaning a step's output count
(`static/js/model.js`). The new concept is called **custom metrics** in code (`stepMetrics`, `metricTrend`,
`metrics_over`) and "Metrics" in the UI, to avoid mixing them up (R9).

**Structure Decision**: Extend the two existing components in place. No new service, package, endpoint or dependency.

## Complexity Tracking

| Departure | Why needed | Simpler alternative rejected because |
|---|---|---|
| Background writer thread for metrics | FR-006: a tight loop must not pay a Redis round trip per call, and a dead Redis must not stall the step (2 s socket timeout) | Writing inline on every call (see SC-003, SC-004). Reusing the event writer was rejected: events are append-only lists with caps; metrics are last-state-wins records that must be coalesced |
| A separate record per step attempt | A running step has no finish record (R1), and attempt-scoping gives "latest attempt wins" for free | Putting metrics in the finish record (invisible while running, FR-007); one record per run (a retry or parallel writer would overwrite other steps' values) |
