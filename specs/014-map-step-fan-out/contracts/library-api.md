# Contract: Library API (waypoint_etl 0.6.0)

## Declaring a map step

```python
from waypoint_etl import MapStepSpec, PipelineSpec, StepSpec, Metric

SPEC = PipelineSpec(
    name="callrail",
    steps=(
        StepSpec("list_accounts", returns_nothing=False),
        MapStepSpec(
            "accounts",
            over="list_accounts",          # optional: the earlier step that supplies the items
            max_concurrency=5,             # optional, informational
            steps=(
                StepSpec("fetch"),
                StepSpec("transform", inputs=(("rows", "fetch"),), metrics=(Metric("rejected", unit="rows", warn_above=100),)),
                StepSpec("load", inputs=(("rows", "transform"),)),
            ),
        ),
        StepSpec("publish", inputs=(("done", "accounts"),)),
    ),
)
```

`MapStepSpec(name, steps, over=None, max_concurrency=None, label=None, group=None, col=None, row=None, inputs=())`.
Validation (an invalid description turns tracking off with the usual warning, never raises): name pattern and uniqueness
across the pipeline including inner steps; 1 to 20 inner steps; no `MapStepSpec` among inner steps; no branches (an inner
step's inputs name only an earlier inner step or an earlier top-level step); `max_concurrency ≥ 1` when given (FR-010).

## Recording

```python
with waypoint_etl.map_step("accounts"):                 # the whole loop
    with ThreadPoolExecutor(5) as pool:
        list(pool.map(process, accounts))

def process(account):
    with waypoint_etl.item(account.id):                 # one pass; id or index, never content
        fetch(account)                                  # @audited_step("fetch") as today
        transform(...)
        load(...)
```

| Call | Behaviour |
|---|---|
| `map_step(name)` | Context manager (also `async with`). Entering writes the ordinary start marker of step `name`; leaving normally writes its step record, leaving with an exception writes its failure item and re-raises. Never suppresses an exception. Map steps do not nest (0.6.1): inside an open map step it is ignored with one warning, and `item()` calls inside it are ignored too (inner steps stay with the enclosing item). Without `init`, or for a name that is not a declared map step, it does nothing except warn once for the latter. |
| `item(key, *, map=None)` | Context manager (also `async with`) for one item. Resolves its map: `map=`, else the enclosing `map_step` of this context, else the one open map block of the run; else nothing is recorded (one warning). Sanitises `key` (research R9). A duplicate key in the same map step: first record kept, this pass ignored (inner steps still run, nothing is recorded), one warning. An exception leaving the block marks the item failed (when no inner step failed) and propagates. |
| `@audited_step`, `waypoint_etl.log`, `waypoint_etl.warn`, `waypoint_etl.error`, `waypoint_etl.metric` | Inside `item()` they belong to that item: an inner step is recorded on the item, events carry `item`, metrics merge per inner step. Outside `item()` they behave exactly as in 0.5.0. |

Inner step names are looked up in the map step's item flow. A name that is not declared there is recorded on the item and
shown as unplanned, after one warning, like an ordinary unplanned step.

## Guarantees

- No call raises into the pipeline, and none waits on the network: state is merged under a lock and a background writer sends
  at most one batch per second (research R4). Records are also written when `map_step` ends, on `stop()` and at exit (waiting at most 2 s).
- Correct attribution when items run in threads (`item()` inside the worker function), asyncio tasks (context is copied per
  task) or a plain loop. A `ThreadPoolExecutor` worker does not inherit the caller's context, which is why `item()` finds its
  map from the open block.
- Items run in a **child process** are not attributed unless the child calls `init` and opens its own scopes; documented, not hidden.
- Bounded retention: 1,000 full items, up to 1,000 further failed (compact) and the 50 slowest later ones keep a record; counts
  always cover every item (research R5). Each limit is a constant, not a setting.
- With the store unreachable, the library not set up or setup failed: every call is a no-op; results, exceptions and exit code of
  the pipeline are identical.
- Only names, keys, counts, numbers, times and short diagnostic text are stored. `capture_error_message` and `redact` apply to
  item error messages as they do to step failures.
- Pipelines without a map step and code that never calls the new entry points behave exactly as in 0.5.0.

## Limits

Item key `^[A-Za-z0-9_.-]{1,64}$` (other characters become `_`, longer keys are cut, an empty key becomes `item_{n}`);
20 inner steps per map step; 20 metrics per inner step per item; everything in data-model.md "Limits".

## Exports

`MapStepSpec`, `map_step`, `item` added to `waypoint_etl.__all__`; `__version__ = "0.6.1"`.

## Store protocol

`write(key, record, ttl_seconds)` is still the only required method. `write_many(items: Sequence[Tuple[str, Dict[str, object]], ...], ttl_seconds: int)`
is optional (the Redis store pipelines it); the map writer falls back to `write` in a loop when a store has none.
