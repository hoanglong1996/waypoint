# Data Model: Optional Step Metrics

## Library (what is written)

### Metric declaration (`Metric`, in `StepSpec.metrics`)

| Field | Type | Rule |
|---|---|---|
| name | str | `^[a-z0-9_]{1,64}$`, unique within the step |
| label | str or None | at most 40 characters |
| unit | str or None | at most 16 characters |
| warn_above | int/float or None | finite, not bool |
| warn_below | int/float or None | finite, not bool, `<= warn_above` when both |

At most 20 per step. Published in the flow record (contracts/redis-keys.md).

### Attempt metrics (in memory, per process)

`(index, step) -> {name: number}`; at most 20 names; `set` / `add` / `max` merge under one lock; a dirty flag per attempt.
A separate small set of already-warned names (bounded) prevents repeated warnings.

### Metrics record (stored)

One JSON value per step attempt: `v`, `pipeline`, `env`, `run_id`, `step`, `index`, `updated_at`, `metrics` (name to
number). Full state, rewritten on change.

## Monitor (what is read and served)

### StepMetrics (validated record)

pipeline, env, run_id, step, index (>= 1), updated_at (UTC or None), values: `Dict[str, float|int]`. Entries with an
invalid name or non-finite / non-number value are dropped; a record with wrong identity, version or shape is unreadable.

### MetricDecl (from the flow)

name, label, unit, warn_above, warn_below. Dropped with a flow problem when malformed (bad name, non-number threshold,
over 20 per step, duplicate name).

### Step metric (in `/api/runs`)

| Field | Meaning |
|---|---|
| name | metric name |
| label | declared label or null |
| value | number, or null when declared but not reported |
| unit | declared unit or null |
| declared | true when the run's flow declares it |
| flag | `"above"`, `"below"` or null (strict comparison; null when value is null) |
| updated_at | UTC time of the record's last write, or null |

Order: declared in declared order, then undeclared by name.

### Counts

`step.metrics_over` = number of flagged metrics on the step; `run.metrics_over` = sum over steps. Informational only (FR-017).

## Relationships and rules

- A step's metrics come from the record whose `index` equals the step's current attempt index. A record of an older
  attempt (a retry has begun) is ignored; a record whose step is not in the run is shown under that step (unplanned).
- A run's declarations come from **its own** flow. History trend declarations come from the newest run shown.
- A metrics record never creates a run or a step by itself: it is attached only to a step that already has a start marker, a finish record or a failure item (the library always writes the marker first). A damaged record still counts as unreadable for its run.
- No state machine: values only change by the three modes during an attempt.

## Metric trend (front end, derived)

Input: runs (newest first), step name, metric name, window, min runs. Output: `points` oldest to newest with `value` or
`null`, `median` (or null), `sample`, `warnAbove`, `warnBelow`, `unit`, `label`.
