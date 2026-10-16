# Quickstart: validating the packaged product

Run from `integrations/callraill`. Expected outcomes are in bold.

## 1. Library tests (no Redis)

```bash
cd packages/step_audit && pip install -e ".[redis]" && python -m unittest discover tests
```
**All pass**, including: pass-through when unconfigured, Redis failure swallowed, exceptions
propagate, sync/async/method steps, no item content in any written record.

## 2. Adopt in a sample pipeline (US1, US2, SC-001)

```bash
python packages/step_audit/examples/sample_pipeline.py
```
**The file contains one `init(...)` block and three `@audited_step` lines; the function that calls
the steps has no audit code.** With `REDIS_URL` set, `redis-cli --scan --pattern 'etl-audit:sample:*'`
**lists a flow, three running markers and three step records.**

## 3. Whole stack (US3, SC-005)

```bash
docker compose -f deploy/docker-compose.yml --profile sample up --build
```
Open http://localhost:8080. **The `sample` pipeline appears with a 3-node graph and correct counts.**
Stop Redis (`docker compose stop redis`) and rerun the sample: **it exits 0 and prints a warning.**

## 4. CallRail unchanged (US4, SC-006)

```bash
python -m unittest discover tests
git diff --stat src/application/application.py   # audit() calls and inputs= dicts gone
```
**Tests pass; a run against QA writes the same keys and counts as before** (compare a stored
flow/step record from before and after with `redis-cli GET`).

## 5. Unsupported version (FR-013)

Write a flow with `"v": 99` under `etl-audit:demo:qa:...:flow` and load the dashboard.
**It shows "unsupported version" for that run and renders the others.**

## Verified (2026-10-16, on the author's machine)

- Step 1: package tests 58 pass; `black`, `ruff`, `mypy --strict` clean in `packages/step_audit`.
- Step 2/3: `docker compose -f deploy/docker-compose.yml --profile sample up --build` — Redis held
  `flow`, three `running:` and three `step:` keys for `sample`; `/api/runs` returned `flow_status: ok`
  with counts 10 → 5 → none. With Redis stopped the sample exited 0 and printed warnings only.
- Step 4: CallRail records compared with `baseline-records.json` in
  `tests/application/test_application.py` (identical apart from timestamps). The full callrail suite
  still has 8 failing tests (stale `CallRailCall`/`CallStatistics` fixtures, `KeyError: 'content'`) that
  also fail at `HEAD` (9 there), unrelated to this feature.
- Step 5: a flow with `"v": 99` came back as `flow_status: unsupported` while its step records still
  listed. Dashboard tests: 94 backend, 68 front-end pass.
- Not measured: SC-002 (30-minute adoption) and SC-005 (15-minute bring-up) were not timed.
