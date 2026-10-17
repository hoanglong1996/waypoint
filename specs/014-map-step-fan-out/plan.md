# Implementation Plan: Map Step (Loop Inside a Pipeline)

**Branch**: `014-map-step-fan-out` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/014-map-step-fan-out/spec.md`

## Summary

A loop becomes a **map step**: an ordinary step that also owns many **items**, each running a short, linear
**item flow** of inner steps. Pipeline library (`packages/waypoint_etl`) writes; Waypoint Monitor
(`waypoint_monitor`) reads and shows. Read from the code on 2026-10-17:

- Today the library assumes steps run one after another: `StepAuditor` keeps one counter `_index`, one `_open` map,
  `_latest_index` by step name and `current_open_step()` returns the single open step (`auditor.py`). Inner steps
  repeat the same names for every item and run in parallel, so they cannot share that state. **Decision:** the map
  step block is an *ordinary step* at run level (same start marker, finish record or failure item as any step), and
  everything per item lives in a **separate item tracker** with its own counters, locked, keyed by item
  ([research.md](research.md) R1, R2).
- The existing `@audited_step` decorator stays unchanged for authors. `begin`, `finish` and `fail` on the auditor
  look at a context variable `current_item` (like `current_step` in `events.py`, right per thread and per asyncio
  task) and route to the item when set. Authors add **two lines**: `with waypoint_etl.map_step("accounts"):` around
  the loop and `with waypoint_etl.item(key):` around one pass (R2).
- **Scale rule: the monitor's existing scans must never see item keys.** `list_records`, `list_markers`,
  `list_failures`, `list_metrics` each `SCAN` and `MGET` every matching key on every refresh. Item data therefore
  goes to **two new key families that no existing pattern matches**: one small *aggregate* per map step
  (`...:map:{map}`, read with the run list) and one record per *detailed* item (`...:item:{map}:{key}`, read only by
  the item endpoints, one run and one map at a time). An older monitor ignores both families (R3, FR-029).
- The library merges everything in memory and a background writer (same shape as the metric writer) writes changed
  records at most once a second, in one pipelined batch. A hot loop costs dictionary updates under a lock, never a
  network call (FR-007, SC-005) (R4).
- **Bounded Redis footprint (FR-011, SC-004):** the first 1,000 items keep a full record; beyond that only failed
  items (up to 1,000 more, compact: no stack trace) and the 50 slowest keep a record. A displaced slow record is
  overwritten with `SETEX … 1` so it expires at once: no new Redis permission (R5). The aggregate holds exact counts
  for all items, per-inner-step counts, in/out sums, a small log-scale duration histogram (median and 95th
  percentile within 5%), the 5 slowest and the first 20 failures.
- The monitor derives a map step's state from its aggregate: a map step with `failed ≥ 1` is **Failed** through a
  synthetic failure (`ItemsFailed`, "3 items failed", no stack trace) added to the same `current failures` set that
  real failures use, so run status, "needs attention", History and the graph treat it exactly like any failed step
  (FR-014, FR-027) (R6).
- `/api/runs` carries a compact `map` summary on the step; two new endpoints serve the item list (filter by state,
  slow, key text; sort; stable paging) and one item's detail. The UI adds a progress node, a map panel with the
  item list, and an item view; item events reuse the events endpoint with a new `item` filter (R7, R8).

Library ships as `0.6.0`. The monitor works before any pipeline is upgraded (FR-029). Flow record `v` stays 1.

## Technical Context

**Language/Version**: Library: Python 3.10+, standard library only (`redis` stays an optional extra). Monitor: Python 3.12, FastAPI. Front end: ES modules, no build step.

**Primary Dependencies**: none added anywhere.

**Storage**: Redis. New per run and map step: one aggregate JSON string `...:{run_id}:map:{map}` and up to ~2,050 item JSON strings `...:{run_id}:item:{map}:{key}` (TTL = the run's `ttl_days`, refreshed on every write). Flow record gains an optional step `kind: "map"` with its item flow. Written only by the library; monitor read-only.

**Testing**: Library `python -m unittest discover tests`; monitor `python -m unittest discover tests`; front end `node --test static/tests/*.test.mjs`; manual browser pass from [quickstart.md](quickstart.md).

**Target Platform**: Pipelines in Docker on any host; monitor container; modern desktop and phone browsers.

**Project Type**: Python library + web application (small API plus static front end), both already in this repository.

**Performance Goals**: `item()` and inner-step recording are locked dictionary updates (no I/O); at most one pipelined write per second per map step. The run list adds one `SCAN`+`MGET` pass for aggregates (one small key per map step per run). Item list first page for 1,000 items under 1 s (SC-009): one `SCAN` on a run-and-map prefix plus pipelined `MGET`, cached `cache_seconds`. Run page with a 10,000-item map under 3 s (SC-004): the run list never touches item keys; the front end draws no item nodes except one page of the list.

**Constraints**: Recording never changes a step's outcome and never waits on the network (FR-007); only names, keys, numbers, times and short diagnostic text are stored (FR-008); monitor read-only toward item data (FR-031); old and new library/monitor combinations interoperate (FR-029, FR-030); no new Redis permission for either account.

**Scale/Scope**: 3 to 20 pipelines, 2 environments, ≤ 100 steps (inner steps count toward the existing limit of 100 per flow, at most 20 per map step), maps up to ~10,000 items, at most 1,000 full + 1,000 compact-failed + 50 slow item records per map step per run (≈ 1 to 6 MB worst case, typically under 2 MB).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is the CallRail ETL constitution copied into this repository, not a Waypoint one
(as in specs 009 to 013). Its principles are applied by analogy:

| Principle | Status |
|---|---|
| I. Layered architecture | Pass. Monitor: pure parsing, summary, filtering and paging in `domain/maps.py`, Redis reads in `infrastructure/`, HTTP in `api/`. Library: item tracking and writer in their own module (`maps.py`), separate from keys, auditor and decorator. |
| II. PII protection (non-negotiable) | Pass by design, with one real risk named. An **item key** is chosen by the author and could be a name by mistake. Mitigations: keys are limited to `[A-Za-z0-9_.-]{1,64}` (no spaces, `@`, or other characters an email or a name usually needs; invalid characters become `_`), documented as "ids or indices only", escaped everywhere in the UI. Error text in items follows the existing `capture_error_message` and `redact` settings and is cut to 200 characters (compact) or the existing limits (full); stack traces hold frames only. Metric names and values follow spec 013. Nothing from pipeline items' contents is read. See R9. |
| III. Type safety and quality | Pass by plan: all new Python fully typed; `mypy --strict`, `ruff`, `black` (line length 100) on both packages. |
| IV. Test coverage | Pass by plan: unit tests for every new behaviour in both packages (threads, async, limits, duplicate keys, no-op cases, writer coalescing, parsing, overlay, paging, old-run regressions) and front-end model tests. |
| V. Resilient, observable execution | Pass. Every new library entry point catches everything and logs at most once per cause; queue and record sizes are bounded; keys expire with the run; nothing changes the exit code or a step's result. Re-running a pipeline writes new keys under a new run id, so loads stay re-runnable. |

Gate result: pass. Re-checked after Phase 1 design: still pass. No new Redis permission, no new dependency, no new
service. Departures are justified below.

## Project Structure

### Documentation (this feature)

```text
specs/014-map-step-fan-out/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── redis-keys.md      # aggregate and item records, flow-record addition, event `item` field
│   ├── library-api.md     # MapStepSpec, map_step(), item(), guarantees, limits
│   ├── api.md             # `map` on steps in /api/runs, items list, item detail, events `item` filter
│   └── ui.md              # what the operator sees
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
packages/waypoint_etl/
├── pyproject.toml                 # version 0.6.0
├── README.md                      # map_step(), item(), MapStepSpec, limits, per-process note
├── src/waypoint_etl/
│   ├── keys.py                    # map_key, item_key; MAP_* and ITEM_* limits; write batching constants
│   ├── spec.py                    # MapStepSpec; PipelineSpec.steps may hold StepSpec | MapStepSpec; validation (FR-010)
│   ├── maps.py                    # NEW: key sanitising, ItemState, MapTracker (counters, histogram, retention), MapWriter
│   ├── auditor.py                 # flow record carries map steps; begin/finish/fail/record_metric/send_event route to the item when `current_item` is set; open/close map block; owns writer
│   ├── scopes.py                  # NEW: map_step() and item() context managers (sync and async), current_item/current_map variables
│   ├── events.py                  # build_event: optional `item` field
│   ├── stores.py                  # optional write_many (pipelined SETEX); fallback loop
│   ├── registry.py                # map_step(), item() entry points; log() adds the item
│   └── __init__.py                # exports map_step, item, MapStepSpec; __version__ = "0.6.0"
└── tests/
    ├── test_maps.py               # NEW: counters, retention, duplicates, key sanitising, histogram
    ├── test_map_scopes.py         # NEW: threads, asyncio, nested/missing scopes, no-op cases
    ├── test_map_writer.py         # NEW: coalescing, batching, store down, evict-by-TTL, flush at stop
    ├── test_spec_map.py           # NEW: validation (duplicates, empty, nested, branches)
    └── test_auditor.py / test_decorator.py / test_events.py   # extended (routing, item field, unchanged behaviour)

waypoint_monitor/
├── app/
│   ├── domain/models.py           # MapDecl, MapAggregate, ItemRecord, ItemStepResult
│   ├── domain/flow.py             # parse optional step `kind: "map"` and its item flow (bad parts dropped + reported)
│   ├── domain/parsing.py          # MAP and ITEM key regexes; parse_maps(), parse_items(); event `item` field
│   ├── domain/maps.py             # NEW: summary, percentile from histogram, slow rule, state overlay, filter/sort/page, item detail
│   ├── domain/analysis.py         # step.map summary; synthetic ItemsFailed failure; flow json carries `map`
│   ├── domain/timeline.py         # select(): optional `item` filter
│   ├── infrastructure/store.py    # RecordStore.list_maps, list_items
│   ├── infrastructure/redis_store.py  # SCAN + MGET of `*:map:*`; SCAN of one run-and-map prefix for items
│   └── api/routes.py              # Window.maps; /maps/{map}/items and /items/{key}; events `item` param
├── static/js/
│   ├── api.js                     # map step.map and flow map decl; fetchItems(), fetchItem()
│   ├── model.js                   # mapProgress(), itemState helpers, plain-text formatting
│   ├── graph-model.js             # map node states and aria text (the layout is unchanged: one node per step)
│   ├── ui.js                      # map progress pill, item state pill, partial-detail notice
│   └── views/{graph,step,run,events}.js + views/map.js (NEW: map panel, item list, item view)
├── static/styles.css, static/tests/map-model.test.mjs (NEW)
├── tests/                         # fakes (list_maps, list_items), seed_demo (sample map runs), test_maps_parsing, test_maps_domain, test_flow, test_analysis, test_api, test_redis_store
└── README.md                      # map step section; no new permission
README.md (root), packages/waypoint_etl/README.md, adopting-waypoint-etl skill   # document map_step() and item()
```

**Structure Decision**: Extend the two existing components in place. No new service, package, endpoint family
beyond two read-only item routes, or dependency.

## Complexity Tracking

| Departure | Why needed | Simpler alternative rejected because |
|---|---|---|
| Two new key families instead of reusing step, failed and metrics keys | The monitor `SCAN`s and `MGET`s every key of its existing patterns on each refresh; 10,000 items × several inner steps would make every run list read tens of thousands of keys (SC-004) | Reusing `...:step:{NN}-{step}` with an item suffix: the old monitor would read and mis-draw them, and every refresh would pay for items nobody opened |
| A background writer thread with a pipelined batch (`write_many`) | FR-007: item start, each inner step and item end are many writes; a dead Redis must not stall the loop (2 s socket timeout) | Writing inline per call (the way ordinary steps are written): fine for tens of steps, wrong for thousands of items |
| Synthetic `ItemsFailed` failure in the monitor | A loop may swallow item errors and finish normally, so no real failure item exists, yet FR-014 requires Failed | A new run state: FR-027 forbids new states and every view would change |
| Histogram for percentiles | Exact percentiles over 10,000 items would need every duration in the aggregate record, rewritten each second | Keeping all durations: ~60 KB per rewrite; sampling: unbounded error on small maps |
| Rewriting a displaced slow record with a 1-second TTL | The library has no `DEL` permission and must keep the slow set at 50 | Leaving displaced records: unbounded in the worst case (loop with rising durations); asking for `DEL`: a new permission |
