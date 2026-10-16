# Results before the rename (2026-10-16)

| Suite | Result |
|---|---|
| `packages/step_audit`: `python -m unittest discover tests` | 58 tests, OK |
| `performance_monitoring_app`: `python -m unittest discover tests` | 94 tests, OK |
| `performance_monitoring_app`: `node --test static/tests` | 68 pass, 0 fail |
| callrail: `python -m unittest discover tests` | 27 tests, 8 errors (all pre-existing, stale fixtures) |
| callrail: `mypy .` | 3 errors in 2 files (same stale tests) |

The 8 pre-existing callrail errors:

- `test_merge_calls_clickview_external_platform`
- `test_merge_calls_clickview_match`
- `test_merge_calls_clickview_no_match_campaign`
- `test_merge_calls_clickview_no_match_gclid`
- `test_get_campaign_by_instance_success`
- `test_get_campaigns`
- `test_save_failure`
- `test_save_success`
