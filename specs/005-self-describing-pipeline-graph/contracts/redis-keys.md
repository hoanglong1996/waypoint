# Contract: Redis keys and flow description

The only interface between a pipeline and the monitor. Adding a pipeline means writing these keys; the monitor
needs no change. Changing keys or fields is a breaking change.

## Keys
| Purpose | Key | TTL |
|---|---|---|
| Flow description | `etl-audit:{pipeline}:{env}:{run_id}:flow` | `AUDIT_TTL_DAYS` (default 30 d) |
| Step record | `etl-audit:{pipeline}:{env}:{run_id}:step:{NN}-{step}` | same |
| Start marker | `etl-audit:{pipeline}:{env}:{run_id}:running:{NN}-{step}` | 24 h |

`pipeline`: `[a-z0-9][a-z0-9_-]{0,39}`. `env`: no colon. `run_id`: `YYYYMMDDTHHMMSSZ` (UTC start). `NN`: 2+ digit execution index.
Example: `etl-audit:callrail:prod:20261016T020000Z:flow`.
Keys beginning `callrail:audit:` or `callrail:running:` are the old layout and are ignored.

## Flow value (JSON)
```json
{"v": 1, "pipeline": "callrail", "env": "prod", "run_id": "20261016T020000Z",
 "label": "CallRail",
 "groups": [{"key": "callrail", "label": "CallRail"}, {"key": "gads", "label": "Google Ads"}],
 "steps": [
  {"name": "read_callrail_account", "label": "Accounts", "group": "callrail", "inputs": []},
  {"name": "read_callrail_call", "label": "Calls", "group": "callrail",
   "inputs": [{"name": "accounts", "from": "read_callrail_account"}]},
  {"name": "record_call_statistics", "group": "persist", "returns_nothing": true,
   "inputs": [{"name": "call_statistics", "from": "merge_calls_clickview"}], "col": 4, "row": 0.5}
 ]}
```
`label`, `groups`, `group`, `returns_nothing`, `col`, `row` are optional. Unknown fields are ignored.
`inputs[].name` is the key used in the step record's `inputs` counts; `from` is the producing step.

## Step record and marker
As in `specs/001-pipeline-step-audit/contracts/step-record.md` and `specs/004-step-running-indicator/contracts/start-marker.md`, with an added `"pipeline"` field equal to the key's pipeline.

## Rules for writers
1. Write the flow first, before running any step, with the TTL above. Rewriting it is safe.
2. Structure and counts only. Never put item contents, names, numbers or ids from data in labels or step names.
3. Failures writing audit data must not fail the pipeline.
