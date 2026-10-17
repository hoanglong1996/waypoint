# Contract: API additions

Changes to existing endpoints. Nothing is removed or renamed, so older front ends keep working.

## `GET /api/runs`: each run gains

```json
"failed": { "step": "read_callrail_call", "index": 2, "failed_at": "2026-10-17T02:03:41Z" }
```

`failed` is `null` unless a failure **stopped** the run. For such a run: `status` is `"incomplete"`,
`running_step` is `null`, `died` is `null`, `first_missing_step` is the failed step, `ended_at` is `failed_at`.

In `steps`, every step whose latest attempt failed (stopping or not) is:

```json
{ "name": "read_callrail_call", "state": "failed",
  "started_at": "2026-10-17T02:03:00Z", "failed_at": "2026-10-17T02:03:41Z",
  "error": { "type": "requests.exceptions.HTTPError", "message": "502 Server Error ...", "traceback": "  File ..." } }
```

`message` is omitted when it was not stored. Later planned steps of a stopped run are
`{ "state": "missing", "missing": true }`, never `waiting`. A run with no failure item is byte-for-byte as before.
A damaged failure item adds to the run's `unreadable` count and `unreadable_total`.

## `GET /api/overview`: each pipeline gains

- `card_status` may be `"failed"`. Order of rules: `running`, `failed`, `died`, `stale`, `incomplete`, `lost`, `ok`.
  `needs_attention` is true for `failed`, `died`, `stale`, `incomplete`, `lost`.
- Cards are ordered: needs attention first, Failed cards first within it, every other group by label (unchanged).
- `latest.failed_step`, `latest.failed_at`, `latest.error` (`{"type", "message"?}`; no traceback). All `null` unless
  the latest run is Failed.

## Errors, config

Unchanged. No new setting. A failure item that cannot be read never changes a status code.
