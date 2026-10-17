# Contract: Redis keys

All keys under the `waypoint:` prefix. Written only by the library; the monitor reads only.

## New: event lists

```
waypoint:{pipeline}:{env}:{run_id}:events:info
waypoint:{pipeline}:{env}:{run_id}:events:warning
waypoint:{pipeline}:{env}:{run_id}:events:error
```

Type: Redis **List**. Elements are JSON strings, oldest first:

```json
{ "v": 1, "n": 17, "ts": "2026-10-17T02:03:41.482Z", "level": "info",
  "step": "load_x", "message": "Loaded batch 3", "fields": { "rows": 1200, "source": "api" } }
```

`step`, `message` and `fields` are optional. `message` is absent when message capture is off.

Write (one transaction per flush, per level that has events): `RPUSH key e1 e2 ...`, `LTRIM key -CAP -1`, `EXPIRE key ttl`.
CAP is 500 (`info`), 200 (`warning`), 200 (`error`). TTL is the run's `ttl_days` in seconds, refreshed on each flush.

Pipeline account needs `RPUSH`, `LTRIM`, `EXPIRE` on `waypoint:*` (already covered by "writes `waypoint:*`").
Monitor account needs **`LRANGE`** and **`LLEN`** (new, read only) next to `SCAN`, `MGET`, `PING`, `PTTL`.

## Extended: finish record `...:{run_id}:step:{NN}-{step}`

Two optional fields added; nothing removed or renamed:

```json
{ "pipeline": "...", "run_id": "...", "env": "...", "step": "...", "index": 2,
  "inputs": { "calls": 120 }, "output": 118, "finished_at": "2026-10-17T02:05:51Z",
  "started_at": "2026-10-17T02:03:41Z", "duration_ms": 130482 }
```

No `v` is added (the record has none today). An older monitor ignores the new fields; a newer monitor treats records
without them as older records (approximate step durations, R1).

## Unchanged

Flow, start marker, alive, died, failed keys and their TTLs.
