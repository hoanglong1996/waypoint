# Data Model: Run Duration and Run Events

Entities of [spec.md](spec.md) with the rules decided in [research.md](research.md). Times are UTC.

## Step record (existing, extended)

Existing fields unchanged. New, both optional (written by library 0.4.0):

| Field | Type | Rule |
|---|---|---|
| `started_at` | ISO-8601 UTC, second resolution | When the attempt began (same value as its start marker). |
| `duration_ms` | int ≥ 0 | Elapsed time measured with a monotonic clock. |

A value of the wrong type is ignored (the field is treated as absent); it does not make the record unreadable.

## Step duration (computed by the monitor)

| Field | Meaning |
|---|---|
| `duration_seconds` | int ≥ 0 or `null` (unavailable) |
| `duration_approx` | `true` when derived from the previous step's end (R1, source 4) |

Applies to `done`, `unplanned` and `failed` steps. `running`/`stalled` steps keep `elapsed_seconds`. `waiting`,
`missing` and `died` steps have no duration.

Source order (R1): `duration_ms` → finish `started_at` → start marker → previous end (approximate). A negative result, or
one without a start, gives `null`.

## Run duration (computed)

`duration`: `{ "seconds": int|null, "running": bool, "complete": bool, "slow": bool }`

- `seconds`: from the run start (run id) to the last activity (latest finish or failure time); for a running run to now.
- `running`: the run is running (the value is elapsed time to now).
- `complete`: `status == "complete"` (counts toward typical durations).
- `slow`: Slower than usual (rule below). Always `false` when `typical` is null.

The existing `duration_seconds` field is unchanged.

## Typical duration (per pipeline and environment)

`typical`: `{ "median_seconds": int, "p95_seconds": int, "sample": int, "window": int, "multiple": float, "slow_after_seconds": int }`
or `null` when fewer than `DURATION_MIN_RUNS` runs qualify.

- Qualifying run: `status == "complete"` with a known duration, newest `DURATION_WINDOW_RUNS` of them.
- `median_seconds`: middle value (mean of the two middle values when `sample` is even), rounded to the second.
- `p95_seconds`: nearest-rank, the `ceil(0.95 * sample)`-th smallest.
- `slow_after_seconds = multiple * median_seconds`.

**Slow rule**: `duration.seconds > slow_after_seconds` and `typical` is not null. For a running run `seconds` is elapsed
time to now. Slow never changes `status`, ordering or the attention group.

## Bottleneck (computed)

`bottleneck`: step name or `null`. The step with the strictly largest `duration_seconds` among steps that have one, only
when at least two steps have one.

## Run event (recorded)

Stored element of a list (see contracts/redis-keys.md).

| Field | Type | Rule |
|---|---|---|
| `v` | int | `1` |
| `n` | int ≥ 1 | Per-process sequence over all levels |
| `ts` | ISO-8601 UTC with milliseconds | When the event was sent |
| `level` | `info` \| `warning` \| `error` | Equals the list it is in |
| `step` | string, optional | Non-empty, ≤ 200 characters |
| `message` | string, optional | ≤ 300 characters; omitted when message capture is off |
| `fields` | object, optional | ≤ 10 entries; name `^[A-Za-z0-9_.-]{1,40}$`; value finite number or string ≤ 100 characters |

Monitor parsing rejects (skips and counts as unreadable for the run): bad JSON, wrong `v`, missing/bad `ts`, a `level`
that differs from the list, `n` not an int ≥ 1. Over-long text is shortened and extra fields dropped, not rejected.

## Timeline entry (computed, returned by the API)

| Field | Type | Meaning |
|---|---|---|
| `id` | string | `r:{level}:{n}` for recorded, `d:{kind}:{step}:{index}` for derived; unique within a run |
| `ts` | ISO-8601 with milliseconds | Position in the timeline (R4) |
| `level` | `info` \| `warning` \| `error` | |
| `step` | string \| null | |
| `message` | string \| null | `null` when not stored |
| `fields` | object \| null | |
| `source` | `pipeline` \| `monitor` | recorded vs derived |
| `kind` | string | `custom`, or a derived kind (below) |

Derived kinds, with level and timestamp rule:

| kind | When | level | `ts` |
|---|---|---|---|
| `run_started` | always | info | run start (run id), `.000` |
| `step_started` | step has a start time (exact or approximate) | info | start, `.000` |
| `step_finished` | `done`/`unplanned` step | info | `finished_at`, `.999`; fields `output`, `duration_seconds` |
| `step_failed` | failed step | error | `failed_at`, `.999`; fields `error_type`; message `Type: message` (no traceback) |
| `step_stalled` | step `stalled` | warning | `started_at + stall_seconds`, `.000` |
| `run_died` | run has a `died` verdict | error | `judged_at`, `.999` |
| `run_stopped` | run is Failed | error | `failed_at`, `.999` |
| `run_finished` | `status == "complete"` | info | `ended_at`, `.999`; field `duration_seconds` |

Derived entries have `source: "monitor"`. A step that retried shows its latest attempt only: the built run keeps one entry per step, so earlier attempts are not listed.

## Event counts (per run, computed)

`event_counts`: `{ "warning": int, "error": int }`, from `LLEN` of the two lists. Counts recorded events only: a step
failure is already shown as Failed and is not counted again.

## State and ordering rules

- Timeline order: `(ts, source_rank, sequence)`; derived (rank 0) before recorded (rank 1) at the same instant; derived by
  derivation order, recorded by `n`.
- `dropped = max(0, max(n over all recorded) - number of recorded events)`.
- Run page tab and filters are client state; no server-side session.
