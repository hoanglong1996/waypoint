# Data Model: Live Step Running Indicator

## StartMarker (Redis, written by the pipeline)

| Field | Type | Rule |
|---|---|---|
| `run_id` | string `YYYYMMDDTHHMMSSZ` | equals the id in the key |
| `env` | string | equals the env in the key |
| `step` | string | one of the expected step names |
| `index` | int >= 1 | position in the run, same as the finish record |
| `started_at` | string, UTC ISO-8601 `…Z` | time just before the step function was called |

Key: `callrail:running:<env>:<run_id>:<NN>-<step>`; TTL 86 400 s. Counts and timestamps only; no item contents.

## StepState (derived by the monitor, per step per run)

| State | Condition | Extra fields |
|---|---|---|
| `done` | a valid finish record exists | `inputs`, `output`, `finished_at` (as today) |
| `running` | no finish record; marker exists; elapsed <= stall limit | `started_at`, `elapsed_seconds` |
| `stalled` | no finish record; marker exists; elapsed > stall limit | `started_at`, `elapsed_seconds` |
| `waiting` | no record, no marker; run has a live running step with a lower index | none |
| `missing` | none of the above (existing behaviour, `missing: true`) | none |

Transitions within one run: `waiting -> running -> done`; `running -> stalled` by time; `stalled -> done` is possible if a late finish record arrives (finish record always wins). A finish record always overrides a marker for the same step.

## Run (extended)

| Field | Change |
|---|---|
| `status` | `complete` \| `incomplete` \| **`running`** |
| `running_step` | **new**, name of the live running step or `null` |
| `stale` | `false` while `status == "running"` |
| `first_missing_step`, `missing_count` | `waiting` and live `running` steps are not counted as missing; a `stalled` step is counted (first stop point) |
| `steps[].state` | **new**, one of the StepState values for every step |

## Settings (monitor)

| Name | Default | Change |
|---|---|---|
| `REFRESH_SECONDS` | `5` | was 60 |
| `CACHE_SECONDS` | `2` | was 10 |
| `STALL_SECONDS` | `900` | new |

## Client view state

`runSignature(runs)`: stable string over runs with `age_seconds`, `elapsed_seconds` removed; compared after each fetch to decide whether to redraw.
