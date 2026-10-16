# Data Model: History-First Pipelines with Run Detail Pages

No stored data changes. This describes the front-end state that is new or changed. Run fields are those of
`mapRun` in `static/js/api.js` (unchanged).

## Route (extended)

| Field | Meaning |
|---|---|
| `name` | `home`, `pipeline`, `run`, or `notfound` |
| `id` | Pipeline name (for `pipeline` and `run`) |
| `page` | For `pipeline`: always `history` (the former `latest` value is gone) |
| `env` | For `pipeline`: optional filter. For `run`: required, the run's environment |
| `runId` | For `run`: `YYYYMMDDTHHMMSSZ` |

Validation: `runId` must match `^\d{8}T\d{6}Z$` and `env` must be non-empty, otherwise `notfound`.

## View kinds

`home`, `history`, `run`, `notfound` (was `home`, `latest`, `history`, `notfound`), plus `runnotfound`: the pipeline
exists but the run does not.

## App state

- `runs`: the pipeline's runs for one environment (history: the filtered list; run page: up to 100).
- The selected run is derived from the route (`runs.find(r => r.id === route.runId)`), never stored separately.
- Removed: `openRunId`, `lastFocus` and the drawer state.

## Relationships

Pipeline 1—N Run (per environment). A run page is addressed by (pipeline, env, runId), which is unique.
