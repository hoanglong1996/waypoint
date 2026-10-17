# Contract: Redis keys

All keys under the `waypoint:` prefix. Written only by the library; the monitor reads only.

## New: metrics record

```
waypoint:{pipeline}:{env}:{run_id}:metrics:{NN}-{step}
```

`{NN}` is the step attempt's index (2 digits, more when needed), the same index as the step's start marker, finish
record and failure item. Type: string. JSON, the full current state of that attempt:

```json
{ "v": 1, "pipeline": "callrail", "env": "prod", "run_id": "20261017T020301Z",
  "step": "merge_calls_clickview", "index": 7, "updated_at": "2026-10-17T02:05:12Z",
  "metrics": { "rejected": 42, "retries": 3, "peak_batch": 5000, "ratio": 0.25 } }
```

Rules: at most 20 entries; names `^[a-z0-9_]{1,64}$`; values finite JSON numbers (never booleans, strings, null).
Write: `SETEX key ttl json`, TTL = the run's `ttl_days` in seconds, refreshed on each write. Rewritten at most once a second
while values change, and once more when the process stops or exits.

Pipeline account: `SETEX` on `waypoint:*` (already granted). Monitor account: `SCAN`, `MGET` (already granted). **No new
permission.**

## Extended: flow record `...:{run_id}:flow`

Each step entry may carry an optional `metrics` list; `v` stays `1`:

```json
{ "name": "merge_calls_clickview", "inputs": [ ... ],
  "metrics": [ { "name": "rejected", "label": "Rejected rows", "unit": "rows", "warn_above": 100 } ] }
```

`label`, `unit`, `warn_above`, `warn_below` are each optional and omitted when not set. An older monitor ignores the field.

## Unchanged

Step records, start markers, alive, died, failed, event lists and their TTLs.
