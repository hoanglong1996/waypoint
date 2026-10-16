---

description: "Task list for Rename the Product to Waypoint"
---

# Tasks: Rename the Product to Waypoint

**Input**: Design documents from `/specs/007-rename-to-waypoint/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md (the rename map), contracts/redis-keys.md, quickstart.md

**Tests**: Included. Existing tests move and are updated with their code; two tests are new (prefix rule on the dashboard reader, guard against leftover old names). No live Redis, CallRail, Google Ads or Sentry in unit tests.

**Organization**: grouped by user story. All paths are relative to `integrations/callraill/` and use the **new** names unless a step says "old". Names to apply are the rename map in `data-model.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 library under its new name · US2 operator stack and key prefix · US3 rename is complete and verifiable · US4 CallRail unchanged

## Notes from implementation

- T022 copied (not moved) the baseline fixture, so `specs/006` stays untouched as history.
- The guard test (T028) removes path references into `specs/NNN-…` and `docs/…` before matching,
  because live files legitimately point at history folders that keep their original names.
- Files the plan did not list but that were renamed: `app/main.py` (FastAPI title, CLI help),
  `app/domain/flow.py` (docstring), `static/styles.css` (header comment and the `pm-` keyframes, now `wp-`).
- T032 needed no change beyond the above.

## Rules for the whole change

- Do not reformat files wholesale. Run `black`/`ruff --fix` only on files you edited, then check `git diff --stat` shows no unrelated files (the last feature's formatter touched unrelated code once).
- Do not edit `specs/001`–`006` or `docs/` (history, excluded by FR-010).
- Untracked folders (`packages/`, `performance_monitoring_app/`, `deploy/`) are moved with `mv`; tracked files with `git mv`. Never delete a folder before its replacement is complete.

---

## Phase 1: Setup

- [X] T001 Record the "before" results to compare against later (SC-002, SC-007): run `python -m unittest discover tests` in `integrations/callraill`, in `packages/step_audit`, and in `performance_monitoring_app` (plus `node --test static/tests` there). Expected today: library 58 pass; dashboard 94 backend + 68 front-end pass; callrail has exactly 8 failing tests (stale `CallRailCall`/`CallStatistics` fixtures and `KeyError: 'content'`). Write the pass/fail counts and the 8 test names to `specs/007-rename-to-waypoint/before-results.md`
- [X] T002 [P] Re-check the public package index for the new names (FR-013): request `https://pypi.org/pypi/waypoint-etl/json`, `https://pypi.org/pypi/waypoint_etl/json` and `https://pypi.org/pypi/waypoint-monitor/json`; all must be 404. Append the date and outcome to R1 in `specs/007-rename-to-waypoint/research.md`. If any name is taken, STOP and ask the user for a different library name before continuing

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: move the library folder and clear the stale install; every later task imports the new name.

- [X] T003 Run `pip uninstall -y etl-step-audit` and delete `packages/step_audit/src/etl_step_audit.egg-info/` (the stale install would keep importing from a path that is about to vanish)
- [X] T004 Move `packages/step_audit/` to `packages/waypoint_etl/` and `packages/waypoint_etl/src/step_audit/` to `packages/waypoint_etl/src/waypoint_etl/` with `mv` (untracked). Do not edit contents yet. Confirm `ls packages` shows only `waypoint_etl`

**Checkpoint**: the tree has the new library folders; nothing imports yet.

---

## Phase 3: User Story 1 - Library under its new name (Priority: P1) 🎯 MVP

**Goal**: install `waypoint-etl`, `import waypoint_etl`, every message says Waypoint, behaviour identical.

**Independent Test**: quickstart step 2; the library suite is green and `import step_audit` fails.

- [X] T005 [P] [US1] Edit `packages/waypoint_etl/pyproject.toml`: `name = "waypoint-etl"`, description mentions Waypoint, `[tool.setuptools.package-data]` key `waypoint_etl`; keep `version = "0.1.0"` and the `redis` extra
- [X] T006 [US1] In every file of `packages/waypoint_etl/src/waypoint_etl/` replace imports `step_audit` → `waypoint_etl` (`__init__.py`, `auditor.py`, `decorator.py`, `registry.py`, `testing.py`, `spec.py`, `stores.py`); in `keys.py` set `ROOT = "waypoint"` and fix the module docstring to point at `specs/007-rename-to-waypoint/contracts/redis-keys.md`
- [X] T007 [US1] Rename the user-visible text in `packages/waypoint_etl/src/waypoint_etl/` (FR-009): in `registry.py` the four `init` warnings become `Warning: Waypoint disabled, invalid pipeline spec: ...`, `Warning: Waypoint disabled, no Redis URL configured`, `Warning: Waypoint disabled, invalid Redis URL: ...`, `Warning: waypoint_etl.init called again, replacing the previous configuration`; in `auditor.py` the prints become `Warning: Waypoint flow write failed: ...`, `Warning: Waypoint start marker failed for {name}: ...`, `Warning: Waypoint record failed for {name}: ...`, `Warning: step {name} is not in pipeline spec {pipeline}` (unchanged) and `Warning: pipeline spec invalid, flow not recorded: ...` (unchanged); update module docstrings (`__init__.py`, `auditor.py`, `decorator.py`) to say Waypoint and `waypoint_etl.init(...)`. Keep the substrings the tests check (`invalid pipeline spec`, `replacing`, `no Redis URL`, `invalid Redis URL`)
- [X] T008 [P] [US1] Update the library tests in `packages/waypoint_etl/tests/` (`test_auditor.py`, `test_decorator.py`, `test_init.py`, `test_second_pipeline.py`, `test_stores.py`, `test_unconfigured.py`): imports `step_audit` → `waypoint_etl`, every literal key `etl-audit:` → `waypoint:`, `import step_audit` → `import waypoint_etl`, `step_audit.init` → `waypoint_etl.init`, `step_audit.audited_step` → `waypoint_etl.audited_step`, test class text where it names the old product; add `packages/waypoint_etl/tests/test_keys.py` asserting `keys.ROOT == "waypoint"`, `flow_key("p", "qa", "R") == "waypoint:p:qa:R:flow"`, and the step/marker key formats from `contracts/redis-keys.md`
- [X] T009 [P] [US1] Update `packages/waypoint_etl/README.md` and `packages/waypoint_etl/examples/sample_pipeline.py`: title "Waypoint library (`waypoint-etl`)", install lines `pip install -e "packages/waypoint_etl[redis]"` and the git URL with `.../step-audit-v0.1.0#subdirectory=...` replaced by tag `waypoint-etl-v0.1.0` and `subdirectory=integrations/callraill/packages/waypoint_etl`, all snippets `import waypoint_etl`, key references point at `specs/007-rename-to-waypoint/contracts/redis-keys.md`, "Develop" section paths
- [X] T010 [US1] Install and verify: `pip install -e "packages/waypoint_etl[redis]"`; in `packages/waypoint_etl` run `python -m unittest discover tests`, `black --check .`, `ruff check .`, `mypy .` (all clean, 58+ tests); `python -c "import step_audit"` must raise `ModuleNotFoundError`; `python examples/sample_pipeline.py` prints a `Warning: Waypoint disabled, no Redis URL configured` line and `loaded 5 rows`

**Checkpoint**: the library is complete under the new name. CallRail does not import yet (US4).

---

## Phase 4: User Story 2 - Operator stack and key prefix (Priority: P1)

**Goal**: Waypoint Monitor reads only `waypoint:`; Waypoint Stack starts with Waypoint names; cutover is documented.

**Independent Test**: quickstart steps 4–6.

### Dashboard

- [X] T011 [US2] Move `performance_monitoring_app/` to `waypoint_monitor/` with `mv` (untracked). Update the root `pyproject.toml` `[tool.mypy] exclude` list to `["^packages/", "^waypoint_monitor/", "^env/"]` and its comment
- [X] T012 [P] [US2] In `waypoint_monitor/app/domain/parsing.py` set `ROOT = "waypoint"` (line 10) and fix the docstring on `pipeline_of_key` (line 148); search `waypoint_monitor/app/` for any other literal `etl-audit` (including the SCAN pattern builder in `app/infrastructure/redis_store.py`) and replace it, so reader and writer agree on `waypoint:`
- [X] T013 [P] [US2] Update the dashboard tests in `waypoint_monitor/tests/` (`fakes.py`, `seed_demo.py`, `test_api.py`, `test_parsing.py`, `test_analysis.py`, `test_redis_store.py`, and any other file containing `etl-audit`): every literal key `etl-audit:` → `waypoint:`; in `test_parsing.py` add a test that a key `etl-audit:demo:prod:20260101T000000Z:flow` and a step key under the old prefix are ignored (not parsed, not counted as unreadable, no exception) and in `test_redis_store.py` a test that the scan pattern used starts with `waypoint:` (FR-006)
- [X] T014 [P] [US2] Front end in `waypoint_monitor/static/`: `index.html` title and `.brand__name` text `Pipeline Monitor` → `Waypoint Monitor` and the inline theme script key `'pm-theme'` → `'wp-theme'`; `js/ui.js` `STEPS_VIEW_KEY` value `pm-steps-view` → `wp-steps-view`; `js/app.js` keys `pm-env`, `pm-pipeline`, `pm-theme` → `wp-env`, `wp-pipeline`, `wp-theme`; update any `static/tests/*.mjs` that mention a storage key or the old title; grep `static/` for any other "Pipeline Monitor" (empty-state text, aria labels, footer)
- [X] T015 [P] [US2] Update `waypoint_monitor/pyproject.toml` (project name `waypoint-monitor`), `waypoint_monitor/Dockerfile` (comments/labels if they name the old product) and `waypoint_monitor/README.md`: title "Waypoint Monitor", the `docker build -t waypoint-monitor .` example, key contract link `../specs/007-rename-to-waypoint/contracts/redis-keys.md` and the key prefix in the "What it reads" section, "Add a pipeline" section naming `waypoint-etl` / `waypoint_etl.init` / `@waypoint_etl.audited_step` and `../packages/waypoint_etl/README.md`, the localStorage names `wp-steps-view` / `wp-pipeline`, links to `../deploy/README.md`
- [X] T016 [US2] Verify the dashboard: in `waypoint_monitor/` run `python -m unittest discover tests` (94 + the new tests pass), `node --test static/tests` (68 pass), `black --check .`, `ruff check .`, `mypy .`

### Deploy bundle

- [X] T017 [P] [US2] Edit `deploy/docker-compose.yml`: first line comment "Waypoint Stack: Redis + dashboard (+ sample pipeline)"; add top-level `name: waypoint`; `monitor` build context `../waypoint_monitor` with `image: waypoint-monitor`; `sample` build `dockerfile: deploy/Dockerfile.sample` with `image: waypoint-sample`; keep service names `redis`, `monitor`, `sample`, volume `redis-data`; keep `REDIS_URL` and `ENVIRONMENTS`
- [X] T018 [P] [US2] Edit `deploy/Dockerfile.sample`: `COPY packages/waypoint_etl /tmp/waypoint_etl`, `pip install --no-cache-dir "/tmp/waypoint_etl[redis]"`, `COPY packages/waypoint_etl/examples/sample_pipeline.py .`
- [X] T019 [US2] Rewrite `deploy/README.md` with Waypoint names: title "Waypoint Stack", the compose commands unchanged, "install the library" using `waypoint-etl` and tag `waypoint-etl-vX.Y.Z`, release steps with the new folder `packages/waypoint_etl`, version file paths, and a link to `RENAME.md` under a "Renaming from the previous names" heading
- [X] T020 [US2] Create `deploy/RENAME.md` (FR-014): (1) the rename map from `data-model.md`; (2) cutover order: stop old pipelines and the old dashboard → delete old keys with `redis-cli --scan --pattern 'etl-audit:*' | xargs -r redis-cli unlink` (and `docker compose ... down -v` for the old compose project name `deploy` if its volume is no longer wanted) → deploy the new dashboard → deploy pipelines on `waypoint-etl` → start runs; (3) what an adopter changes: install name `etl-step-audit` → `waypoint-etl` and the import `step_audit` → `waypoint_etl` (nothing else); (4) what owners of outside references must update: dashboard folder and image names, `AUDIT_TTL_DAYS` → `WAYPOINT_TTL_DAYS`, library tag format, `pip` git URL subdirectory; (5) a line stating that `specs/001`–`006` and `docs/` are history and keep the old names; (6) the mixed-version warning (old pipeline writes are invisible to the new dashboard and vice versa). This is the only live file allowed to contain the old identifiers
- [X] T021 [US2] Verify the stack on an empty store (SC-003, SC-005, SC-006): `docker compose -f deploy/docker-compose.yml --profile sample up --build -d`; the sample's graph appears at http://localhost:8080 (`/api/pipelines?env=qa` lists `sample`); `redis-cli --scan` shows only `waypoint:` keys; `docker ps`, `docker volume ls` and `docker images` show `waypoint`-prefixed names; set a stray key `etl-audit:x:qa:20260101T000000Z:flow` with `redis-cli set` and confirm `/api/pipelines?env=qa` still answers and does not list `x`; then `docker compose -f deploy/docker-compose.yml --profile sample down -v`

**Checkpoint**: dashboard and deploy bundle are complete; US1 + US2 is a shippable Waypoint without CallRail.

---

## Phase 5: User Story 4 - CallRail unchanged (Priority: P2)

**Goal**: CallRail uses the renamed library and prefix; steps, counts and graph identical.

**Independent Test**: quickstart step 3; results equal `before-results.md` from T001.

- [X] T022 [US4] Move the baseline fixture: create `tests/application/fixtures/`, `mv specs/006-packaged-audit-sdk/baseline-records.json tests/application/fixtures/baseline-records.json`, and rewrite every `"key"` value's prefix `etl-audit:` → `waypoint:` in it (nothing else); change `BASELINE` in `tests/application/test_application.py` to `os.path.join(os.path.dirname(__file__), "fixtures", "baseline-records.json")`
- [X] T023 [US4] Replace the import name `step_audit` → `waypoint_etl` in `main.py` (`import waypoint_etl`, `waypoint_etl.init(...)`), `src/application/pipeline_spec.py`, the nine use-case files (`src/application/use_cases/extract/callrail_account_uc.py`, `callrail_call_uc.py`, `partner_uc.py`, `instance_uc.py`, `campaign_uc.py`, `gads_clickview.py`, `transform/calls_statistics_uc.py`, `transform/recording_call_statistics_uc.py`, `load/call_statistics.py`), `tests/application/test_application.py` and `tests/application/test_pipeline_spec.py` (`from waypoint_etl.testing import assert_spec_matches`, `from waypoint_etl.spec import validate_spec`); keep each file's import order valid for `ruff` (the library is third-party, goes before `src.` imports)
- [X] T024 [P] [US4] Rename the audit setting: in `src/utils/config.py` `AUDIT_TTL_DAYS = env_int("AUDIT_TTL_DAYS", 30)` → `WAYPOINT_TTL_DAYS = env_int("WAYPOINT_TTL_DAYS", 30)` and the comment block "STEP AUDIT" → "WAYPOINT" pointing at `packages/waypoint_etl`; in `main.py` `ttl_days=Config.WAYPOINT_TTL_DAYS`; in `.env.qa` line 38 `AUDIT_TTL_DAYS=30` → `WAYPOINT_TTL_DAYS=30` and in `.env.prod` line 38 `# AUDIT_TTL_DAYS=30` → `# WAYPOINT_TTL_DAYS=30` (do not print or alter any other line of these files; they contain credentials)
- [X] T025 [P] [US4] Edit `Dockerfile`: `COPY packages/waypoint_etl /tmp/waypoint_etl`, `RUN pip install --no-cache-dir "/tmp/waypoint_etl[redis]" && rm -rf /tmp/waypoint_etl`, comment "Install the Waypoint library"; edit `tests/application/test_application.py` literal key `etl-audit:callrail:qa:RUN:step:01-read_callrail_account` → `waypoint:callrail:qa:RUN:step:01-read_callrail_account`
- [X] T026 [P] [US4] Rewrite the `README.MD` section "Step Audit (Redis)" as "Waypoint (step tracking)": library `waypoint-etl` (`packages/waypoint_etl`), `waypoint_etl.init` and `@audited_step`, the env table row `WAYPOINT_TTL_DAYS` (default 30) replacing `AUDIT_TTL_DAYS`, every key `etl-audit:callrail:...` → `waypoint:callrail:...` including the `redis-cli` examples, links to `packages/waypoint_etl/README.md`, `deploy/README.md` and `specs/007-rename-to-waypoint/contracts/redis-keys.md`, and the install line `pip install -e "packages/waypoint_etl[redis]"`; the line saying older `callrail:audit:*` keys are not read stays and gains "and neither are `etl-audit:*` keys" only if it can be written without the old prefix literal, otherwise refer to `deploy/RENAME.md`
- [X] T027 [US4] Verify CallRail: `python -m unittest discover tests` gives exactly the failures listed in `before-results.md` (the 8 stale-fixture tests) and no others, with `tests.application.test_application` and `tests.application.test_pipeline_spec` passing (baseline comparison included); `mypy .` reports only the 3 errors it reported before (stale tests); `ruff check` on the files you edited is clean; `git diff --stat` lists only intended files

**Checkpoint**: all three components and CallRail run on Waypoint names.

---

## Phase 6: User Story 3 - The rename is complete and verifiable (Priority: P2)

**Goal**: a standing test proves no old names remain in live files.

**Independent Test**: quickstart step 1.

- [X] T028 [US3] Create `tests/test_no_legacy_names.py` (`unittest`, typed): walk the tree from `Path(__file__).resolve().parents[1]`; skip directories `specs`, `docs`, `env`, `.git`, `.claude`, `.specify`, `.playwright-mcp`, `htmlcov`, `node_modules`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, and any `*.egg-info`; skip binary files (undecodable as UTF-8), this test file, and `deploy/RENAME.md`; fail with `path:line: pattern` for every line matching any of: `etl-audit`, `step_audit`, `step-audit`, `etl-step-audit`, `Pipeline Monitor`, `pipeline-monitor`, `performance_monitoring_app`, `AUDIT_TTL_DAYS`, `'pm-` and `"pm-`. Include one test that the skip list does not hide `src/`, `tests/`, `packages/`, `waypoint_monitor/` or `deploy/` (assert those top-level folders are walked)
- [X] T029 [US3] Run `python -m unittest tests.test_no_legacy_names`; for every hit it lists, rewrite the line with the name from the rename map (README text, comments, docstrings, test names, docker files, `.env` comments). Repeat until it passes. Do not add exclusions to make it pass except `deploy/RENAME.md`
- [X] T030 [US3] Search for folder-path leftovers the pattern list cannot catch: `grep -rn "packages/step_audit\|performance_monitoring_app\|src/step_audit" --exclude-dir=specs --exclude-dir=docs --exclude-dir=env --exclude-dir=.git .` returns nothing outside `deploy/RENAME.md`; open every README, `Dockerfile*`, `docker-compose.yml` and `pyproject.toml` and confirm each path in it exists (US3 scenario 2)

**Checkpoint**: SC-001 holds and is enforced by a test.

---

## Phase 7: Polish

- [X] T031 Walk `specs/007-rename-to-waypoint/quickstart.md` steps 1–6 in order and add a dated "Verified" section to it with what was run and the results (counts compared with `before-results.md`); note anything not measured (SC-004's 10-minute adopter migration is checked by following the "what an adopter changes" paragraph of `deploy/RENAME.md` on a copy of an old-style adopter and confirming only the install name and import lines change)
- [X] T032 Update `specs/006-packaged-audit-sdk/` only if a later tool needs a path that moved: none expected; confirm `grep -rn "baseline-records.json" tests specs/007-rename-to-waypoint` points to `tests/application/fixtures/`
- [X] T033 Mark every completed task `[X]` in this file, then report to the user: what changed, results versus `before-results.md`, the library-name deviation (`waypoint-etl`, not `waypoint-sdk`) and the reason, the reminder that the library must not be published to the public index without reserving the name, and the outside references the user must update (`knx-etl-tpi-scripts`, Jenkins) per `deploy/RENAME.md`

---

## Dependencies & Execution Order

- Setup (T001–T002) → Foundational (T003–T004) → US1 → US2 → US4 → US3 → Polish.
- **US1 before everything else**: the library rename (T005–T010) provides the prefix the dashboard reads and the import CallRail needs.
- **US2** needs T006 (prefix constant) only for the end-to-end check (T021); T011–T020 can start once T004 is done, but T021 needs T010 and T016.
- **US4** needs US1 (import) and uses nothing from US2.
- **US3** runs last because its guard test checks every other phase's output.
- Within US2: dashboard (T011–T016) and deploy (T017–T020) are independent groups; T021 needs both.

```text
Setup → Foundational → US1 → ┬→ US2 (dashboard ∥ deploy) ─┐
                             └→ US4 (CallRail) ───────────┴→ US3 (guard) → Polish
```

## Parallel opportunities

- Setup: T001 and T002 together.
- US1: T005, T008, T009 together after T006–T007.
- US2: T012, T013, T014, T015 together after T011; T017 and T018 together (and alongside the dashboard group).
- US4: T024, T025, T026 together after T023.
- US4 and US2 can proceed in parallel once US1 is done (different folders).

## Implementation Strategy

- **MVP = Setup + Foundational + US1** (T001–T010): the library under its new name with the new prefix, proven by its own suite and the sample. Stop and validate with quickstart step 2.
- Then **US2** (dashboard, deploy bundle, cutover note), then **US4** (CallRail), so the system is consistent end to end.
- Finish with **US3** (guard test, sweep) and Polish. Do not merge the rename in pieces: the key prefix changes the writer (US1) and the reader (US2) together, so ship US1 + US2 + US4 as one change, and note in the PR that outside deployment definitions need the `deploy/RENAME.md` updates.
