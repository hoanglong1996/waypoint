# Data Model: Pipeline Monitor Dashboard

Source records are defined by `specs/001-pipeline-step-audit/contracts/step-record.md`. The app derives the models below in memory; nothing is persisted. The JSON shape served to the UI is in `contracts/api.md`.

## StepRecord (parsed from Redis)
| Field | Type | Rule |
|---|---|---|
| `run_id` | string | `YYYYMMDDTHHMMSSZ`; must equal the id in the key |
| `env` | string | must equal the env in the key |
| `step` | string | non-empty; one of the expected steps |
| `index` | int ≥ 1 | pipeline order |
| `inputs` | map string → int ≥ 0 | may be empty; values may not be null |
| `output` | int ≥ 0 or null | null shows "n/a" |
| `finished_at` | string | UTC ISO-8601 |

A record failing any rule is unreadable: it is dropped, counted against its run (`unreadable`) when the key identifies one (otherwise only in `unreadable_total`), and its step counts as not reported.

## StepDefinition (static, `expected_steps`)
`name`, `group` (CallRail, Google Ads, Merge, Persist), `inputs` (ordered `{name, from}`), `returns_nothing` (bool).

| # | Step | Group | Inputs (from) | Returns nothing |
|---|---|---|---|---|
| 1 | `read_callrail_account` | CallRail | none | no |
| 2 | `read_callrail_call` | CallRail | accounts (1) | no |
| 3 | `read_partners` | Google Ads | none | no |
| 4 | `read_instances` | Google Ads | partners (3) | no |
| 5 | `read_campaigns` | Google Ads | instances (4) | no |
| 6 | `read_gads_clickview` | Google Ads | instances (4) | no |
| 7 | `merge_calls_clickview` | Merge | calls (2), campaigns (5), clickview (6) | no |
| 8 | `record_call_statistics` | Persist | call_statistics (7) | yes |
| 9 | `save_call_statistics` | Persist | call_statistics (7) | yes |

## Run
`env`, `run_id`, `started_at` (from run_id), `ended_at`, `duration_seconds`, `steps` (always 9, ordered; missing ones flagged), `status` ∈ {complete, incomplete}, `first_missing_step`, `missing_count`, `loss_steps`, `unreadable`, `age_seconds`, `stale`. If a step has several records in a run, the one with the latest `finished_at` wins.

## UI-side derived values (pure functions in the front end, unit-tested)
- **metric(step)**: output, or the first input value when output is null; null if the step is missing.
- **headline(run)**: accounts = output of `read_callrail_account`; calls = output of `read_callrail_call`; saved = the `call_statistics` input of `save_call_statistics`; each null when that step is missing.
- **change vs previous run** (delta chip): both values present required; previous 0 and current 0 → 0%; previous 0 → "new"; otherwise `(cur − prev) / prev`, shown as ±%, values within ±0.05% shown as no change. The "previous run" is the immediately preceding run in the list.
- **Series**: sparkline = last 14 runs, trend chart = last 30 runs, both from `metric(step)` oldest to newest; missing steps are gaps (null), not zeros.
