# Contract: Library API (`waypoint_etl` 0.5.0)

## `waypoint_etl.metric`

```python
waypoint_etl.metric(name: str, value: int | float, *, step: str | None = None, mode: str = "set") -> None
```

- `mode`: `"set"` (replace, default), `"add"` (add to the current value; starts from the value itself), `"max"` (keep the larger).
- Inside a running step (`@audited_step`) `step` may be omitted: the call applies to the running step, per thread and per
  asyncio task. With `step` given, it applies to the latest attempt of that step if one has begun (also after it finished).
- No step given and none running: nothing happens.
- `name` must match `[a-z0-9_]{1,64}`; `value` must be a finite `int` or `float` (not `bool`); an unknown `mode`, a result that
  would become non-finite, a 21st distinct name on one attempt, or an explicit step that never began are all dropped. Each
  of these logs one warning per name and never raises.
- Before `init`, after a failed `init`, or when Redis is unreachable: does nothing, never raises, never waits on the network.
- Safe from any number of threads; `add` totals are exact.
- A retry of a step starts a fresh set of metrics for the new attempt.
- Metrics are merged in the process that called `init`; a separate worker process that did not run `init` records nothing.

## `Metric` and `StepSpec(metrics=...)`

```python
from waypoint_etl import Metric, StepSpec
StepSpec("merge_calls", inputs=(...), metrics=(
    Metric("rejected", label="Rejected rows", unit="rows", warn_above=100),
    Metric("coverage", unit="%", warn_below=90),
))
```

Validated with the rest of the spec: bad name, duplicate in a step, more than 20, over-long label or unit, non-numeric or
non-finite threshold, `warn_below > warn_above` make the spec invalid, which disables auditing with the usual warning.
Declaring a metric does not change how `metric()` works.

## Delivery guarantees

Values are written by a background thread at most once a second; at `waypoint_etl.clear()` and at process exit pending
values are delivered, waiting at most 2 seconds together with events. A failing store is logged at most once a minute and
the batch is dropped.

## Versions

`__version__ = "0.5.0"`. `init`, `audited_step`, `log`/`warn`/`error` are unchanged.
