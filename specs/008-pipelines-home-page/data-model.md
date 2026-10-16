# Data Model: Pipelines Home Page

No new stored data. Everything is derived on read from existing records (read only).

## PipelineSummary (response item of `/api/overview`)

| Field | Type | Rule |
|---|---|---|
| `name` | string | Pipeline name as stored in keys. Identity; unique. |
| `label` | string | Friendly name from the newest run's flow description, else `name`. |
| `environments` | list of string | Environments in which this pipeline has at least one run, in `ENVIRONMENTS` order. Never empty. |
| `latest` | RunSummary or null | Newest run across all environments. Null only when keys exist but no run can be built. |
| `card_status` | enum | `running`, `stale`, `incomplete`, `lost`, `ok`. First match wins (see below). |
| `needs_attention` | bool | True for `stale`, `incomplete`, `lost`. |

## RunSummary (newest run, trimmed)

| Field | Type | Source |
|---|---|---|
| `run_id` | string | `YYYYMMDDTHHMMSSZ`. |
| `env` | string | Environment of this run. Shown as the card's tag. |
| `status` | `complete` / `incomplete` / `running` | Existing run status. |
| `stale` | bool | Existing: not running and older than `STALE_HOURS`. |
| `started_at`, `ended_at` | UTC ISO-8601 | Existing. |
| `age_seconds` | int | Existing. |
| `loss_steps` | list of string | Existing: steps with output 0 and some input. |
| `first_missing_step` | string or null | Existing. |
| `stalled_step`, `stalled_seconds` | string / int or null | The first stalled step and how long it has run. |
| `unreadable` | int | Existing. |
| `headline` | list of 3 `{key, step, label, value}` | first, largest middle, last step of the run's flow (null value when not reported). |

## Card status (first match wins)

`running` > `stale` > `incomplete` (stopped or stalled) > `lost` > `ok`. Attention group: `stale`, `incomplete`, `lost`.
Order on the page: attention group first, then the rest; each A to Z by label.

## Environment filter (browser state, not stored)

| Field | Rule |
|---|---|
| `env` | In the History address as `?env=`. Default when absent: `prod` if the pipeline has prod runs, else the environment of `latest`. An `env` without runs is kept and shown with a "no runs" hint. Options: the pipeline's `environments`, prod first then A to Z. |

## Relationships

Pipeline 1 to many Runs. Run belongs to exactly one Environment. A pipeline can have runs in several
environments; the card uses the newest, the History page uses the one chosen.
