# Quickstart: validating the rename

Run from `integrations/callraill`. Expected outcomes in bold.

## 1. No old names left (US3, SC-001)

```bash
python -m unittest tests.test_no_legacy_names
```
**Passes.** (It lists file, line and pattern for any hit.)

## 2. Library under its new name (US1, SC-004)

```bash
pip uninstall -y etl-step-audit; pip install -e "packages/waypoint_etl[redis]"
cd packages/waypoint_etl && python -m unittest discover tests && black --check . && ruff check . && mypy .
REDIS_URL=redis://localhost:6379/0 python examples/sample_pipeline.py
```
**All pass; the sample prints `Warning: Waypoint ...` text only when Redis is missing, and the old
import `import step_audit` fails with `ModuleNotFoundError`.**

## 3. CallRail unchanged (US4, SC-002, SC-007)

```bash
python -m unittest discover tests
```
**Same results as before the rename: the 8 known stale-fixture failures and nothing new.** The
baseline comparison test passes with only the key prefix different from the old baseline.

## 4. Dashboard (US2, SC-005)

```bash
cd waypoint_monitor && python -m unittest discover tests && node --test static/tests && black --check . && ruff check . && mypy .
```
**Pass.** Open the page: **title and header say "Waypoint Monitor"; the browser's local storage
holds `wp-*` keys, none `pm-*`.**

## 5. Whole stack on an empty store (US2, SC-003, SC-006)

```bash
docker compose -f deploy/docker-compose.yml --profile sample up --build
docker compose -f deploy/docker-compose.yml exec redis redis-cli --scan
```
**The sample's graph appears at http://localhost:8080; every listed key starts with `waypoint:`;
container, volume and image names start with `waypoint`.** Add a stray key `etl-audit:x:qa:r:flow`
with `redis-cli set` and reload: **the page still loads and ignores it.**

## 6. Cutover note (FR-014)

Read `deploy/RENAME.md`: **it holds the rename map, the cutover order (stop old pipelines and
dashboard → delete old keys → deploy new), the key-deletion command, and what outside owners change.**

## Verified (2026-10-16, on the author's machine)

- Step 1: `tests.test_no_legacy_names` passes; a planted legacy name in `src/` made it fail with
  `path:line: pattern` and no line content, then pass again once removed.
- Step 2: library 61 tests pass (58 before + 3 for the key layout); `black`, `ruff`, `mypy --strict`
  clean; `import step_audit` raises `ModuleNotFoundError`; the sample prints
  `Warning: Waypoint disabled, no Redis URL configured`. An old-style adopter needed only 3 changed
  lines (two imports and the `init` call) to run on the new library (SC-004, checked by diff).
- Step 3: callrail has the same 8 failing tests as in `before-results.md` and nothing new; the
  baseline comparison (now `tests/application/fixtures/baseline-records.json`, prefix only changed)
  passes; `mypy .` shows the same 3 errors in the stale tests.
- Step 4: dashboard 95 backend tests (94 + 1 new "other prefix ignored") and 68 front-end tests pass;
  `black`, `ruff`, `mypy` clean; page title is "Waypoint Monitor"; storage keys are `wp-*`.
- Step 5: `docker compose -f deploy/docker-compose.yml --profile sample up --build`: containers and
  network are `waypoint-*`, volume `waypoint_redis-data`, images `waypoint-monitor` and
  `waypoint-sample`; Redis held only `waypoint:sample:...` keys; `/api/pipelines?env=qa` listed
  `sample`, and still did after a key under the previous prefix was added (ignored).
- Step 6: `deploy/RENAME.md` written (map, cutover order, key-deletion command, outside references).
- Not measured: the 10-minute adopter migration time of SC-004 (only the size of the change was
  checked) and publishing/tagging (no tag exists; names re-checked on pypi.org, all free).
