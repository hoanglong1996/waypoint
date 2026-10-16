# Contract: Start marker (pipeline -> Redis -> monitor)

> **Superseded key layout**: keys and fields are now pipeline-scoped (`etl-audit:{pipeline}:{env}:{run_id}:...`, plus a `pipeline` field). See `specs/005-self-describing-pipeline-graph/contracts/redis-keys.md`. The text below is kept as history.

**Writer**: `StepAuditor.run(name, fn, ..., inputs=...)`, immediately before `fn(*args)`.

```text
SETEX callrail:running:<env>:<run_id>:<NN>-<step> 86400 <json>
json = {"run_id": "...", "env": "...", "step": "...", "index": N, "started_at": "YYYY-MM-DDTHH:MM:SSZ"}
```

Rules:
- Written through the existing `StepAuditStore.write(key, record, ttl_seconds)`; the TTL passed is the constant `START_MARKER_TTL_SECONDS = 86400`, not the 30-day audit TTL.
- A write failure is logged (`Warning: step start marker failed for <step>: <exc>`) and swallowed; `fn` still runs.
- If `fn` raises, the marker stays (it expires on its own) and no finish record is written (unchanged).
- The `NN`-`step` suffix equals the finish record's key suffix so the monitor can pair them.
- No-op store (`NoopStepAuditStore`) ignores the write, as today.

**Reader**: monitor `RecordStore.list_markers(env)` returns `(key, raw_json)` pairs by SCAN of `callrail:running:<env>:*`; invalid markers are ignored silently (they are never "unreadable audit records").
