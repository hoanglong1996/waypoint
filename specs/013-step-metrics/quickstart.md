# Quickstart: validating step metrics

Prerequisites: Redis reachable at `redis://localhost:6379/0` (or the fake store used by the tests), repository checked out.

## 1. Automated

```bash
cd packages/waypoint_etl && python -m unittest discover tests   # includes test_metrics, test_metric_writer
cd ../../waypoint_monitor && python -m unittest discover tests  # includes test_metrics, parsing, analysis, api additions
node --test static/tests/*.test.mjs                              # metric trend, flags, formatting
mypy --strict app && ruff check . && black --check .             # each package
```

## 2. End to end

1. Start the monitor with demo data (`python -m tests.seed_demo`, which now includes metrics) and open the run page:
   a step shows a Metrics block; a declared `rejected` over its limit shows the badge in the list and the graph.
2. Run a real pipeline with the library:

```python
import waypoint_etl
from waypoint_etl import Metric, PipelineSpec, StepSpec

SPEC = PipelineSpec("demo", (StepSpec("load", metrics=(Metric("rejected", unit="rows", warn_above=100),)),))
waypoint_etl.init(pipeline=SPEC, redis_url="redis://localhost:6379/0", env="qa")

@waypoint_etl.audited_step("load")
def load():
    for batch in range(5):
        waypoint_etl.metric("rejected", 40, mode="add")
        waypoint_etl.metric("peak_batch", batch * 100, mode="max")
        time.sleep(2)
    return []
```

Expected: while `load` runs, its details show `rejected` growing (40, 80, ...) within about 6 seconds; `peak_batch` appears
undeclared; when `rejected` passes 100 the badge appears; after the step ends the final values stay (`rejected 200 rows`,
`peak_batch 400`).
3. Run it three more times with different counts and open History: the Metric trend card lists step `load`, metric
   `rejected`, shows one point per run, a median after the minimum number of runs, and the 100 threshold line.
4. Stop Redis during a run: the pipeline finishes with the same result and exit code; no exception from `metric()`.
5. Point the new monitor at runs written by library 0.4.0: pages render unchanged, no banners.

## 3. Success-criteria spot checks

- SC-002: 8 threads x 1,000 `add` calls give exactly 8,000 (unit test).
- SC-003: a 100,000-call loop with and without `metric()` differs by 5% or less (timing test, generous bound in CI).
- SC-005: values equal to, above and below a threshold behave as specified (unit tests on both sides).

## Baseline (before the change, 2026-10-17)

- `packages/waypoint_etl`: 178 tests OK; `ruff`, `black --check` clean; `mypy --strict src` clean.
- `waypoint_monitor`: 343 tests OK; `ruff`, `black --check` clean; `mypy --strict app` clean; front end `node --test` 148 pass.
- The Python environment has an older non-editable `waypoint-etl` 0.4.0 installed. Library tests must run against the
  working tree: `cd packages/waypoint_etl && PYTHONPATH=src python -m unittest discover tests`.

## Results (after the change, 2026-10-17)

- Library: 210 tests OK (`PYTHONPATH=src`); `ruff`, `black --check`, `mypy --strict src` clean.
- Monitor: 379 tests OK; `ruff`, `black --check`, `mypy --strict app` clean; front end 165 pass, 0 fail.
- Hand-run (Redis in a throwaway container on port 6390, monitor on 8099, both removed afterwards):
  - Real library pipeline `livedemo` with `rejected` (declared, warn above 100, mode `add`, +40 every 2 s) and
    `peak_batch` (undeclared, mode `max`): `/api/runs` showed `rejected` 40, 80, 160 (flag `above`), 200 and
    `peak_batch` 0 to 400 while the step ran, and the same final values after it finished.
  - Run page (list and graph, phone width): table with `140 rows`, `above 100`, `not reported` handled, badge
    `1 metric over limit` in the list and `1 over limit` on the graph node.
  - History: Metric trend card with step and metric pickers, a gap for the run that did not report, median line, limit
    line, diamonds on points over the limit. No console errors.
- Not exercised by hand: stopping Redis mid-run (covered by `test_metric_writer` with a failing and a hanging store and
  by `test_unconfigured` with a raising store), and data written by library 0.4.0 read by the new monitor (covered by
  the existing old-run tests, which pass unchanged apart from the new run-level `metrics_over` key).
