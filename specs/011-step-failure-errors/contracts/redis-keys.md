# Contract: Redis keys (addition)

Extends `specs/007-rename-to-waypoint/contracts/redis-keys.md` and `specs/009-run-liveness-heartbeat/contracts/redis-keys.md`.
Existing keys, values and TTLs are unchanged; record format version stays 1.

| Item | Key | Writer | TTL |
|---|---|---|---|
| Failure | `waypoint:{pipeline}:{env}:{run_id}:failed:{NN}-{step}` | pipeline (library) | `WAYPOINT_TTL_DAYS` |

Example (message capture on):

```json
{"v": 1, "pipeline": "callrail", "env": "prod", "run_id": "20261017T020000Z",
 "step": "read_callrail_call", "index": 2,
 "started_at": "2026-10-17T02:03:00Z", "failed_at": "2026-10-17T02:03:41Z",
 "error": {"type": "requests.exceptions.HTTPError",
           "message": "502 Server Error: Bad Gateway for url: https://api.example/calls",
           "traceback": "  File \"/app/src/infrastructure/extract/calls.py\", line 52, in execute\n    response.raise_for_status()\n  ...\nrequests.exceptions.HTTPError: 502 Server Error: Bad Gateway for url: https://api.example/calls\n"}}
```

With `capture_error_message=False` the `message` field is absent and the traceback's last line is the type only.

## Rules

1. Written once per failed attempt, when the step's function raises an `Exception`. A retry has a higher `NN`.
   Failures to write are logged, never raised. Items hold names, times and the shortened diagnostic text only.
2. The start marker of the failed attempt is left in place; readers decide by attempt index (see data-model.md).
3. Readers scan by the exact pattern `waypoint:{pipeline}:{env}:*:failed:*`. A monitor built before this feature
   does not scan it, so it ignores the item and counts nothing unreadable; the step then looks as it did before.
4. Permissions: the monitor needs nothing new (`SCAN`, `MGET`, `PING`, and the `died` write of spec 009). The
   monitor never creates, changes or deletes a `failed` item.
5. Size: `message` ≤ 500 characters, `traceback` ≤ 8192 UTF-8 bytes, `type` ≤ 200 characters. Readers enforce the
   same caps.
