# Contract: API additions

Nothing is removed or renamed, so older front ends keep working.

## `GET /api/runs`: response

New top-level field:

```json
"typical": { "median_seconds": 612, "p95_seconds": 745, "sample": 24, "window": 30,
             "multiple": 2.0, "slow_after_seconds": 1224 }
```

`typical` is `null` when fewer than `DURATION_MIN_RUNS` complete runs exist. It is computed over every run the monitor
read for this pipeline and environment, not only the `limit` returned.

## `GET /api/runs`: each run gains

```json
"duration": { "seconds": 655, "running": false, "complete": true, "slow": false },
"bottleneck": "read_callrail_call",
"event_counts": { "warning": 2, "error": 1 }
```

`duration_seconds` (existing) is unchanged. `bottleneck` is `null` unless 2+ steps have durations. `event_counts` is
`{ "warning": 0, "error": 0 }` when the run has none.

Each step of state `done`, `unplanned` or `failed` gains:

```json
"duration_seconds": 130, "duration_approx": false, "started_at": "2026-10-17T02:03:41Z"
```

`duration_seconds` may be `null`. `started_at` is present for `done`/`unplanned` steps when known (it already exists for
`failed`, `running`, `stalled`, `died`). A run from library 0.2.0/0.3.0 has `duration_approx: true` on steps whose start
was derived.

## `GET /api/overview`: each pipeline's `latest` gains

`duration_seconds` (int|null), `duration_running` (bool), `slow` (bool), `warnings` (int), `errors` (int). Ranking and
`card_status` are unchanged (Slower than usual never changes them).

## New: `GET /api/runs/{pipeline}/{env}/{run_id}/events`

Query: `level` (`info`|`warning`|`error`, repeatable or comma list), `step` (exact name), `offset` (≥ 0, default 0),
`limit` (1 to 500, default 200).

```json
{
  "env": "prod", "pipeline": "callrail", "run_id": "20261017T020000Z",
  "generated_at": "2026-10-17T02:10:00Z",
  "total": 41, "matched": 6, "offset": 0, "has_more": false,
  "recorded": 12, "dropped": 0, "unreadable": 0,
  "events": [
    { "id": "d:run_started::0", "ts": "2026-10-17T02:00:00.000Z", "level": "info", "step": null,
      "message": "Run started", "fields": null, "source": "monitor", "kind": "run_started" },
    { "id": "r:info:3", "ts": "2026-10-17T02:03:41.482Z", "level": "info", "step": "load_x",
      "message": "Loaded batch 3", "fields": { "rows": 1200 }, "source": "pipeline", "kind": "custom" }
  ]
}
```

- `total`: all timeline entries for the run; `matched`: after filters; `recorded`: author events read; `dropped`: R6;
  `unreadable`: damaged event elements skipped.
- `recorded: 0` and `dropped: 0` means the run has no author events (older library or none sent).
- Errors: `400` for an unknown `env`, an invalid `pipeline`/`run_id`, a bad `level`/`offset`/`limit`; `404` is **not**
  used (an unknown run returns an empty timeline with `total: 0`, like `/api/runs` returns no runs); `503` when the
  store is unavailable.
- Read only: three `LRANGE` calls for the one run. If the account lacks `LRANGE`/`LLEN`, `recorded` is `0` and the derived timeline is still returned (research R12).

## `GET /api/config`: gains

`slow_run_multiple`, `duration_window_runs`, `duration_min_runs` (informational).

## New settings (environment variables, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `SLOW_RUN_MULTIPLE` | `2.0` | A run is Slower than usual above this multiple of the median |
| `DURATION_WINDOW_RUNS` | `30` | Newest complete runs used for median and p95 |
| `DURATION_MIN_RUNS` | `5` | Fewest complete runs needed before any run is flagged |

Invalid values fall back to the default, like the other settings.
