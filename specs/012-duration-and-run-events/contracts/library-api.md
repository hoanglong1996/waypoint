# Contract: library API (`waypoint_etl` 0.4.0)

## New functions

```python
waypoint_etl.log(message: str, *, level: str = "info", step: str | None = None, **fields: int | float | str) -> None
waypoint_etl.warn(message: str, *, step: str | None = None, **fields) -> None    # level="warning"
waypoint_etl.error(message: str, *, step: str | None = None, **fields) -> None   # level="error"
```

Example: `waypoint_etl.log("Loaded batch 3", step="load", rows=1200)`.

## Guarantees

- **Never raises and never blocks on the network.** Before `init`, after a failed `init`, with no store `push_events`,
  or with Redis down, the call does nothing (at most one warning per minute). Safe from any thread and from async code.
- `level` other than `info`/`warning`/`error` is treated as `info`.
- **Step attachment**: with `step=None` inside a running step the event is attached to that step (per thread/task via a
  context variable; a worker thread falls back to the single open step). `step=` always wins.
- **Limits** (shortened or dropped silently): message 300 characters; 10 fields; field names `^[A-Za-z0-9_.-]{1,40}$`;
  values finite numbers or strings of at most 100 characters (booleans, lists, objects, NaN dropped).
- **Privacy**: `init(capture_error_message=False)` omits event messages and drops text field values (numbers kept);
  `init(redact=fn)` cleans every message and text value before the cap. Same settings as for error messages; a `redact`
  that raises or returns a non-string drops that text.
- **Volume**: stored per run at most 500 info, 200 warning and 200 error events (oldest of a level dropped first).
  The in-process queue holds 2,000 events; beyond that the event is dropped (warning/error displace an info event).
- **Delivery**: events are written by a background thread within about a second. `waypoint_etl.clear()` and process exit
  flush, waiting at most 2 seconds. A killed process (`SIGKILL`) can lose the last second of events.
- **No data content**: event text is whatever the author wrote; the documentation says to keep data values out.

## `init` (unchanged signature)

No new parameters. `capture_error_message` and `redact` now cover event text too (docstring and README say "free text").

## Finish records

Each step's finish record gains `started_at` and `duration_ms` (contracts/redis-keys.md). The step's result and
exceptions are unchanged.

## Not changed

`audited_step`, `wrap`, `PipelineSpec`, `StepSpec`, failure records, heartbeat. A custom store that implements only
`write` keeps working: step records still go through `write`, events need `push_events(items, ttl_seconds)` (items are `(key, values, cap)` triples)
and are skipped (one warning) when it is missing.
