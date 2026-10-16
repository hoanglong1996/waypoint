# Rename note: everything is now Waypoint

This is the one live file that names the previous identifiers, because moving an installation needs
them (to find and delete old data). Earlier specs (`specs/001`–`006`) and the design notes under
`docs/` are history and keep the old names; nothing else in the repository does.

## Old → new

| Kind | Old | New |
|---|---|---|
| Product | Pipeline Monitor (UI name only) | Waypoint |
| Library install name | `etl-step-audit` | `waypoint-etl` |
| Library import name | `step_audit` | `waypoint_etl` |
| Library folder | `packages/step_audit/` | `packages/waypoint_etl/` |
| Library tag format | `step-audit-vX.Y.Z` | `waypoint-etl-vX.Y.Z` |
| Dashboard | Pipeline Monitor | Waypoint Monitor |
| Dashboard folder | `performance_monitoring_app/` | `waypoint_monitor/` |
| Dashboard image | `pipeline-monitor` | `waypoint-monitor` |
| Deploy bundle | (unnamed) | Waypoint Stack, compose project `waypoint` |
| Redis key prefix | `etl-audit:` | `waypoint:` |
| Record-lifetime setting | `AUDIT_TTL_DAYS` | `WAYPOINT_TTL_DAYS` (same default, 30) |
| Browser storage keys | `pm-env`, `pm-pipeline`, `pm-steps-view`, `pm-theme` | `wp-env`, `wp-pipeline`, `wp-steps-view`, `wp-theme` |

Unchanged: `init`, `audited_step`, `wrap`, `PipelineSpec`, `StepSpec`, `GroupSpec`,
`assert_spec_matches`, `REDIS_URL`, the record format (`v` = 1) and every step name.

The library install name differs from the first suggestion (`waypoint-sdk`) because that name, and
`waypoint`, are already used by other projects on the public package index.

## Cutover order

Records are not migrated. Pipelines and dashboard must switch together, otherwise the new dashboard
cannot see a pipeline that still writes the old prefix, and the old dashboard cannot see a renamed one.

1. Stop the old pipelines (or let their current run finish) and stop the old dashboard.
2. Delete the old keys:
   `redis-cli --scan --pattern 'etl-audit:*' | xargs -r redis-cli unlink`
   Old compose installation: `docker compose -f deploy/docker-compose.yml -p deploy down -v` if its
   Redis volume is no longer wanted, and `docker rmi deploy-monitor deploy-sample` for the old images.
3. Deploy the new dashboard (Waypoint Monitor, image `waypoint-monitor`).
4. Deploy the pipelines on `waypoint-etl` and start their runs.
5. Open the dashboard: each pipeline appears after its first run. Browser-stored choices (view mode,
   selected pipeline, theme) reset once.

## What an adopter changes

Only the install name (`etl-step-audit` → `waypoint-etl`) and the import lines (`step_audit` →
`waypoint_etl`). Calls, arguments and the pipeline declaration stay as they are.

## What owners of outside references must update

Deployment definitions outside this repository (job manifests, CI pipelines, Jenkins jobs) that mention:

- the dashboard folder (`performance_monitoring_app/` → `waypoint_monitor/`) or its image name;
- the library folder or `pip` URL (`packages/step_audit` → `packages/waypoint_etl`, tag format above);
- the setting `AUDIT_TTL_DAYS` (renamed `WAYPOINT_TTL_DAYS`; if left unset the default of 30 days applies);
- any Redis tooling that lists or deletes keys by the old prefix.
