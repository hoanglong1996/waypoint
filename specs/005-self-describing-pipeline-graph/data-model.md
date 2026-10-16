# Data Model: Self-Describing Pipeline Graph

Counts, names and layout hints only. No item contents.

## PipelineSpec (pipeline code, declared once)
| Field | Type | Rule |
|---|---|---|
| name | str | `[a-z0-9][a-z0-9_-]{0,39}`; identifies the pipeline |
| label | str? | display name, ≤60 chars, default = name |
| groups | list[GroupSpec]? | optional; `{key, label}` |
| steps | list[StepSpec] | ≥1, ≤100; declared order is the execution order |

## StepSpec
| Field | Type | Rule |
|---|---|---|
| name | str | unique in the spec; `[a-z0-9_]+`, ≤64 |
| label | str? | ≤40 chars, default = name |
| group | str? | key of a declared group |
| inputs | list[{name, from}] | `from` must be another step of the spec declared earlier |
| returns_nothing | bool | default false (output count not expected) |
| col, row | number? | optional layout hints, ≥0 |

## Flow description (Redis value, `...:flow`)
`{"v": 1, "pipeline", "env", "run_id", "label", "groups": [...], "steps": [...]}` where `steps` = StepSpec as above.
Written once per run at start; TTL = `AUDIT_TTL_DAYS`.

## Step record (Redis value, `...:step:NN-step`)
Unchanged fields from feature 001 (`run_id, env, step, index, inputs, output, finished_at`) plus `pipeline`.
The monitor no longer rejects a step name that is not on a built-in list; it checks only that the name is in the run's flow (otherwise shown as *unplanned*).

## Start marker (Redis value, `...:running:NN-step`)
Unchanged fields from feature 004 plus `pipeline`; TTL 24 h.

## Run (monitor view)
`pipeline, env, run_id, flow_status (ok|missing|invalid), flow_problems[], steps[]` and the existing status/loss/stale fields.
Step `state` ∈ `done, running, stalled, waiting, missing, unplanned`.

## Relationships and rules
- Run identity = (pipeline, env, run_id). Same step name in two pipelines never mixes (keys are pipeline-scoped).
- A step with a record or marker whose name is not in the flow is `unplanned`.
- A planned step with no record or marker keeps today's rules: `waiting` after a live running step, else `missing`.
- Flow `invalid` = unknown `v`, not JSON, no steps; individual bad steps/inputs are dropped and listed in `flow_problems` and the rest is drawn.
