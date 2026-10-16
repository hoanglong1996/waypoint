# Data Model: Run Liveness Heartbeat

## Alive signal (written by the library, one per run)

| Field | Type | Rule |
|---|---|---|
| `v` | int | `1` |
| `pipeline` | string | equals the key's pipeline |
| `env` | string | equals the key's env |
| `run_id` | string | equals the key's `YYYYMMDDTHHMMSSZ` |
| `beat_at` | string | UTC `YYYY-MM-DDTHH:MM:SSZ`, time of the latest beat |

One item per run, overwritten each beat. TTL = the run's `ttl_days`, refreshed on each beat. Invalid or unreadable
items are treated as absent for that run (legacy behaviour) and never counted unreadable.

## Died verdict (written by the monitor, at most one per run)

| Field | Type | Rule |
|---|---|---|
| `v` | int | `1` |
| `pipeline`, `env`, `run_id` | string | equal the key's |
| `judged_at` | string | UTC time of the first judgement |
| `last_seen_at` | string | the alive item's `beat_at` at judgement time |

Created with `SET NX`, never modified or deleted by the monitor. TTL = remaining TTL of the run's alive item
(fallback 30 days). Contains no business data.

## Run liveness (derived, in the monitor)

| State | Condition |
|---|---|
| Unknown (legacy) | no valid alive item and no verdict |
| Alive | valid alive item, `now - beat_at <= HEARTBEAT_DEAD_SECONDS`, no verdict |
| Died | verdict exists, or (alive item present, work unfinished, `now - beat_at > HEARTBEAT_DEAD_SECONDS`) |

Transitions: Unknown and Alive may become Died; Died never changes (FR-007a). A run whose planned steps are all
recorded is not newly judged Died (FR-013).

## Run (API) additions

| Field | Type | Meaning |
|---|---|---|
| `died` | object or null | `{ "judged_at", "last_seen_at", "recorded" }`; null unless Died. `recorded` is false until the verdict is stored. |

Step state `died` is added to `done`, `missing`, `running`, `stalled`, `waiting`, `unplanned`. A died step carries
`started_at` and `last_seen_at`. For a Died run: `status` is `incomplete`, `running_step` is null,
`first_missing_step` is the first step not finished.

## Settings

| Name | Default | Where |
|---|---|---|
| `HEARTBEAT_DEAD_SECONDS` | 90 | monitor env |
| `heartbeat_seconds` | 15 | `waypoint_etl.init(...)` argument; `None` or `<= 0` turns the heartbeat off |
