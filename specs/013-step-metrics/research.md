# Research: Optional Step Metrics

Decisions taken while planning, with what was read in the code on 2026-10-17. Rn numbers are referenced from
[plan.md](plan.md).

## R1. Where metrics are stored (roadmap open decision 8)

**Decision**: one record per step attempt, `waypoint:{pipeline}:{env}:{run_id}:metrics:{NN}-{step}`, a JSON string
holding all metrics of that attempt, written with the existing `store.write` (`SETEX`, TTL = run TTL).

**Rationale**: `auditor.finish` writes the step's record only when the step returns, so a metric inside the record
would be invisible while the step runs (FR-007). A separate key can be refreshed while the step runs. It reuses the
existing write method and the monitor's existing `SCAN` + `MGET` read, so **no new permission** on either side
(events needed `LRANGE`/`LLEN`). `{NN}` is the attempt index, so a retry writes a new key: the monitor takes the newest
index of a step, as it already does for failures (spec 011).

**Alternatives**:
- *Inside the finish record*: fewer keys, but not readable while running. Rejected.
- *Redis hash per step* (`HINCRBYFLOAT`, `HSET`): atomic across processes, but `max` needs a script (extra permission), and the
  monitor would need `HGETALL`. Rejected.
- *One record per run*: a retry or a second writer would overwrite the other steps' values. Rejected.
- *Reuse event lists*: append-only and capped by count, not mergeable into "current value". Rejected.

**Consequence**: metrics are merged **per process**. Metrics recorded by a forked or spawned worker process that
did not run `init` are not seen (same limit as `audited_step`). Documented in the library README.

## R2. How values are merged and delivered

**Decision**: `metrics.py` keeps, per (attempt index, step), a dictionary `name -> value` under one lock. `set` replaces,
`add` sums, `max` keeps the larger. A daemon writer thread (same pattern as `events.EventWriter` and `Heartbeat`)
wakes at most once a second, takes the dirty attempts and writes each record in full. `stop()` and the exit hook
flush for at most 2 s together with events.

**Rationale**: FR-006 and SC-003 (no Redis call per call) and SC-002 (exact totals under threads: the lock makes
`add` exact; the record is always rewritten from the merged state, so writer ordering cannot lose an update).
A value reaches the monitor up to ~1 s late, which the spec accepts (Assumptions).

**Alternatives**: per-call write (SC-003 fails); extend the event writer (different semantics, see Complexity Tracking).

## R3. Which attempt a call belongs to

**Decision**: a call without `step` uses the context variable `current_step` that `audited_step` already sets (right
per thread and per asyncio task) and the auditor's index of the latest attempt of that name (`_latest_index[name]`,
set in `begin`). A call with an explicit `step` uses the latest attempt of that name if one began; otherwise it is
dropped with one warning. A call with no step and no running step does nothing (FR-002).

**Rationale**: the key needs an index (R1). `begin` already assigns it. A metric after the step finished still lands on the
same attempt (spec edge case) because the index is remembered after the step closes. Retried steps get a new index, so
`add` starts again from zero for the new attempt (spec edge case: "latest attempt, not merged").

## R4. Validation and limits

**Decision**: name `^[a-z0-9_]{1,64}$` (the step-name rule), at most 20 distinct names per attempt, value `int` or `float`
but not `bool`, finite. An `add` or `max` whose result would be non-finite is ignored. Invalid input is dropped, with
one warning per name (set kept in the auditor, bounded to 100 names). Limits are constants in `keys.py`.

**Rationale**: matches spec FR-003/FR-004 and keeps the record small (20 entries, about 2 KB). Counting new names only
means existing metrics keep updating at the limit.

## R5. Declarations

**Decision**: `Metric(name, label=None, unit=None, warn_above=None, warn_below=None)` frozen dataclass in `spec.py`;
`StepSpec.metrics: Tuple[Metric, ...] = ()`. Validation (in `validate_spec`, so an invalid declaration disables
auditing the same way an invalid step does): name rule, unique within the step, at most 20, label up to 40, unit up to
16, thresholds finite numbers, `warn_below <= warn_above` when both set. Published as an optional `metrics` list on the
step in the flow record. `FLOW_VERSION` stays 1.

**Rationale**: spec FR-010/011. The flow record already carries label, group and layout hints per step, and the monitor's
`parse_flow` reads only known fields, so older monitors ignore the new one (FR-021). A duplicate name within one `StepSpec` is a validation error (the same rule as duplicate step names), which is
stricter and simpler than "last wins"; the spec's edge case was amended to say so.

## R6. Monitor parsing and merge

**Decision**: `parse_metrics` mirrors `parse_failures`: key regex, validate `v == 1`, identity fields equal to the key,
`metrics` is an object of at most 20 entries whose names match the rule and whose values are finite numbers (non-bool);
an entry that fails is dropped, a record that fails as a whole is unreadable and counted for its run. `domain/metrics.py`
picks, for each step, the record whose index equals the step's current attempt index (an older attempt's record is
ignored), then builds `metrics: [{name, label, value, unit, flag, declared, updated_at}]`: declared first in declared
order (value `null` when not reported), then undeclared alphabetically (FR-015). Flag: `above` when `value > warn_above`,
`below` when `value < warn_below` (strict, FR-014); never for a not-reported or undeclared metric.

**Rationale**: reuses patterns the code base already trusts. Per-step `metrics_over` (count of flagged) and run
`metrics_over` (sum) are cheap and give alerting #6 and the badge what they need (FR-016/017).

## R7. Privacy

**Decision**: nothing new beyond numbers and identifier-like names. Labels and units come from the author's declaration
in code, are capped, and are escaped in the page. No `capture_error_message` / `redact` involvement: there is no free text
from runtime data in a metric.

**Rationale**: FR-009. A boolean or string value is rejected rather than coerced so that data cannot be smuggled in as a number
by accident (for example `True` counting as 1).

## R8. History trend and median

**Decision**: computed in the front end from `/api/runs` (which already returns each run's steps with metrics):
`metricTrend(runs, step, name, window, minRuns)` returns points oldest to newest (`null` for not reported, drawn as gaps),
the median of the newest `window` reported values when at least `minRuns` exist, and the threshold lines from the **newest
run's** declaration. The picker lists steps that declare at least one metric in any shown run (FR-018). Window and minimum
come from `/api/config` (`duration_window_runs`, `duration_min_runs`), no new setting (FR-019).

**Rationale**: the server would only repeat what the page can do from data it already has; this is how the step trend and
sparkline work today. Run limit of `/api/runs` bounds the data (default 30, max 100).

## R9. Names that collide in the front end

`static/js/model.js` exports `metric(step)`, the output count used by deltas, sparklines and the History step trend.
New code uses `stepMetrics`, `metricTrend`, `metricsOver`, and CSS classes `.xmetric*`, so a search for `metric(` still
finds only the old meaning.

## R10. Compatibility matrix

| Library | Monitor | Result |
|---|---|---|
| old | new | no metrics records, no declarations: unchanged display (FR-021) |
| new | old | extra keys never matched by the old monitor's patterns; extra flow field ignored; no error |
| new, no `Metric` declared | new | metrics appear in the step table without unit/flag; no History trend (spec US4) |
| new, declared | new | full feature |
