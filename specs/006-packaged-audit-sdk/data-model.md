# Data Model

Stored data is **unchanged** from feature 005 (see
`../005-self-describing-pipeline-graph/contracts/redis-keys.md`). This feature adds in-process
objects only.

## Library entities

| Entity | Fields | Rules |
|---|---|---|
| `PipelineSpec` | `name`, `label?`, `groups`, `steps` | Name `[a-z0-9][a-z0-9_-]{0,39}`; 1–100 steps; validated at `init` |
| `StepSpec` | `name`, `inputs: ((input_name, producer_step),...)`, `label?`, `group?`, `returns_nothing`, `col?`, `row?` | Producer must be an earlier step; input names should equal the decorated function's parameter names |
| `GroupSpec` | `key`, `label` | Referenced groups must be declared |
| `AuditConfig` | `pipeline`, `env`, `redis_url?`, `ttl_days` (default 30) | Built by `init`; `redis_url` empty → no-op store |
| `Registry` (module state) | active `StepAuditor` or none | `init` replaces it; none → decorator pass-through |
| `StepAuditor` | store, spec, env, ttl, run_id, step index | Sequential index per run |

## State transitions of the registry

`unconfigured` --init(valid)--> `active` · `unconfigured` --init(invalid)--> `unconfigured` (warning) ·
`active` --init--> `active` (replaced, warning).

## Step call, as seen by the decorator

1. No active auditor → call the function, return its result.
2. Active → bind arguments to names → write start marker → call function → write record
   (`inputs` counts from bound args that match the step's declared input names, `output` count).
3. Function raises → exception propagates, no finish record. Store errors are logged and swallowed.
