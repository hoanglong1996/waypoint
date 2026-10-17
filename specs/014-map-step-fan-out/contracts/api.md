# Contract: Monitor HTTP API

Read only. Existing routes keep their shapes; additions are optional fields and two new routes. Same error shape as today
(`{"error": "…"}`; 400 for bad input, 503 when the store is unreachable).

## `GET /api/runs` (extended)

A step of a run that is a map step carries `map` (absent for ordinary steps and for map steps from older libraries):

```json
{ "name": "accounts", "state": "failed",
  "error": { "type": "ItemsFailed", "message": "1 of 10 items failed", "traceback": "" },
  "map": {
    "state": "failed",
    "counts": { "started": 10, "running": 0, "done": 9, "failed": 1 },
    "in_total": 480, "out_total": 455, "lost_items": 0,
    "concurrency_limit": 5, "over": "list_accounts",
    "loop_seconds": 41,
    "duration": { "count": 10, "median_ms": 3900, "p95_ms": 9100, "approx": true, "enough": true },
    "slowest": [ { "key": "acct-7", "ms": 9120 } ],
    "failed_items": [ { "key": "acct-7", "step": "transform", "error_type": "ValueError" } ],
    "inner": [ { "name": "fetch", "running": 0, "done": 10, "failed": 0, "in": 10, "out": 480 } ],
    "detail": { "partial": false, "kept": 10, "failed_without_record": 0 },
    "unreadable": 0 } }
```

- `state` follows research R6: `running` while the block is open (also while items have failed), then `failed` or `done`; a
  stalled or died run reports the run's state.
- When the map step failed only through items, `error` is the synthetic `ItemsFailed` (numbers only, empty trace) and the run's
  `failed` object and status follow the existing rules. A real failure item (the block itself raised) replaces it.
- `duration.enough` is false (and `median_ms`/`p95_ms` null) when fewer than `duration_min_runs` items finished. `approx` is
  always true (histogram, within 5%).
- `slowest` ≤ 5, `failed_items` ≤ 20 (in arrival order). `detail.partial` is true when more items started than have records.
- The run's `flow.steps[i]` of a map step gains `map: { "over": …, "max_concurrency": …, "steps": [flow step, …] }` (inner
  steps use the existing flow step shape, including declared `metrics`). Inner steps are not in `flow.steps`.
- A damaged aggregate is skipped and counted in the run's `unreadable`.
- `/api/overview`, `/api/pipelines` and History read the same runs: a map step failed through items counts as a failed step, no new state.

## `GET /api/runs/{pipeline}/{env}/{run_id}/maps/{map}/items`

Query: `state` (`failed|running|done`, optional), `slow` (`1`, optional), `q` (substring of the item key, **case-insensitive**, ≤ 64),
`sort` (`index` default, `duration`, `key`; `key` is a **natural** sort, so `acct-2` comes before `acct-10`), `order` (`asc` default, `desc`; for `duration` the default is `desc`), `failed_first` (`1`, optional: failed items sort before all others, then the chosen sort; used by the All view of a failed map step),
`limit` (default 50, 1 to 200), `after` (cursor from the previous page).

```json
{ "env": "prod", "pipeline": "callrail", "run_id": "20261017T020301Z", "map": "accounts",
  "generated_at": "2026-10-17T02:05:13Z",
  "state": "running",
  "total": 10, "with_record": 10,
  "counts": { "failed": 1, "running": 4, "done": 5 },
  "partial": false, "failed_without_record": 0,
  "matched": 4, "has_more": false, "next": null,
  "items": [ { "key": "acct-7", "index": 7, "state": "failed", "slow": true,
               "started_at": "2026-10-17T02:04:21Z", "duration_ms": 9120,
               "failed_step": "transform", "error_type": "ValueError", "in": 48, "out": null, "loss": false,
               "compact": false } ],
  "unreadable": 0 }
```

- `total` = all items that started (from the aggregate); `with_record` = items with a record; `counts` are over the records read
  (not the filtered set); `matched` = records matching the filters.
- Ordering is `failed_first` (when set), then the chosen sort value, then `index`, then `key`: total and deterministic. `next` is an opaque cursor (sort value
  + index); passing it as `after` continues strictly after that position, so no item repeats. An item that changes sort value
  between pages can be skipped in that pass, never shown twice.
- `slow` per item: duration above `slow_run_multiple × median` when the aggregate's `duration.enough`, else false. The `slow=1`
  filter uses the same rule. A running item has no duration yet: it is slow when its elapsed time (now minus `started_at`) exceeds the same threshold, and its row then carries the elapsed time in `elapsed_ms`.
- Items stored as `running` in a stalled or died run are reported with `state` `stalled` or `died` (research R12).
- 400: unknown env, bad pipeline, run id or map name, bad `state`, `sort`, `order`, `limit` or `after`. An unknown run or map
  gives 200 with `total: 0` and empty `items` (the same leniency as the events route).
- Cost: one `SCAN` on the run-and-map prefix and pipelined `MGET` (at most ~2,050 keys), cached for `cache_seconds`.

## `GET /api/runs/{pipeline}/{env}/{run_id}/maps/{map}/items/{key}`

One item for the item view; 404 `{"error": "Item not found"}` when it has no record (the screen then explains beyond-limit items).

```json
{ "key": "acct-7", "index": 7, "state": "failed", "slow": true, "compact": false,
  "started_at": "…", "finished_at": "…", "duration_ms": 9120,
  "steps": [
    { "name": "fetch", "state": "done", "inputs": [ { "name": "account", "value": 1 } ], "output": 48,
      "duration_ms": 2300, "loss": false },
    { "name": "transform", "state": "failed", "inputs": [ { "name": "rows", "value": 48 } ], "output": null,
      "duration_ms": 6820, "error": { "type": "ValueError", "message": "bad date", "traceback": "…" },
      "metrics": [ { "name": "rejected", "label": null, "unit": "rows", "value": 4, "over": false } ] },
    { "name": "load", "state": "not_run" } ],
  "error": null }
```

`steps` follows the map's declared item flow in order; a declared step with no result is `not_run` (item failed or ended) or
`waiting` (item running); a result for an undeclared step is added with `unplanned: true`. Metrics use the spec 013 shape and
the declared thresholds of the flow. Item events are read with the events route below.

## `GET /api/runs/{pipeline}/{env}/{run_id}/events` (extended)

New optional query parameter `item` (an item key). Only events with that `item` are returned; `total`, `matched`, `has_more`
follow the filtered set. Events carry `item` when the library recorded one. Unknown key: empty result.

## Settings

No new setting. Slow and percentile rules reuse `SLOW_RUN_MULTIPLE` and `DURATION_MIN_RUNS`. `/api/config` is unchanged.
