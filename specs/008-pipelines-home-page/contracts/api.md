# Contract: `GET /api/overview` (new)

Read only. No parameters. Environments are those configured in `ENVIRONMENTS`.

## 200

```json
{
  "generated_at": "2026-10-16T03:12:00Z",
  "unreadable_total": 0,
  "pipelines": [
    {
      "name": "callrail", "label": "CallRail",
      "environments": ["prod", "qa"],
      "card_status": "incomplete",
      "needs_attention": true,
      "latest": {
        "run_id": "20261016T020000Z", "env": "prod", "status": "incomplete", "stale": false,
        "started_at": "2026-10-16T02:00:00Z", "ended_at": "2026-10-16T02:01:12Z", "age_seconds": 4320,
        "loss_steps": [], "first_missing_step": "read_campaigns",
        "stalled_step": null, "stalled_seconds": null, "unreadable": 0,
        "headline": [
          {"key": "first", "step": "read_callrail_account", "label": "Accounts", "value": 10},
          {"key": "peak", "step": "read_gads_clickview", "label": "Click views", "value": 3410},
          {"key": "last", "step": "save_call_statistics", "label": "Save stats", "value": null}
        ]
      }
    }
  ]
}
```

## Rules

- `card_status` is the first match of: `running`, `stale`, `incomplete` (stopped or stalled), `lost` (a step got
  input and returned 0), `ok`. `needs_attention` is true for `stale`, `incomplete` and `lost`.
- `pipelines` is already ordered: needs-attention first, then the rest; each group by `label` A to Z.
- Only pipelines with at least one run appear. `latest` is the run with the greatest `run_id` across all
  environments; equal ids go to the environment listed first in `ENVIRONMENTS`.
- `environments` lists only environments with at least one run for that pipeline, in `ENVIRONMENTS` order.
- `headline`: `first` is the first step of the run's own flow, `last` the last one, `peak` the largest step
  strictly between them (the second step when none of them has a value; null step when there is no middle).
  A step's value is its output, or its first input when it returns nothing; `null` when it has not reported.
  Steps outside the flow are ignored.
- `stalled_step` / `stalled_seconds`: the first stalled step and how long it has run, else null.
- `unreadable_total` is the sum across environments, same meaning as in `/api/runs`.
- No pipelines: `{"generated_at": "...", "unreadable_total": 0, "pipelines": []}` with status 200.
- Only the fields above are returned. No step contents, no free-form record text.

## Errors

- `503 {"error": "Data store unavailable"}` when Redis cannot be reached (same as `/api/runs`).

## Unchanged

`/api/config`, `/api/health`, `/api/pipelines` and `/api/runs` keep their shape. `/api/runs` is what the
History page calls with a single `env`.
