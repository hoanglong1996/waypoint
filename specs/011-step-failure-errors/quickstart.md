# Quickstart: validating Step Failure Errors

## Automated

```bash
cd packages/waypoint_etl      && python -m unittest discover tests && mypy src && ruff check . && black --check .
cd waypoint_monitor           && python -m unittest discover tests && mypy app && ruff check . && black --check .
cd waypoint_monitor           && node --test static/tests/*.test.mjs
```

Expected coverage (see spec FR ids):

- Library: failure item written for sync and async steps (FR-001); original exception re-raised identical (FR-002);
  store down or unprintable exception or bad `redact` never changes the outcome (FR-003); retry gets a higher index
  (FR-004); caps and kept-last-frames (FR-005); no locals, message off, redact applied (FR-006, FR-006a);
  `BaseException` not recorded; no active auditor = plain call.
- Monitor domain: Failed step beats Running/Stalled/Died (FR-007); stopping failure makes run Failed and blocks a died
  verdict (FR-007, FR-008); handled error leaves the run's status unchanged but the step Failed; later success or
  retry clears it; steps after are `missing` (FR-009); error in API output (FR-010); damaged item counted
  unreadable (FR-016); legacy runs identical (FR-015); the monitor writes nothing for failures (FR-018).
- Front end: card status/rank/reason (FR-011), node state and icon (FR-012), step error block and copy (FR-013),
  History pill and filter (FR-014).

## Manual (end to end, real Redis)

1. Start a throwaway Redis, run the monitor against it (`README.md`, `tests/seed_demo.py`), open the dashboard.
2. Run `packages/waypoint_etl/examples/sample_pipeline.py` modified so the second step raises `ValueError("boom 42")`.
3. Within 10 s the card shows **Failed** (first in "needs attention") naming the step and `ValueError` (SC-001, SC-007).
4. Open the run: headline, `Not reached` steps, Failed node with icon and label; open the step: type, message and trace,
   scroll and Copy (FR-013). Confirm the script exited with the original traceback (SC-003).
5. Re-run with `capture_error_message=False`: grep Redis (`redis-cli --scan`, `GET` the failed key) for `boom 42` - absent (SC-004).
6. Make a step catch its own error and continue: the step shows Failed, the run is not Failed (clarification Q2).
7. Make the step retry successfully: Failed disappears for that step (edge case).
8. Point the pipeline at an unreachable Redis: the original error is still raised, one warning logged (SC-003).
9. Run a pipeline on 0.2.0: display identical to before (SC-006).
10. Browser: inject `<img src=x onerror=alert(1)>` as the message: shown as text, no script runs (R9).
11. History: Failed rows are labelled; "Failed only" lists exactly them.
12. Phone width: trace scrolls inside its box, no horizontal page scroll.

## Baseline (record before implementing)

Recorded 2026-10-17 before any change (the monitor's `.venv` lacks dependencies, so the system Python is used):

- `packages/waypoint_etl`: `PYTHONPATH=src python -m unittest discover tests` 77 pass; mypy, ruff, black clean.
- `waypoint_monitor`: `python -m unittest discover tests` 182 pass; `node --test static/tests/*.test.mjs` 100 pass; mypy and black clean; `ruff check .` reports 1 pre-existing import-order finding in `tests/test_api.py`.

## Results (2026-10-17, after implementation)

Automated:

- `packages/waypoint_etl`: 117 tests pass (was 77); mypy (src and tests), ruff, black clean.
- `waypoint_monitor`: 222 Python tests pass (was 182); 114 `node --test` pass (was 100); mypy, ruff, black clean. The pre-existing ruff import-order finding in `tests/test_api.py` was fixed on the way.

Manual (throwaway Redis in Docker on port 6390, the real library, the real monitor, Playwright at 1200 and 390 px wide):

- Step 2-4: a pipeline whose second step raises `ValueError`: the caller got the original error; the card showed **Failed** (first in "Needs attention", "Failed at clean: ValueError ..."), the run page "A step failed / Stopped at clean", the graph node Failed with its own icon and label and `load` Not reached, the step panel the type, message and trace with a working **Copy** (button read "Copied"). The failure item had a 30-day TTL (SC-001, SC-007).
- Step 5: with `capture_error_message=False` and with a `redact` function the runtime value (an e-mail address built at run time, also held in a local variable) was in none of the Redis values; the default run had it in the message only, by design (SC-004). Note: a literal inside a source line shows in the trace, because source lines are code, not data.
- Step 8: Redis unreachable (port closed): the original error still reached the caller, one warning per failed write, 0.2 s total (SC-003).
- Step 9: demo data in the 0.2.x layout (`tests/seed_demo.py`: running, complete, lost data, died) kept its states; Failed cards led the attention group.
- Step 10: a message of `<img src=x onerror=...><script>...</script>` rendered as text, no element and no script ran.
- Step 11: History labels failed runs with the Failed pill; "Failed only" lists them ("3 failed of 3 runs").
- Step 12: at 390 px the page does not scroll sideways; the trace scrolls inside its box (1064 px content in a 291 px box); max height 256 px.
- Steps 6 and 7 (handled error, retry) are covered by unit tests only (`TestFailedSteps`), not run against a live pipeline.

Observation: the browser caches the monitor's static files by `Last-Modified` heuristics (no `Cache-Control` on `/js/*` and `/styles.css`), so a page opened before a release needs a hard reload to pick up new JS. Pre-existing; not changed here.
