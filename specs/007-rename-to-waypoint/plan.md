# Implementation Plan: Rename the Product to Waypoint

**Branch**: `007-rename-to-waypoint` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-rename-to-waypoint/spec.md`

## Summary

Rename the product, its three components and the Redis key prefix to Waypoint in one coordinated
change, with no behaviour change. Library: `etl-step-audit`/`step_audit` → **`waypoint-etl`/`waypoint_etl`**
(not `waypoint-sdk`/`waypoint` as first suggested: both are already taken on the public package
index, see research R1). Dashboard: Pipeline Monitor → **Waypoint Monitor** (`waypoint_monitor/`).
Deploy bundle → **Waypoint Stack**. Key prefix `etl-audit:` → `waypoint:`. No migration; a rename
note gives the operator cutover order. A guard test keeps old names from coming back (SC-001).

## Technical Context

**Language/Version**: Python 3.12 (callrail, dashboard), Python ≥3.10 (library); plain ES modules for the dashboard front end

**Primary Dependencies**: none new

**Storage**: Redis; only the key prefix changes, structure and values unchanged (contract: [contracts/redis-keys.md](contracts/redis-keys.md))

**Testing**: `python -m unittest discover tests` (callrail), same inside the library and dashboard folders, `node --test static/tests` (dashboard); plus a new guard test for leftover old names

**Target Platform**: Linux containers, local runs

**Project Type**: library + web service + deployment bundle (no behaviour change)

**Performance Goals**: n/a

**Constraints**: public library calls unchanged (`init`, `audited_step`, `wrap`, spec types, testing helper); record format version stays 1; PII rule unchanged (names and counts only); repo has no CI, so every suite is run by hand

**Scale/Scope**: about 50 live files plus renamed folders; exact inventory in [data-model.md](data-model.md)

## Constitution Check

| Principle | Status |
|---|---|
| I. Layered architecture | PASS. No structural change; imports change from `step_audit` to `waypoint_etl`. |
| II. Caller PII | PASS. Nothing stored changes; the existing "counts only" test is carried over. |
| III. Type safety | PASS. `mypy --strict`, ruff, black stay clean in callrail, library and dashboard; the root `mypy` exclude list is updated for the new folder names. |
| IV. Test coverage | PASS. All tests move with their code; a new guard test covers the rename itself. |
| V. Resilient execution | PASS. Behaviour untouched. |
| Technical constraints: new env vars documented in `README.MD` | PASS. `WAYPOINT_TTL_DAYS` is documented there; `AUDIT_TTL_DAYS` removed. |

No violations; Complexity Tracking not needed. Re-checked after Phase 1: still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/007-rename-to-waypoint/
├── plan.md
├── research.md
├── data-model.md          # the rename map (every old → new name) and the live-file inventory
├── quickstart.md
├── contracts/
│   └── redis-keys.md      # the live key contract (supersedes 005's prefix)
└── tasks.md               # /speckit-tasks
```

### Source Code (changes, repository root `integrations/callraill/`)

```text
packages/step_audit/                   → packages/waypoint_etl/
  src/step_audit/                      → src/waypoint_etl/       (ROOT = "waypoint", messages, docstrings)
  pyproject.toml                       name = "waypoint-etl"
  README.md, examples/, tests/         updated names
performance_monitoring_app/            → waypoint_monitor/
  app/domain/parsing.py                key regexes use the new prefix
  static/index.html, js/ui.js, js/app.js   title, brand, storage keys pm-* → wp-*
  pyproject.toml, Dockerfile, README.md, tests/   updated names
deploy/
  docker-compose.yml                   name: waypoint; images waypoint-monitor, waypoint-sample
  Dockerfile.sample                    installs waypoint-etl
  README.md                            updated names
  RENAME.md                            NEW rename note: map, cutover order, outside references
main.py, Dockerfile, pyproject.toml    imports, install path, mypy exclude list
src/application/**, src/utils/config.py   imports; AUDIT_TTL_DAYS → WAYPOINT_TTL_DAYS
.env.qa, .env.prod                     WAYPOINT_TTL_DAYS (if the variable is set there)
README.MD                              "Step Audit (Redis)" section → Waypoint
tests/application/*                    imports; baseline moves to tests/fixtures/
tests/test_no_legacy_names.py          NEW guard test
```

**Structure Decision**: rename folders to match the product names; the dashboard's inner Python
package (`app`) and the `deploy/` folder keep their names because neither is an old name. Folders
that are not yet tracked by git (`packages/`, `performance_monitoring_app/`, `deploy/`) are moved
with plain `mv`; tracked files with `git mv`. Specs 001–006 and `docs/design/` are history and are
not edited.
