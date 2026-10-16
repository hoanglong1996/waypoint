# Contract: API additions

Changes to existing endpoints. Nothing is removed or renamed, so older front ends keep working.

## `GET /api/runs`: each run gains

```json
"died": { "judged_at": "2026-10-16T02:09:20Z", "last_seen_at": "2026-10-16T02:07:45Z", "recorded": true }
```

`died` is `null` unless the run is Died. For a Died run: `status` is `"incomplete"`, `running_step` is `null`,
`first_missing_step` is the first unfinished planned step. In `steps`, the open step has:

```json
{ "name": "read_callrail_call", "state": "died", "started_at": "2026-10-16T02:03:00Z", "last_seen_at": "2026-10-16T02:07:45Z" }
```

Later planned steps are `{ "state": "missing", "missing": true }`, never `waiting`. A run with no alive signal
never has `died` set by the heartbeat rule (it may still be `stalled` as today).

## `GET /api/overview`: each pipeline gains

- `card_status` may be `"died"`. Order of rules: `running`, `died`, `stale`, `incomplete`, `lost`, `ok`.
  `needs_attention` is true for `died`, `stale`, `incomplete`, `lost`.
- `latest.died_step` (string or null) and `latest.last_seen_at` (string or null).

## `GET /api/config`: gains

```json
"heartbeat_dead_seconds": 90
```

## Errors

Unchanged. A failed verdict write never changes the status code or body of these endpoints (FR-007d).
