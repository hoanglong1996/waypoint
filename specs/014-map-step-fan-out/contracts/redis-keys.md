# Contract: Redis keys

All keys under the `waypoint:` prefix. Written only by the library; the monitor reads only.

## New: map aggregate

```
waypoint:{pipeline}:{env}:{run_id}:map:{map}
```

`{map}` is the map step's name (`^[a-z0-9_]{1,64}$`). Type: string. JSON, the full current state:

```json
{ "v": 1, "pipeline": "callrail", "env": "prod", "run_id": "20261017T020301Z",
  "map": "accounts", "index": 4,
  "started_at": "2026-10-17T02:04:10Z", "ended_at": null, "updated_at": "2026-10-17T02:05:12Z",
  "counts": { "started": 10, "running": 4, "done": 5, "failed": 1 },
  "in_total": 480, "out_total": 455, "lost_items": 0,
  "inner": { "fetch": { "running": 2, "done": 8, "failed": 0, "in": 10, "out": 480 },
             "transform": { "running": 1, "done": 7, "failed": 1, "in": 480, "out": 455 },
             "load": { "running": 1, "done": 5, "failed": 0, "in": 455, "out": 455 } },
  "duration": { "count": 6, "sum_ms": 31840, "hist": { "92": 2, "95": 3, "101": 1 },
                "slowest": [ { "key": "acct-7", "ms": 9120 } ] },
  "failed_items": [ { "key": "acct-7", "step": "transform", "error_type": "ValueError" } ],
  "detail": { "limit": 1000, "kept": 10, "extra_failed_limit": 1000,
              "failed_without_record": 0, "slow_kept": 0 } }
```

Rules: `counts.started = running + done + failed`; `inner` has at most 20 entries; `hist` keys are bucket numbers (strings),
`bucket = floor(ln(ms)/ln(1.1))` for `ms ≥ 1`; `slowest` at most 5, `failed_items` at most 20, in arrival order. Counts and
sums cover **all** items, whatever their retention. Write: `SETEX key ttl json`, TTL = the run's `ttl_days` in seconds,
refreshed on each write. Rewritten at most once a second while values change, and once more when the map block ends,
when the process stops or exits.

## New: item record

```
waypoint:{pipeline}:{env}:{run_id}:item:{map}:{key}
```

`{key}` matches `^[A-Za-z0-9_.-]{1,64}$` (no `:`). Type: string. JSON:

```json
{ "v": 1, "pipeline": "callrail", "env": "prod", "run_id": "20261017T020301Z",
  "map": "accounts", "key": "acct-7", "index": 7, "state": "failed",
  "started_at": "2026-10-17T02:04:21Z", "finished_at": "2026-10-17T02:04:30Z", "duration_ms": 9120,
  "steps": [
    { "step": "fetch", "attempt": 1, "state": "done", "inputs": { "account": 1 }, "output": 48,
      "started_at": "2026-10-17T02:04:21Z", "duration_ms": 2300 },
    { "step": "transform", "attempt": 1, "state": "failed", "inputs": { "rows": 48 }, "output": null,
      "started_at": "2026-10-17T02:04:23Z", "duration_ms": 6820,
      "error": { "type": "ValueError", "message": "bad date", "traceback": "…frames…" } } ],
  "metrics": { "transform": { "rejected": 4 } } }
```

Rules: `state` is `running`, `done` or `failed`; `finished_at` and `duration_ms` absent while running; `steps` in the order
the inner steps began, at most 20 results; `error` as in failure items (type ≤ 200, message ≤ 500, traceback ≤ 2048 bytes
here); `metrics` follows spec 013 per inner step (≤ 20 names, finite numbers). A **compact** record (`"compact": true`)
beyond the first 1,000 items has no `metrics`, no `traceback` and a message ≤ 200 characters. An optional item-level
`error` appears when an exception left the item block with no failed inner step.
Written with `SETEX key ttl json`, same TTL as above, only for items that keep a record (research R5). A displaced slow
record is rewritten with a TTL of 1 second.

## Extended: flow record `...:{run_id}:flow`

A step entry may be a map step. `v` stays `1`:

```json
{ "name": "accounts", "kind": "map", "inputs": [ { "name": "accounts", "from": "b" } ],
  "over": "b", "max_concurrency": 5, "label": "Accounts", "group": "load",
  "steps": [
    { "name": "fetch", "inputs": [] },
    { "name": "transform", "inputs": [ { "name": "rows", "from": "fetch" } ],
      "metrics": [ { "name": "rejected", "unit": "rows", "warn_above": 100 } ] },
    { "name": "load", "inputs": [ { "name": "rows", "from": "transform" } ] } ] }
```

Optional fields are omitted when not set. An older monitor sees an ordinary step named `accounts` and ignores `kind`, `over`,
`max_concurrency` and `steps`; the map step's ordinary start marker and step record keep it consistent (research R1).

## Extended: events

Each event in the run's event lists may carry `"item": "acct-7"` (the sanitised key). `step` is the inner step's name. Event
version stays `1`; an older monitor ignores the field and shows the event with its step name.

## Run-level records for the map block

Unchanged shapes. Entering the block writes `...:running:{NN}-{map}`; leaving it normally writes `...:step:{NN}-{map}` with
`inputs` (the `over` source's count when given) and `output` = number of items that started; an exception leaving it writes
`...:failed:{NN}-{map}`.

## Unchanged

Alive, died, event lists and their TTLs; step, start-marker, failure and metrics record shapes.

## Permissions

Pipeline account: `SETEX` on `waypoint:*` (already granted; pipelined). Monitor account: `SCAN`, `MGET` (already granted).
**No new permission.**
