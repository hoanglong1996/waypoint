# Implementation Plan: Run Duration and Run Events

**Branch**: `012-duration-and-run-events` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/012-duration-and-run-events/spec.md`

## Summary

Two additions to both halves of Waypoint: the pipeline library (`packages/waypoint_etl`, writes) and Waypoint
Monitor (`waypoint_monitor`, reads and shows).

**Duration (roadmap 2)** is mostly a monitor feature. Read from the code on 2026-10-17:

- A run's duration is already computed (`analysis.py::_build_run`: `ended - started`, with the run id as start).
- A step's **own start time is not in its finish record** (`auditor.py::finish` writes only `finished_at`). The only
  source is the start marker, which expires after 24 h (`START_MARKER_TTL_SECONDS`), plus failure items (spec 011).
  So exact step durations for completed runs need a small library change (finish record gains `started_at` and
  `duration_ms`), and runs from library 0.2.0/0.3.0 get **approximate** step durations derived from the previous
  step's end (steps are sequential). This corrects an assumption of the first draft of the spec (amended there).
- New monitor module computes typical (median, p95) durations per pipeline and environment, the "Slower than usual"
  flag, and the bottleneck step. The front end gains durations on the run page, graph, Home card and History.

**Events (roadmap 3)**: automatic events (run started, step started/finished/failed, run died/stalled) are
**derived by the monitor** from records that already exist, so they appear for every library version and cost no
Redis writes. Only author-sent events need new data:

1. **Library `0.4.0`**: `waypoint_etl.log/warn/error(...)`; events go through a non-blocking in-process queue to a
   background writer thread (same pattern as the heartbeat) that pushes them to three capped Redis lists per run.
2. **Monitor**: reads event counts cheaply for cards and History, and the events of one run on demand through a new
   endpoint `GET /api/runs/{pipeline}/{env}/{run_id}/events` that merges recorded and derived events into a
   timeline (filter by level and step, paging).
3. **Front end**: an Events tab on the run page, a step's events in its details, warning/error counts on Home and
   History.

One new Redis permission for the monitor: `LRANGE` and `LLEN` (read only). The monitor still writes only the `died`
verdict. Existing keys and records only gain optional fields, so older monitors and older libraries keep working.

## Technical Context

**Language/Version**: Library: Python 3.10+, standard library only (`redis` stays an optional extra). Monitor: Python 3.12, FastAPI. Front end: ES modules, no build step.

**Primary Dependencies**: none added anywhere.

**Storage**: Redis. New per run: three lists `waypoint:{pipeline}:{env}:{run_id}:events:{info|warning|error}` (JSON elements, capped with `LTRIM`, TTL = the run's `ttl_days`). Finish records gain optional `started_at`, `duration_ms`. Written only by the library; the monitor never writes them.

**Testing**: Library `python -m unittest discover tests`; monitor `python -m unittest discover tests`; front end `node --test static/tests/*.test.mjs`; manual browser pass from [quickstart.md](quickstart.md).

**Target Platform**: Pipelines in Docker on any host; monitor container; modern desktop and phone browsers.

**Project Type**: Python library + web application (small API plus static front end), both already in this repository.

**Performance Goals**: Sending an event costs microseconds on the caller (queue put, never a network call) and at most 5% added run time at 5,000 events (SC-006). Events appear within one refresh (5 s) plus the 2 s server cache (SC-004). First page of a 500-event timeline under 2 s (SC-009): one `LRANGE` per list for one run only.

**Constraints**: Monitoring never changes a step's outcome (FR-017/018); events never block beyond a small bound (queue, bounded flush at exit ≤ 2 s); no data content stored (FR-022); message capture setting and cleaning function shared with error messages (FR-022); monitor read-only except the existing verdict (FR-033); old and new library/monitor combinations interoperate (FR-031, FR-035).

**Scale/Scope**: About 3 to 20 pipelines, 2 environments, tens of steps, up to 100 runs per request. Per run: at most 900 stored events (500 + 200 + 200), each ≤ ~1 KB.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the CallRail ETL constitution copied into this repository, not a Waypoint
one (as in specs 009 to 011). Its principles are applied by analogy:

| Principle | Status |
|---|---|
| I. Layered architecture | Pass. Monitor: pure parsing, durations and timeline in `domain/`, Redis reads in `infrastructure/`, HTTP in `api/`. Library: queue and writer in their own module, separate from keys, auditor, decorator. |
| II. PII protection (non-negotiable) | Pass by design. Event text and text values obey the same `capture_error_message` / `redact` settings as failures; numbers and short text only; lengths capped on write and again on read; front end escapes everything. See [research.md](research.md) R7, R11. |
| III. Type safety and quality | Pass by plan: all new Python fully typed; `mypy --strict`, `ruff`, `black` (line length 100) on both packages. |
| IV. Test coverage | Pass by plan: unit tests for every new behaviour in both packages, regression tests for "old runs unchanged", front-end model tests. |
| V. Resilient, observable execution | Pass. Sending an event can never raise or block; writer errors are caught and logged at most once a minute; the queue is bounded; nothing here changes the exit code or the step's result. Keys expire with the run. |

Gate result: pass. Re-checked after Phase 1 design: still pass. One departure to justify below (new Redis read
permission).

**Re-checked against the final code (2026-10-17)**: typing pass (`mypy --strict`, `ruff`, `black` clean on both packages);
tests cover every new behaviour and the old-run regressions (library 178, monitor 341, front end 148); PII: the shared
`capture_error_message`/`redact` setting is tested end to end (marker never stored, SC-010), text is capped on both
sides and escaped in the page; resilience: `log` never raises or waits on the network (tested with a raising and a
hanging store, and by hand with Redis down), the queue and the stored lists are bounded, and keys expire with the run.

## Project Structure

### Documentation (this feature)

```text
specs/012-duration-and-run-events/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── redis-keys.md      # event lists, finish-record additions
│   ├── library-api.md     # log/warn/error, init behaviour, guarantees
│   ├── api.md             # durations, typical, counts, the events endpoint, new settings
│   └── ui.md              # what the operator sees
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
packages/waypoint_etl/
├── pyproject.toml                 # version 0.4.0
├── README.md                      # log/warn/error, privacy note, durations in finish records
├── src/waypoint_etl/
│   ├── keys.py                    # events_key(level)
│   ├── events.py                  # NEW: build an event, limits, non-blocking queue, writer thread, flush
│   ├── stores.py                  # RedisStepAuditStore.push_events (RPUSH+LTRIM+EXPIRE); optional on other stores
│   ├── auditor.py                 # finish() adds started_at, duration_ms (monotonic); current step; owns the writer
│   ├── decorator.py               # sets/clears the current-step context (sync and async)
│   ├── registry.py                # log/warn/error entry points; clear() flushes the writer
│   └── __init__.py                # exports log, warn, error; __version__ = "0.4.0"
└── tests/
    ├── test_events.py             # NEW: limits, redaction, levels, step attach, no-op cases, threads, caps
    ├── test_event_writer.py       # NEW: non-blocking, store down, flush at clear/exit, queue overflow
    └── test_auditor.py / test_keys.py / test_stores.py   # extended

waypoint_monitor/
├── app/
│   ├── config.py                  # SLOW_RUN_MULTIPLE, DURATION_WINDOW_RUNS, DURATION_MIN_RUNS
│   ├── domain/models.py           # RunEvent, EventCounts; StepRecord gains optional started_at, duration_ms
│   ├── domain/parsing.py          # parse the new finish fields; parse_events(); event key regex
│   ├── domain/durations.py        # NEW: step/run durations, approximate rule, typical, slow, bottleneck
│   ├── domain/timeline.py         # NEW: derive automatic events, merge, filter, page, dropped note
│   ├── domain/analysis.py         # calls durations; run gains duration, bottleneck, event_counts
│   ├── domain/overview.py         # latest.duration_*, slow, warnings, errors
│   ├── infrastructure/store.py    # RecordStore.list_event_counts, read_events
│   ├── infrastructure/redis_store.py  # SCAN names + pipelined LLEN; LRANGE for one run (read only)
│   └── api/routes.py              # events endpoint, typical in /api/runs, counts plumbed, config
├── static/js/
│   ├── api.js, model.js           # durations, typical, slow, bottleneck, counts, events mapping, duration format
│   ├── graph-model.js, ui.js      # duration labels, bottleneck marker, level icons and pills
│   ├── chart.js                   # duration-over-time chart
│   ├── router.js                  # run page tab and events filters in the hash query
│   └── views/{run,step,graph,home,history}.js, views/events.js (NEW)
├── static/styles.css, static/tests/   # new styles; tests for model, events view, router
├── tests/                         # fakes, seed_demo, parsing, durations, timeline, analysis, overview, api, redis_store
└── README.md                      # durations, Events, new settings, new read permission
README.md (root), deploy/README.md # permission line (LRANGE, LLEN), 0.4.0 install URL
```

**Structure Decision**: Extend the two existing components in place. No new service, package or dependency.

## Complexity Tracking

| Departure | Why needed | Simpler alternative rejected because |
|---|---|---|
| Background writer thread with a bounded queue in the library | FR-018: sending an event must never wait on the network; thousands of events must not slow the step (SC-006) | Writing to Redis inline costs a round trip (up to the 2 s socket timeout when Redis is down) on every call |
| New monitor read permission (`LRANGE`, `LLEN`) | Events are lists so that any process can append atomically and the cap keeps the oldest-dropped rule | One JSON key per event (more keys, heavier `SCAN` on every refresh) or a single JSON document (child processes overwrite each other); see [research.md](research.md) R2 |
| Three lists per run instead of one | Cheap warning/error counts for Home and History (`LLEN`), and the rule "oldest info dropped first, warnings and errors kept" with plain `LTRIM` | One list cannot drop only info events atomically without a script (extra permission) |
