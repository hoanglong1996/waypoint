# Quickstart: validating the running indicator

Prerequisites: Redis reachable (local or tunnel), `.env.qa`, Python 3.12. Run pipeline commands from `integrations/callraill`, monitor commands from `performance_monitoring_app`.

## 1. Automated checks

```bash
# pipeline
python -m unittest discover tests && black --check . && ruff check . && mypy .
# monitor
cd performance_monitoring_app && pytest && node --test static/tests/
```

Expected: all pass; new tests cover marker-before-run, swallowed marker failure, `running`/`waiting`/`stalled` states, status `running` not stale, signature ignores counters.

## 2. See it live (no real pipeline needed)

1. Start the monitor: `python -m app.main -c qa` (or the documented command) and open it with the Graph view.
2. In a second terminal write a fake run to Redis: finish records (`callrail:audit:qa:<run_id>:01-…` to `03-…`) for steps 1–3 and a start marker for step 4 (`callrail:running:qa:<run_id>:04-read_instances`).
3. Within 5 s the page shows step 4 with a spinner, "Running · N s" counting up, steps 5-9 "Waiting", and no stale or stopped warning (spec FR-003/004/010).
4. Write the finish record for step 4 and a marker for step 5: within ~5 s step 4 shows counts and step 5 is running, without touching the page; selected step and view are unchanged (US2).
5. Stop writing: after `STALL_SECONDS` (set `STALL_SECONDS=30` to try) the step shows "Stalled", no animation (US3).
6. Enable OS "reduce motion": spinner and bar are static, text still reads "Running".

## 3. Real run

Run the pipeline with `-c qa` while the monitor is open; watch the running step advance through all 9 steps and the run end as complete.
