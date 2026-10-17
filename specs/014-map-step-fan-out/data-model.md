# Data Model: Map Step

Names follow the spec's Key Entities. Stored shapes are in [contracts/redis-keys.md](contracts/redis-keys.md);
HTTP shapes in [contracts/api.md](contracts/api.md).

## Declaration (library, in the pipeline description)

**MapStepSpec** — a step of `PipelineSpec.steps` next to `StepSpec`.

| Field | Rule |
|---|---|
| `name` | Same as a step name: `^[a-z0-9_]{1,64}$`; unique across all steps **and** inner steps of the pipeline |
| `steps` | 1 to 20 `StepSpec`, linear order as declared, no branches (an inner step's inputs may name only an earlier inner step or an earlier top-level step); inner steps may declare metrics like any step |
| `over` | Optional name of an earlier top-level step that supplies the items; shown in the flow, used for the step record's input count |
| `max_concurrency` | Optional integer ≥ 1; informational (FR-001) |
| `label`, `group`, `col`, `row`, `inputs` | As for `StepSpec` |

Invalid when: a duplicate name anywhere, `steps` empty, an inner step that is itself a `MapStepSpec`, a name that fails
the pattern, an inner input from an unknown or later step, `max_concurrency` below 1 (FR-010). An invalid description
turns tracking off with the usual warning, as today.

## Aggregate: map step summary (one per map step per run)

| Field | Meaning |
|---|---|
| `map` | Map step name |
| `index` | Attempt index of the map block (the ordinary step's index) |
| `started_at`, `ended_at` | UTC; `ended_at` is null while the block is open |
| `updated_at` | UTC time of the write |
| `counts` | `{started, running, done, failed}` over **all** items; `started = running + done + failed` |
| `in_total`, `out_total` | Sums over items of the item's in and out (below) |
| `lost_items` | Number of items with data loss (rule below) |
| `inner` | Per inner step: `{running, done, failed, in, out}` counts across all items |
| `duration` | `{count, sum_ms, hist: {bucket: n}, slowest: [{key, ms}] (≤ 5)}` over finished items |
| `failed_items` | First 20 failures in order: `{key, step, error_type}` |
| `detail` | `{limit: 1000, kept: n, extra_failed_limit: 1000, failed_without_record: n, slow_kept: n}` |

State rules: `running` = block open; failed = `counts.failed ≥ 1`; done = block ended and `failed = 0`. `detail.partial`
(derived by the monitor) = `counts.started > detail.kept`.

## Item (one record per detailed item)

| Field | Meaning |
|---|---|
| `key` | Sanitised item key (`^[A-Za-z0-9_.-]{1,64}$`) |
| `index` | Arrival number, 1-based: order the items started in; breaks ties in every sort |
| `state` | `running`, `done` or `failed` |
| `started_at`, `finished_at` | UTC; `finished_at` absent while running |
| `duration_ms` | Whole milliseconds, monotonic; absent while running |
| `steps` | List of **inner step results** in the order they began |
| `metrics` | `{inner_step: {name: number}}` (latest attempt of each inner step) |
| `error` | Item-level error (an exception that left the item block with no inner step failure): `{type, message?, traceback}` |
| `compact` | True for a record kept beyond the detail limit: no `metrics`, no traceback |

**Inner step result**: `{step, attempt, state: running|done|failed, inputs: {name: count}, output: count|null,
started_at, duration_ms?, error?}`. `attempt` is the per-item counter the decorator holds; a later attempt of the same
inner step replaces the earlier one in the item's view.

Item state: `failed` when the latest attempt of any inner step failed or the item block raised with no inner step
failure; `running` while open and not failed; `done` when the block ended with no failure.

Item **in** = sum of the first inner step's input counts; item **out** = the last inner step's output (null when
unknown or not finished). Item **loss**: any inner step with `output == 0` while some input is above 0 (the rule of an
ordinary step, `analysis._is_loss`).

## Item key and duplicate rule

A key is unique within one map step of one run. Starting an existing key again (after sanitising) is ignored: the first
record stays, the second pass's recordings are dropped, one warning is logged per key (spec Clarifications).

## Map step summary as the monitor serves it

`{counts, started, state, in_total, out_total, lost_items, concurrency_limit, loop_seconds, duration: {median_ms,
p95_ms, approx: true, enough: bool}, slowest: [{key, ms}], failed_items: [...], inner: [{name, ...counts}], detail:
{partial, kept, failed_without_record}, unreadable}`. See contracts/api.md.

## Run, step and flow additions in the monitor

- **Flow step** gains optional `map`: `{over, max_concurrency, steps: [flow step]}`. Inner steps are not top-level steps.
- **Run step** (existing object) gains optional `map`: the summary above. State and `error` come from R6.
- **Event** gains optional `item`.

## State transitions

```
item:      (absent) → running → done
                          └──→ failed        (an inner step's latest attempt failed, or the block raised)
map step:  (absent) → running (block open) → done      (block ended, failed = 0)
                                    └──────→ failed    (failed ≥ 1: shown as running until the block ends)
```

A stalled or died run shows running items with the run's state instead (R12).

## Limits (fixed in this release)

| Limit | Value |
|---|---|
| Items with a full record per map step | 1,000 |
| Further failed items with a compact record | 1,000 |
| Slowest later items kept | 50 |
| Item key | `^[A-Za-z0-9_.-]{1,64}$` |
| Inner steps per map step | 20 |
| Metrics per inner step per item | 20 (spec 013) |
| Item trace in a full record | 2 KiB (frames only, last frames kept) |
| Compact error message | 200 characters |
| Failures listed in the aggregate | 20 |
| Slowest listed in the aggregate | 5 |
| Item page size | default 50, maximum 200 |
| Write interval | at most once per second per map step |
