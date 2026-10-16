# Contract: Monitor HTTP API

All endpoints are `GET`, read-only, JSON. Errors: `{"error": "<message>"}`.
The UI (`docs/design/pipeline-monitor-degisn`) needs the recent runs in full to draw hero, step list, sparklines,
history and the trend chart, so one call returns them all; there are no per-run or per-step endpoints.

| Endpoint | Purpose |
|---|---|
| `/api/health` | `{"redis": "ok"}`, or 503 `{"redis": "unavailable", "error": "Data store unavailable"}` |
| `/api/config` | Static settings and the pipeline definition (below) |
| `/api/runs?env=prod&limit=30` | Newest-first runs with full step detail; `limit` default 30, max 100 |

Unknown `env` → 400. Redis unreachable → 503 `{"error": "Data store unavailable"}`. No runs → 200 with `"runs": []`.

## `/api/config`

```json
{"environments": ["prod", "qa"], "refresh_seconds": 60, "retry_seconds": 30, "stale_hours": 26,
 "expected_steps": [
   {"name": "read_callrail_account", "group": "CallRail", "inputs": [], "returns_nothing": false},
   {"name": "read_callrail_call", "group": "CallRail",
    "inputs": [{"name": "accounts", "from": "read_callrail_account"}], "returns_nothing": false},
   {"name": "merge_calls_clickview", "group": "Merge",
    "inputs": [{"name": "calls", "from": "read_callrail_call"},
               {"name": "campaigns", "from": "read_campaigns"},
               {"name": "clickview", "from": "read_gads_clickview"}], "returns_nothing": false},
   {"name": "save_call_statistics", "group": "Persist",
    "inputs": [{"name": "call_statistics", "from": "merge_calls_clickview"}], "returns_nothing": true}
 ]}
```

`expected_steps` is the complete ordered list of 9 (abridged above). It is the single source for
step order, group labels (CallRail 2, Google Ads 4, Merge 1, Persist 2), the input names and the
"from" tooltip, and which steps return nothing. The UI hard-codes none of it.

## `/api/runs`

```json
{"env": "prod", "generated_at": "2026-10-15T03:12:00Z", "unreadable_total": 2,
 "runs": [{
   "run_id": "20261015T020000Z", "env": "prod",
   "started_at": "2026-10-15T02:00:00Z", "ended_at": "2026-10-15T02:01:12Z",
   "duration_seconds": 72, "age_seconds": 4320, "stale": false,
   "status": "complete", "first_missing_step": null, "missing_count": 0,
   "loss_steps": [], "unreadable": 0,
   "steps": [
     {"name": "read_callrail_account", "inputs": [], "output": 10, "finished_at": "2026-10-15T02:00:07Z"},
     {"name": "read_callrail_call", "inputs": [{"name": "accounts", "value": 10}], "output": 1284,
      "finished_at": "2026-10-15T02:00:16Z"},
     {"name": "save_call_statistics", "inputs": [{"name": "call_statistics", "value": 1284}],
      "output": null, "finished_at": "2026-10-15T02:01:12Z"},
     {"name": "record_call_statistics", "missing": true}
   ]}]}
```

Rules:
- `steps` always has all 9 entries in pipeline order. A step with no valid record is `{"name", "missing": true}`.
- `inputs` is an ordered list following `expected_steps`; extra input names found in a record are appended; an empty list means "none".
- `output` is a number or `null` (null = step returns nothing, shown "n/a").
- `status` is `complete` (no missing steps) or `incomplete`. `first_missing_step` is the first missing name, else null.
- `loss_steps` lists steps with output exactly 0 and at least one input > 0.
- `ended_at` is the latest `finished_at` among reported steps (falls back to `started_at`); `duration_seconds = ended_at - started_at`.
- `age_seconds = generated_at - ended_at`; `stale = age_seconds > stale_hours × 3600`. The UI shows these for the newest run only.
- `unreadable` counts records of that run that failed validation (the step then counts as missing). `unreadable_total` also includes records whose key cannot be attributed to a run.
- Nothing other than the fields above is ever returned (no free-form record content).
