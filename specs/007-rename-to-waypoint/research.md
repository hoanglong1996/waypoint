# Research: Rename to Waypoint

## R1. Is `waypoint-sdk` / `waypoint` free on the public package index?

**Finding** (checked 2026-10-16 against pypi.org): `waypoint-sdk` exists (v0.1.0, an unrelated
"fault-tolerant LLM agent workflow" SDK, uploaded 2026-06-14); `waypoint` exists (v0.2.1, a Halo
Waypoint API client). `waypoint-monitor`, `waypoint-etl`, `waypoint-audit`, `waypoint-pipeline`
returned 404 (free). This was not part of the spec's assumptions; it changes the library names.

**Decision**: install name **`waypoint-etl`**, import name **`waypoint_etl`**.

**Rationale**: pipelines install this library from a git URL, but a plain `pip install waypoint-sdk`
(a typo, a forgotten URL, a requirements file with the bare name) would pull a stranger's package
and run its code. Distinct install *and* import names also avoid two top-level modules both called
`waypoint` shadowing each other in one environment. The product keeps the Waypoint name; only the
library identifier carries the `-etl` suffix, which also says what it is for.

**Alternatives considered**: keep `waypoint-sdk`/`waypoint` and accept the risk (rejected, supply-chain
risk for no gain); `waypoint-audit` (free but describes less than the library does); a namespace like
`knorex-waypoint` (free but ties the name to the company and is longer).

**Follow-up** (spec FR-013): record the check again just before the first tag, since names can be
taken at any time. The library is not published to the public index; do not publish it without
reserving the name first.

## R2. What exactly counts as an "old name"?

**Decision**: the guard list is `etl-audit`, `step_audit`, `step-audit`, `etl-step-audit`,
`Pipeline Monitor`, `pipeline-monitor`, `performance_monitoring_app`, `AUDIT_TTL_DAYS`, and the
storage prefix `pm-` (as `'pm-`). The calls `init`, `audited_step`, `wrap`, and class names such as
`StepAuditor` describe what code does, not the brand, so they stay (spec FR-002 keeps public
behaviour unchanged).

**Rationale**: renaming function names would break every adopter for no naming gain. The generic
English phrase "step audit" in prose is rewritten where it names the product, not policed by the guard.

## R3. Redis key prefix

**Decision**: `waypoint:` replaces `etl-audit:`; the rest of the key (`{pipeline}:{env}:{run_id}:...`)
and all values stay. The prefix lives in one constant on the writer side (`keys.ROOT`) and one
pattern on the reader side (`parsing.py`), so a mismatch is caught by tests on both.

**Rationale**: smallest change that satisfies FR-005. The dashboard reads only the new prefix and
ignores old keys (as it already ignores the pre-005 layout), so there is no dual-read code to remove later.

## R4. Browser storage keys

**Decision**: `pm-env`, `pm-pipeline`, `pm-steps-view`, `pm-theme` → `wp-env`, `wp-pipeline`,
`wp-steps-view`, `wp-theme`. The inline theme script in `index.html` reads `wp-theme`. No migration.

**Rationale**: spec FR-008 accepts losing preferences once; the dashboard already falls back to defaults.

## R5. Environment variable

**Decision**: `AUDIT_TTL_DAYS` → `WAYPOINT_TTL_DAYS` (same default, 30; `Config.AUDIT_TTL_DAYS`
attribute renamed too). `REDIS_URL` unchanged. The library's `init(ttl_days=...)` argument keeps its name.

**Rationale**: matches the spec's "audit-specific names change, generic names stay". Outside
manifests that set `AUDIT_TTL_DAYS` silently fall back to 30, which is the default anyway; the
rename note lists it.

## R6. The baseline fixture

**Decision**: move `specs/006-packaged-audit-sdk/baseline-records.json` to
`tests/application/fixtures/baseline-records.json` and rewrite only the key prefix in it
(`etl-audit:` → `waypoint:`); keep a comment-free JSON file. The CallRail test compares against it.

**Rationale**: a live test must not read from a historical spec folder, and SC-007 says only the
prefix may differ.

## R7. How to keep the rename complete

**Decision**: add `tests/test_no_legacy_names.py` to callrail. It walks the repository from
`integrations/callraill/`, skips `specs/`, `docs/`, `env/`, `.git`, `.claude`, `.specify`,
`.playwright-mcp`, `htmlcov`, `node_modules`, `__pycache__`, `*.egg-info`, binary files, itself and
`deploy/RENAME.md`, and fails with the file, line and pattern for any hit.

**Rationale**: the repo has no CI, so a unit test run by hand is the only enforcement available;
it turns SC-001 from a one-time grep into a standing check. `RENAME.md` is the one place that must
name the old identifiers (the operator needs the old prefix to delete old keys).

## R8. Moving folders and stale installs

**Decision**: `mv` for untracked folders, `git mv` for tracked files. After the move: `pip uninstall -y
etl-step-audit`, delete `packages/waypoint_etl/src/*.egg-info` left from the old name, then
`pip install -e "packages/waypoint_etl[redis]"`. The Docker images are rebuilt with `--build`.

**Rationale**: an editable install of the old name keeps importing `step_audit` from a path that no
longer exists, and the old egg-info otherwise contains the old name (and trips the guard test).

## R9. Order of work

**Decision**: library → CallRail → dashboard → deploy → guard test and docs sweep → full
verification. Each step ends with that component's own tests green, because the library rename
breaks CallRail's imports until step two and the dashboard's key regex until step three.

## R1 re-check before implementation (2026-10-16)

`waypoint-etl`, `waypoint_etl` and `waypoint-monitor` all returned 404 on pypi.org (free). Check again
immediately before the first tagged release; the library must not be published to the public index.
