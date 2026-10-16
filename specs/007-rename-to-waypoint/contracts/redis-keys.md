# Contract: Redis keys (Waypoint)

Supersedes the prefix in `specs/005-self-describing-pipeline-graph/contracts/redis-keys.md`.
**Only the first segment changed (`etl-audit` → `waypoint`)**; everything after it, every value and
every TTL is exactly as in 005 (record format version `v` stays 1).

| Item | Key | TTL |
|---|---|---|
| Flow description | `waypoint:{pipeline}:{env}:{run_id}:flow` | `WAYPOINT_TTL_DAYS` (default 30 d) |
| Step record | `waypoint:{pipeline}:{env}:{run_id}:step:{NN}-{step}` | same |
| Start marker | `waypoint:{pipeline}:{env}:{run_id}:running:{NN}-{step}` | 24 h |

`pipeline`: `[a-z0-9][a-z0-9_-]{0,39}`. `env`: no colon. `run_id`: `YYYYMMDDTHHMMSSZ` (UTC start).
`NN`: 2+ digit execution index. Values: see 005.

## Reader rules

- The dashboard scans only `waypoint:*`. Keys under any other prefix are ignored, never counted as
  unreadable, and never cause an error.
- Writers (`waypoint_etl`) write only `waypoint:*`.

## Compatibility

None. Old keys are not migrated or read; the operator deletes them (see `deploy/RENAME.md`).

## Later additions

`:alive` (written by the pipeline) and `:died` (written by the monitor) are defined in
`specs/009-run-liveness-heartbeat/contracts/redis-keys.md`. The monitor's one write is the `:died` item; every other
item is still written only by the pipeline.
