# Contract: library API (`waypoint_etl` 0.3.0)

Extends `specs/006-packaged-audit-sdk/contracts/library-api.md`. Nothing is removed or renamed.

## `init(...)` gains two keyword-only arguments

```python
waypoint_etl.init(
    pipeline=SPEC, redis_url=url, env="prod",
    capture_error_message=True,                 # False: store error type and traceback, never the message
    redact=lambda text: scrub(text),            # optional: str -> str, applied to every message first
)
```

- `capture_error_message`: default `True`.
- `redact`: default `None`. If it raises or returns a non-string, the message is dropped for that failure.

## Behaviour guarantees (tests assert each)

1. A step function (plain or `async`) that raises an `Exception` has a failure item written, and the **same exception
   object** is re-raised: same type, message, `__cause__`, `__context__` and traceback frames as without monitoring.
2. A step that returns is unchanged: same result, same finish record as 0.2.x.
3. Any failure while building or writing the item (store down, unprintable exception, bad `redact`) is logged as
   one warning and never alters, hides or replaces the step's own exception.
4. The traceback has no variable values. With capture off, the message text appears nowhere in the item.
5. Not recorded: `KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError` (not `Exception` subclasses).
6. Without `init` (no active auditor) behaviour is exactly the original function's.
7. The existing heartbeat, flow and finish records are unchanged.

## Also

- `StepAuditor.run(...)` (the non-decorator path) records failures the same way.
- `waypoint_etl.__version__` is `"0.3.0"`; README documents the new record and both settings.
