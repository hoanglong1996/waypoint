# Implementation Plan: Run Liveness Heartbeat

**Branch**: `009-run-liveness-heartbeat` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-run-liveness-heartbeat/spec.md`

## Summary

Let Waypoint Monitor tell a dead pipeline run from a hung one. The Waypoint library (`packages/waypoint_etl`)
gets a background heartbeat that refreshes one small "alive" item per run every 15 seconds. Waypoint Monitor
(`waypoint_monitor/`) reads that item: an unfinished run whose last beat is older than 90 seconds is judged
**Died**, the monitor records that verdict once as a small "died" item (the monitor's only write), and every later
view of the run shows Died. Runs without a heartbeat behave exactly as today. The front end gets a Died state next
to Running and Stalled.

Read from the code on 2026-10-16: the library writes a flow item, one record per finished step and a 24 h start
marker through `StepAuditor` (`auditor.py`) and `RedisStepAuditStore.write` (`setex`, 2 s timeouts); the monitor
turns those into runs in the pure function `build_runs` (`app/domain/analysis.py`), where an unfinished step is
`running` until `STALL_SECONDS` (900) and `stalled` after; the store interface (`app/infrastructure/store.py`) is read only.
So this plan adds: one library module, two parsers, two store methods (one read, one write), one analysis rule,
one setting, one new card/step state in the front end, and the contract and README updates.

## Technical Context

**Language/Version**: Python 3.12 (monitor, constitution); library supports Python >= 3.10 (`packages/waypoint_etl/pyproject.toml`); ES modules in the browser, no build step

**Primary Dependencies**: `redis` (already used by both); standard-library `threading` for the heartbeat. Nothing added

**Storage**: Redis. Two new key kinds under the existing `waypoint:` prefix: `alive` (written by the library) and `died` (written by the monitor). See [contracts/redis-keys.md](contracts/redis-keys.md)

**Testing**: library: `python -m unittest` under `packages/waypoint_etl/tests` (fake store, short interval); monitor: `python -m unittest discover tests` (fake store) and `node --test static/tests` (pure front-end rules). No live Redis

**Target Platform**: Linux containers (pipeline job, monitor service); modern browsers

**Project Type**: Library plus small web application (API and static front end), both already in this repository

**Performance Goals**: Died shown within 2 minutes of the last beat at defaults (about 90 s + 2 s cache + 5 s refresh); pipeline duration increases by at most 1 s with the store unreachable (SC-001, SC-004)

**Constraints**: The heartbeat never raises into, blocks or outlives the pipeline; items hold identities and times only; monitor writes exactly one kind of item; backward compatible in both directions; mypy strict, ruff, black (line length 100)

**Scale/Scope**: About 3 to 20 pipelines, 2 environments, 30 runs per view; one alive item per active run (overwritten), at most one died item per run

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status |
|---|---|
| I. Layered architecture | Pass. `waypoint_monitor` keeps its own split: judgement logic in `app/domain/`, Redis access in `app/infrastructure/`, wiring in `app/api/`. The library change is one self-contained module. |
| II. Caller PII protection | Pass. The alive and died items hold pipeline, environment, run id and timestamps only (FR-002, FR-007b). No item contents, no free text, no exception messages. |
| III. Type safety and quality | Applies. New code is fully typed and must pass `mypy`, `ruff check`, `black` in `waypoint_monitor/` and in `packages/waypoint_etl/` before merge. |
| IV. Test coverage | Pass by plan: unit tests for the heartbeat, parsing, judgement rules, the verdict write and the routes, plus front-end rule tests; no live services. A regression test pins the legacy no-heartbeat behaviour (SC-003). |
| V. Resilient, observable execution | Pass. The heartbeat swallows and logs store errors; a failed verdict write never fails a request (FR-004, FR-007d). Not a pipeline load, so the re-run rule does not apply; the verdict write is idempotent (`SET NX`). |

Deliberate change to a project rule outside the constitution: the monitor stops being strictly read-only (one
permitted write, FR-007c). It is recorded in the README and its security note, and in Complexity Tracking.

Gate result: pass. Re-checked after Phase 1 design: still pass.

## Project Structure

### Documentation (this feature)

```text
specs/009-run-liveness-heartbeat/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── redis-keys.md    # new `alive` and `died` items (extends specs/007 contract)
│   └── api.md           # new fields on /api/runs, /api/overview, /api/config
├── checklists/requirements.md
└── tasks.md             # created later by /speckit-tasks
```

### Source Code (repository root: `integrations/callraill/`)

```text
packages/waypoint_etl/                 # the library (writer)
├── pyproject.toml                     # version 0.1.0 -> 0.2.0
├── README.md                          # document heartbeat_seconds and the alive item
├── src/waypoint_etl/
│   ├── keys.py                        # alive_key()
│   ├── heartbeat.py                   # NEW: Heartbeat thread (start/stop, never raises)
│   ├── auditor.py                     # StepAuditor owns a Heartbeat
│   ├── registry.py                    # init(heartbeat_seconds=...), clear() stops it
│   └── __init__.py                    # __version__
└── tests/test_heartbeat.py            # NEW

waypoint_monitor/                      # the monitor (reader, plus the one verdict write)
├── app/config.py                      # HEARTBEAT_DEAD_SECONDS (default 90)
├── app/domain/models.py               # AliveSignal, DiedVerdict
├── app/domain/parsing.py              # parse_alive, parse_died, key patterns
├── app/domain/analysis.py             # judge Died, `died` state, run.died, card inputs
├── app/domain/overview.py             # card_status "died", needs attention, summary fields
├── app/infrastructure/store.py        # list_alive, list_died, record_died in RecordStore
├── app/infrastructure/redis_store.py  # scan alive/died, SET NX PX with the alive item's remaining TTL
├── app/api/routes.py                  # read the two new lists, write verdicts, /api/config field
├── static/js/{api,model,graph-model}.js, static/js/views/{home,latest,step,graph}.js, static/styles.css
│                                      # Died state, "last seen" text
├── README.md                          # keys, setting, "one permitted write", security note
└── tests/                             # test_parsing, test_analysis, test_overview, test_api, test_redis_store, fakes
    static/tests/                      # model, graph-model, overview rule tests
```

**Structure Decision**: No new project and no new service. The library gains one module; the monitor keeps its
`domain / infrastructure / api` split, and the front end keeps its plain ES modules. The key contract lives with
this feature (`contracts/redis-keys.md`) and extends `specs/007-rename-to-waypoint/contracts/redis-keys.md`.

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Monitor makes one write (the died verdict) | FR-007a/b require Died to survive monitor restarts and several instances (clarification 2, option A). | In-memory only loses the verdict on restart and differs per instance (rejected by the user). A separate checker job adds a component to deploy. |
| Background thread in the library | A heartbeat must continue while a step blocks the main thread; that is the hung versus dead signal. | Beating from step boundaries only cannot tell a long step from a dead process. |
