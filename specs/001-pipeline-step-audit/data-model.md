# Data Model: Pipeline Step Audit Trail

## Pipeline Run
- `env`: from `-c` (prod / qa)
- `run_id`: UTC start time, `YYYYMMDDTHHMMSSZ`; generated once per `run_pipeline` call

## Step Record
| Field | Type | Notes |
|---|---|---|
| `run_id` | string | as above |
| `env` | string | as above |
| `step` | string | e.g. `read_callrail_account` |
| `index` | int | 1-based order in the pipeline |
| `inputs` | object name → int | empty object when the step has no input |
| `output` | int or null | item count; null when the step returns nothing |
| `finished_at` | string | UTC ISO-8601 |

Counting rule: `None` → null; list/tuple/set → length; any other object → 1.
Validation: no field may hold item contents. TTL: 30 days from write (configurable by
`AUDIT_TTL_DAYS`, default 30).

## Step list
1 `read_callrail_account` (in: none) · 2 `read_callrail_call` (in: `accounts`) ·
3 `read_partners` (none) · 4 `read_instances` (`partners`) · 5 `read_campaigns` (`instances`) ·
6 `read_gads_clickview` (`instances`) · 7 `merge_calls_clickview` (`calls`, `campaigns`,
`clickview`) · 8 `record_call_statistics` (`call_statistics`; output null) ·
9 `save_call_statistics` (`call_statistics`; output null). Location-code step is part of 9's
preparation and is not recorded separately.
