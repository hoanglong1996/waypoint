# Quickstart: validating the self-describing graph

Prerequisites: a Redis you can write to (local `docker run -p 6380:6379 redis`), Python 3.12, Node 18+.

## 1. Automated checks
```bash
cd integrations/callraill
python -m unittest discover tests && black --check . && ruff check . && mypy .
cd performance_monitoring_app && python -m unittest discover tests && node --test static/tests
```
Expect all green.

## 2. A pipeline the monitor has never seen (US1, US2)
1. Start the monitor: `REDIS_URL=redis://localhost:6380/0 python -m app.main`.
2. Write a three-step flow and records for pipeline `demo` using the key layout in [contracts/redis-keys.md](contracts/redis-keys.md) (a small helper script in tests prints the `redis-cli` commands).
3. Open http://localhost:8080, choose `demo` in the picker: three nodes, two arrows with counts, labels as declared. No monitor edit.
4. Also write `callrail` data: switching pipelines never mixes runs or steps.

## 3. Interrupted run (US3)
Write a six-step flow and records for only three steps: all six nodes show, last three not reached.

## 4. Bad input (US4)
- Records and markers but no `flow` key: simplified graph with "no flow description".
- Flow with an input from an unknown step, a cycle, or `"v": 9`: valid part drawn, problem listed, page keeps working.
- A key `callrail:audit:prod:...` in the old layout: not shown, no error.

## 5. Real pipeline
Run the CallRail job against the QA Redis (`python main.py -c qa`); the monitor shows the nine-step graph with names and groups from the stored flow. Rename a step in `pipeline_spec.py`, rerun, and confirm the new graph appears with no monitor change (SC-001).

## Run record

- 2026-10-16, read from an actual run against a throwaway Redis (port 6390): the real `CALLRAIL_PIPELINE` stopped after 3 steps and an unrelated two-step `sample` pipeline were written through `StepAuditor`; an old-layout key was added. `/api/pipelines` listed both; the CallRail run showed all 9 planned steps (3 done, 6 not reached, stop point `read_instances`); the old key was ignored. In a browser the picker switched between the two and the graph drew labels and groups from the stored flow. Stored values were checked by hand: names and counts only.
- Not done: the real CallRail job against the QA Redis and the step-rename check (SC-001) need QA credentials; the rename path is covered by `tests/test_analysis.py::TestFlowDrivenRuns`.
