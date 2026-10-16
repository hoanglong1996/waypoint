# Contract: API additions

Additive only; existing fields keep their meaning, so older front ends still work.

## GET /api/config

Unchanged shape. `refresh_seconds` now defaults to `5`. `stall_seconds` is **added** (informational for tooltips).

## GET /api/runs?env=<env>&limit=<n>

Each run gains:

```json
{ "status": "running", "running_step": "read_callrail_call", "stale": false }
```

`status` is `"complete" | "incomplete" | "running"`.

Each element of `steps` gains `state` and, where relevant, live fields:

```json
{ "name": "read_callrail_account", "state": "done", "inputs": [], "output": 10, "finished_at": "..." }
{ "name": "read_callrail_call", "state": "running", "started_at": "...", "elapsed_seconds": 42 }
{ "name": "read_partners", "state": "waiting" }
{ "name": "read_instances", "state": "stalled", "started_at": "...", "elapsed_seconds": 1020 }
{ "name": "read_campaigns", "state": "missing", "missing": true }
```

Rules:
- `missing: true` appears only for `state == "missing"`; `waiting`/`running`/`stalled` steps have no `inputs`/`output`.
- `elapsed_seconds >= 0` (clamped), measured against `generated_at`.
- 503 `{"error": "Data store unavailable"}` behaviour unchanged, including for marker reads.
