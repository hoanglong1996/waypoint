# Data Model: the Rename Map

Nothing stored changes except the key prefix (see [contracts/redis-keys.md](contracts/redis-keys.md)).
This document is the single list of old → new names that the tasks and `deploy/RENAME.md` copy.

## Names

| Kind | Old | New |
|---|---|---|
| Product | (none; "Pipeline Monitor" for the UI) | Waypoint |
| Library install name | `etl-step-audit` | `waypoint-etl` |
| Library import name | `step_audit` | `waypoint_etl` |
| Library folder | `packages/step_audit/` | `packages/waypoint_etl/` |
| Library source folder | `src/step_audit/` | `src/waypoint_etl/` |
| Library tag format | `step-audit-vX.Y.Z` | `waypoint-etl-vX.Y.Z` |
| Dashboard display name | Pipeline Monitor | Waypoint Monitor |
| Dashboard folder | `performance_monitoring_app/` | `waypoint_monitor/` |
| Dashboard image | `pipeline-monitor` | `waypoint-monitor` |
| Deploy bundle | (unnamed) | Waypoint Stack |
| Compose project | `deploy` (folder default) | `waypoint` (`name:` in the file) |
| Sample image | `deploy-sample` (default) | `waypoint-sample` |
| Redis key prefix | `etl-audit:` | `waypoint:` |
| Record-lifetime env var | `AUDIT_TTL_DAYS` | `WAYPOINT_TTL_DAYS` |
| Config attribute | `Config.AUDIT_TTL_DAYS` | `Config.WAYPOINT_TTL_DAYS` |
| Browser storage keys | `pm-env`, `pm-pipeline`, `pm-steps-view`, `pm-theme` | `wp-env`, `wp-pipeline`, `wp-steps-view`, `wp-theme` |

## Unchanged on purpose

`init`, `audited_step`, `wrap`, `PipelineSpec`, `StepSpec`, `GroupSpec`, `assert_spec_matches`,
class names (`StepAuditor`, `StepAuditStore`, `RedisStepAuditStore`, `NoopStepAuditStore`), the
`REDIS_URL` setting, the `FLOW_VERSION` (1), the dashboard's inner `app` package, the `deploy/`
folder, and all step names of CallRail.

## Live-file inventory (to touch; counts from a search on 2026-10-16, excluding specs 001–007 and `docs/`)

| Area | Files |
|---|---|
| Library (`packages/step_audit/`) | `pyproject.toml`, `README.md`, `examples/sample_pipeline.py`, `src/step_audit/*.py` (8), `tests/*.py` (7), stale `*.egg-info` |
| Dashboard (`performance_monitoring_app/`) | `pyproject.toml`, `Dockerfile`, `README.md`, `app/domain/parsing.py`, `static/index.html`, `static/js/ui.js`, `static/js/app.js`, `tests/` (fakes, seed_demo, test_api, test_parsing, test_analysis, test_redis_store, others that use the prefix), `static/tests/*.mjs` that use storage keys |
| Deploy (`deploy/`) | `docker-compose.yml`, `Dockerfile.sample`, `README.md` |
| CallRail | `main.py`, `Dockerfile`, `pyproject.toml`, `README.MD`, `.env.qa`, `.env.prod`, `src/utils/config.py`, `src/application/pipeline_spec.py`, 9 use-case files, `tests/application/test_application.py`, `tests/application/test_pipeline_spec.py` |

## Rules

- A name in the "Old" column must not appear in any live file after the rename, except in
  `deploy/RENAME.md` (the rename note) and in specs/design history.
- The writer's prefix constant and the reader's pattern must agree; a test on each side asserts the
  literal `waypoint:`.
