# Contract: Redis keys (additions)

Extends `specs/007-rename-to-waypoint/contracts/redis-keys.md`. Existing keys, values and TTLs are unchanged;
record format version stays 1.

| Item | Key | Writer | TTL |
|---|---|---|---|
| Alive signal | `waypoint:{pipeline}:{env}:{run_id}:alive` | pipeline (library) | `WAYPOINT_TTL_DAYS`, refreshed each beat |
| Died verdict | `waypoint:{pipeline}:{env}:{run_id}:died` | monitor | remaining TTL of the alive item (fallback 30 d) |

Values: see [data-model.md](../data-model.md). Example:

```json
{"v": 1, "pipeline": "callrail", "env": "prod", "run_id": "20261016T020000Z", "beat_at": "2026-10-16T02:07:45Z"}
{"v": 1, "pipeline": "callrail", "env": "prod", "run_id": "20261016T020000Z",
 "judged_at": "2026-10-16T02:09:20Z", "last_seen_at": "2026-10-16T02:07:45Z"}
```

## Rules

1. The library writes the alive item immediately on `init`, then every `heartbeat_seconds` (default 15), until
   `waypoint_etl.clear()` or a repeated `init`. Failures are logged, never raised. Items hold identities and
   times only, never item contents.
2. The monitor writes the died item only with `SET NX`; it never overwrites, modifies or deletes any key.
   A missing write permission is tolerated (the run is shown as Died per view; a warning is logged).
3. Readers scan these keys by the exact suffixes `:alive` and `:died`. A monitor built before this feature does
   not scan them, so it ignores both and counts nothing unreadable.
4. A run with no alive item is a legacy run: never judged Died by the heartbeat rule.
5. Clock rule: `beat_at` uses the pipeline host's UTC clock and is compared with the monitor's clock; both must
   agree within `HEARTBEAT_DEAD_SECONDS`.
6. Permissions: the monitor's Redis account needs `SCAN`, `MGET`, `PING` (as today) plus `SET` and `PTTL` for the
   keys matching `waypoint:*:died` (and `PTTL` for `waypoint:*:alive`).
