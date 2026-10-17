# Contract: Monitor API

Only additions; every existing field keeps its meaning. No new endpoint, no new setting.

## `GET /api/runs` (and every run object inside `/api/overview` sources)

Each element of `runs[].steps[]` that is `done`, `unplanned`, `running`, `stalled`, `died` or `failed` may carry:

```json
"metrics": [
  { "name": "rejected", "label": "Rejected rows", "value": 150, "unit": "rows",
    "declared": true, "flag": "above", "updated_at": "2026-10-17T02:05:12Z" },
  { "name": "coverage", "label": null, "value": null, "unit": "%",
    "declared": true, "flag": null, "updated_at": null },
  { "name": "retries", "label": null, "value": 3, "unit": null,
    "declared": false, "flag": null, "updated_at": "2026-10-17T02:05:12Z" }
],
"metrics_over": 1
```

- `metrics` and `metrics_over` are both omitted (not an empty list, not 0) when the step has none declared and none recorded, so every step of an older run keeps exactly its earlier keys.
- Declared metrics come first in declared order (`value` null = not reported, never 0), then undeclared by name.
- `flag`: `"above"` when `value > warn_above`, `"below"` when `value < warn_below`, else null. Equal to the threshold is not flagged.
- Each run object always gains `metrics_over` (0 when no step has metrics): the sum of its steps' `metrics_over` (informational; does not change `status` or ordering).
- `flow.steps[]` gains `metrics`: the declarations as stored (`name`, `label`, `unit`, `warn_above`, `warn_below`; absent keys are null).
- A damaged metrics record adds to the run's existing `unreadable` count.

## Overview

`/api/overview` is unchanged (no card shows metrics in this release).

## `GET /api/config`

Unchanged. The front end reuses `duration_window_runs` and `duration_min_runs` for the metric median (FR-019). The front end
currently maps only `duration_min_runs`; it also maps `duration_window_runs`.

## Errors

Unchanged (503 when the store is unreachable).
