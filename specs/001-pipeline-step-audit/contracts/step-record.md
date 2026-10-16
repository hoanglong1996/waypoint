# Contract: Step Record in Redis

> **Superseded key layout**: keys and fields are now pipeline-scoped (`etl-audit:{pipeline}:{env}:{run_id}:...`, plus a `pipeline` field). See `specs/005-self-describing-pipeline-graph/contracts/redis-keys.md`. The text below is kept as history.

The only external interface is the stored record that operators read.

**Key**: `callrail:audit:{env}:{run_id}:{index:02d}-{step}`
Example: `callrail:audit:prod:20261015T020000Z:01-read_callrail_account`

**Value** (JSON string):

```json
{"run_id": "20261015T020000Z", "env": "prod", "step": "read_callrail_account",
 "index": 1, "inputs": {}, "output": 10, "finished_at": "2026-10-15T02:00:07Z"}
```

**TTL**: 30 days (`AUDIT_TTL_DAYS`).

**Configuration**: `REDIS_URL` (empty disables auditing), `AUDIT_TTL_DAYS` (default 30).
Changing key layout or fields is a breaking change for anyone reading the records.
