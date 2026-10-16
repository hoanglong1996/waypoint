# Research: Pipeline Step Audit Trail

## Decision 1: Wrap steps in `run_pipeline` via a small `StepAuditor.run(name, fn, **inputs)` helper
- **Rationale**: Records input and output at one place, keeps the pipeline body readable, and the
  helper can time-stamp and swallow storage errors uniformly.
- **Alternatives**: Decorators on each use case (spreads audit logic into 9 classes, and use cases do
  not know their run); manual `store.write` calls after each step (repetitive, easy to forget).

## Decision 2: Store only counts, via `count_items(value)`
- **Rationale**: Meets "only the number of items" and constitution II. `None` → "none" (`null`),
  list/tuple/set → `len`, any other object → 1.
- **Alternatives**: Store JSON of items (PII risk, large); store type names too (not requested).

## Decision 3: One Redis key per step per run, string value with JSON, `SETEX` 30 days
- **Key**: `callrail:audit:{env}:{run_id}:{index:02d}-{step}`; `run_id` = UTC start time
  `YYYYMMDDTHHMMSSZ`.
- **Rationale**: Per clarification, runs are kept separately. Timestamped ids sort lexically, so the
  latest run is the highest id (`SCAN callrail:audit:prod:*`). Per-key TTL expires each record 30 days
  after its own write. The step index keeps steps in pipeline order.
- **Alternatives**: One hash per run (TTL refreshed per step, so expiry is relative to the last
  write; also harder to read one step); a "latest" pointer key (rejected in clarification).

## Decision 4: Redis is optional and failure-tolerant
- **Rationale**: `REDIS_URL` empty → no-op auditor, as with `SENTRY_DSN`, so local runs and tests need
  no Redis. Connection and command errors are caught, logged with `print` as a warning (the
  project's logging style), and never raised. Socket connect/read timeouts of 2 s bound the delay.
- **Alternatives**: Fail the job when Redis is down (violates FR-008).

## Decision 5: Failed step
- A step that raises is not recorded (no output exists); earlier records remain (FR-009). The
  exception propagates unchanged.
