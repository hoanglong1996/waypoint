# Data Model: Step Failure Errors

## Failure item (written by the library; one per failed attempt of a step)

Key: `waypoint:{pipeline}:{env}:{run_id}:failed:{NN}-{step}` (`NN` = attempt index, two digits or more, as for step
records). TTL = the run's `ttl_days`.

| Field | Type | Rule |
|---|---|---|
| `v` | int | `1` |
| `pipeline`, `env`, `run_id`, `step` | string | equal the key's |
| `index` | int ≥ 1 | the attempt index (equals `NN`) |
| `started_at` | string | UTC `YYYY-MM-DDTHH:MM:SSZ`, when the attempt began (the same value as its start marker) |
| `failed_at` | string | UTC, when the error was caught |
| `error.type` | string | fully qualified class name (`ValueError`, `requests.exceptions.HTTPError`), ≤ 200 chars |
| `error.message` | string, optional | cleaned, ≤ 500 chars; **absent** when message capture is off or cleaning failed |
| `error.traceback` | string | frames only (no variable values), ≤ 8192 UTF-8 bytes, last frames kept |

Contains names, times and the shortened diagnostic text only. Invalid items (bad JSON, wrong identity, missing
`error.type`, `index` or `failed_at` not valid) are skipped and counted as unreadable for their run, like step records.

## Attempt, step and run state (derived in the monitor)

Per run and step name, over **attempts** identified by `index`:

| Source | Gives |
|---|---|
| finish record | attempt `index` finished (Done) |
| start marker | attempt `index` started |
| failure item | attempt `index` failed |

`latest_attempt(step)` = the highest `index` among those sources. Step state:

| Latest attempt is | State |
|---|---|
| a failure item | **Failed** (never Running, Stalled or Died) |
| a start marker with no finish of the same or higher index | Running / Stalled / Died, as today |
| a finish record | Done, as today |

Ties between sources at the same index do not occur for one attempt except marker + failure (the failure wins)
and marker + finish (the finish wins, as today).

**Stopping failure**: the run's failure whose `index` is greater than the `index` of every other finish record, start
marker and failure item in the run. At most one exists. If the run has one, the run is **Failed**.

| Run condition | Result |
|---|---|
| a stopping failure exists | run Failed; `status` stays `incomplete`; `died` is null (no verdict is judged or written); planned steps after the failed one are `missing` |
| failed steps exist but none stopped the run | those steps are Failed; run status is whatever the other rules give (a failed planned step counts as missing, so a finished run is Incomplete, not Completed) |
| no failure item | exactly as before this feature |

`ended_at` / `age_seconds` use the latest of finish times and the `failed_at` of current failures. A failed step does
not make a run "unfinished" for the heartbeat rule (it is terminal).

### Run and card status priority

Run (per spec FR-008): Running, **Failed**, Died, Stale, Incomplete, Lost data, Completed.
Card (`card_status`): `running`, `failed`, `died`, `stale`, `incomplete`, `lost`, `ok`. `needs_attention` is true for
`failed`, `died`, `stale`, `incomplete`, `lost`.

## Step (API additions)

A failed step: `{"name", "state": "failed", "started_at", "failed_at", "error": {"type", "message"?, "traceback"}}`
(see [contracts/api.md](contracts/api.md)). It has no counts: `inputs` empty and `output` null in the front end.

## Run (API additions)

`failed`: null, or `{"step", "index", "failed_at"}` for the stopping failure.

## Overview card summary (API additions)

`latest.failed_step`, `latest.failed_at`, `latest.error` (`{"type", "message"?}`, no traceback), all null unless the
latest run is Failed.

## Library settings (init)

| Setting | Default | Meaning |
|---|---|---|
| `capture_error_message` | `True` | store a shortened, cleaned message; `False` stores type and traceback only |
| `redact` | `None` | `(str) -> str` applied to every message before it is shortened and stored |

## State transitions of one step

```text
(not started) -> Running -> Done
                      \-> Failed -> (retry begins) -> Running -> Done | Failed
Running -> Stalled -> Died            (unchanged; Failed takes precedence once a failure item exists)
```
