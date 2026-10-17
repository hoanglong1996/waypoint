# Quickstart: validating the map step

Validation guide, not implementation. Contracts: [redis-keys](contracts/redis-keys.md), [library-api](contracts/library-api.md),
[api](contracts/api.md), [ui](contracts/ui.md). Data shapes: [data-model](data-model.md).

## Prerequisites

- Python 3.12 with the monitor's virtualenv (`waypoint_monitor/.venv`), Node 20+ for the front-end tests.
- A local Redis (`redis-server`) on `localhost:6379`, or the fake store the tests use.
- Library installed in editable mode: `pip install -e "packages/waypoint_etl[redis]"`.

## 1. Automated checks

```bash
cd packages/waypoint_etl && python -m unittest discover tests && ruff check . && black --check . && mypy --strict src
cd waypoint_monitor && python -m unittest discover tests && ruff check . && black --check . && mypy --strict app
cd waypoint_monitor && node --test static/tests/*.test.mjs
```

Expected: all green, including the new `test_maps`, `test_map_scopes`, `test_map_writer`, `test_spec_map` (library),
`test_maps_parsing`, `test_maps_domain`, map cases in `test_api`, `test_flow`, `test_analysis` (monitor) and `map-model.test.mjs`.

## 2. Library scenarios (maps to spec stories 1, 2, 5, 6)

Run each against a fake store or Redis; check the records named in the redis-keys contract.

| Scenario | Do | Expect |
|---|---|---|
| Plain loop | `map_step("accounts")` around a `for`, `item(id)` around fetch, transform, load (10 items) | 10 item records, aggregate `started=10, done=10`, step record `output=10` |
| Thread pool | Same with `ThreadPoolExecutor(5)` and `item()` inside the worker | Every record's inner steps match its key; no mixing (run 50 times) |
| Asyncio | `asyncio.gather` of 10 coroutines, each `with item(id)` | Same as above |
| One item fails | `transform` raises for `acct-7`, loop collects the error | Item `failed`, failed step `transform`, later step `not run` in the item view, aggregate `failed=1`, block ends normally |
| Block raises | Exception leaves `map_step` | Failure item for the map step, aggregate still written |
| Duplicate key | Start `acct-1` twice | First record kept, one warning, aggregate `started` counts it once |
| Bad key | `item("a b@c")`, `item("")`, a 100-character key | Stored as `a_b_c`, `item_N`, 64 characters; one warning each |
| No scope | `item("x")` with no open map block, `init` never called | Nothing recorded, nothing raised |
| Store down | Point at a closed port | Loop result and exit code identical to a run without Waypoint |
| Hot loop | 100,000 `waypoint_etl.metric` calls inside an item | Added time ≤ 5% (SC-005); at most one write per second |
| Big loop | 10,000 items, 1 in 20 fails, a few slow | Item records: 1,000 + failed beyond the limit (≤ 1,000, compact) + 50 slowest; aggregate counts exactly 10,000; Redis key count and bytes within the documented bound |
| All fail | 10,000 items all fail | Failed records stop at 1,000 more; `failed_without_record` counts the rest |
| 0.5.0 code | A pipeline with no map step | Records identical to 0.5.0 |

## 3. Monitor scenarios (stories 1, 3, 4, 6)

Seed data with `python -m tests.seed_demo` (extended with a running map run, a failed map run, a 10,000-item run and a run from a
pre-map library), then start the monitor (`uvicorn app.main:app`) and check:

1. `GET /api/runs?env=prod&pipeline=callrail`: the map step has `map` with correct `counts`; a map failed through items has
   `state: failed` with `ItemsFailed`; the run is `incomplete` (swallowed errors) or `Failed` (block raised).
2. `GET …/maps/accounts/items?state=failed`: only failed items, deterministic order; `limit=2` then `after=next` repeats nothing.
3. `GET …/maps/accounts/items?slow=1&sort=duration`: slow items, slowest first; with fewer than 5 finished items nothing is slow.
4. `GET …/maps/accounts/items/acct-7`: inner steps in order, `not_run` after the failed one; 404 for an item beyond the limit.
5. `GET …/events?item=acct-7`: only that item's events.
6. The 10,000-item run: `/api/runs` answers in the same time as a run without a map (no item keys read); the item list first
   page answers in under 1 s.
7. A run written by the previous library and a flow with no map step: identical JSON to before (golden test).
8. Redis `MONITOR` or the fake store's call log while loading `/api/runs`: no `SCAN` pattern matches an item key.

## 4. Browser pass (stories 1 to 5)

Start the monitor against the seeded Redis; use the browser tool for screenshots at 1280 px and 390 px.

1. Run with a running map (6 done, 4 running): the node shows `6 done · 4 running · 0 failed`; it updates on the next refresh.
2. Select the map node: the panel shows summary, item flow strip and item list; the failed chip is selected when items failed.
3. Search `acct-7`, filter `Slow`, sort by duration, `Show more`: no repeats, counts stay correct.
4. Open the failed item: inner steps in order, error block with trace, `not run` for the later step, metrics and events of that item.
5. Open the 10,000-item run: usable in under 3 s, notice `Showing items with a record…`, no per-item DOM beyond one page.
6. A map key containing `<img src=x onerror=alert(1)>` in an error message renders as text (the key itself is sanitised before storage).
7. Pre-map run and a run with no map: display unchanged.
8. Keyboard only: reach the chips, the sort control and a row, open and close the item view; screen reader names match the
   contract.

## 5. Compatibility

- New monitor with the 0.5.0 library: no errors or banners (SC-008).
- Old monitor (spec 013 build) with the 0.6.0 library: the map step appears as one ordinary step; no error; item keys never read.
- Rollback: pipelines can drop back to 0.5.0 with no data cleanup; the new keys simply expire with their run.

## 6. Done when

All spec success criteria SC-001 to SC-010 have a passing check above or in the automated suites, and the root README, the
library README, the monitor README and the `adopting-waypoint-etl` skill describe `map_step()` and `item()`, the limits and the
"ids only" rule for item keys.
