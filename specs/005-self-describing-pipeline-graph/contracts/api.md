# Contract: Monitor API (changes to feature 002)

Read-only. Environment must be one of `ENVIRONMENTS`.

## `GET /api/pipelines?env=`
`200 {"env", "pipelines": [{"name", "label", "last_run_id"}]}` sorted by `last_run_id` desc. Discovered from keys; `503 {"error"}` when the store is unreachable, `400` for an unknown env.

## `GET /api/runs?env=&pipeline=&limit=`
`pipeline` required, must match the name pattern (`400` otherwise). Each run:
```json
{"run_id": "...", "pipeline": "callrail", "env": "prod", "status": "complete|incomplete|running",
 "flow_status": "ok|missing|invalid", "flow_problems": ["input 'x' of 'b' names unknown step 'z'"],
 "flow": {"label": "...", "groups": [{"key","label"}],
          "steps": [{"name","label","group","inputs":[{"name","from"}],"returns_nothing","col","row"}]},
 "steps": [{"name","state","...as before"}],
 "...existing fields (started_at, ended_at, duration_seconds, age_seconds, stale, running_step,
   first_missing_step, missing_count, loss_steps, unreadable)": ""}
```
`flow` is `null` when `flow_status` is `missing`/`invalid` (the simplified graph then uses `steps` order).

## `GET /api/config`
Removes `expected_steps`; other fields unchanged.

## `GET /api/health`
Unchanged.
