# Quickstart: validating Run Duration and Run Events

Prerequisites: Python 3.12, Node 20+, a local Redis (`docker run -p 6379:6379 redis`), and the monitor's virtualenv
(`waypoint_monitor/.venv`). Paths are relative to the repository root. Contracts: [contracts/](contracts/);
entities: [data-model.md](data-model.md).

## Baseline (record before implementing)

Run once and write the pass counts here so later failures can be attributed.

```bash
cd packages/waypoint_etl && python -m unittest discover tests && mypy && ruff check . && black --check .
cd ../../waypoint_monitor && python -m unittest discover tests && node --test static/tests/*.test.mjs
```

| Suite | Baseline |
|---|---|
| library unit tests | 117 pass; mypy, ruff, black clean |
| monitor unit tests | 222 pass (needs a working venv: the repo's `.venv` is broken, a fresh one from requirements.txt was used); mypy `app`, ruff, black clean |
| front-end tests | 114 pass |

## 1. Automated checks (every change)

```bash
cd packages/waypoint_etl && python -m unittest discover tests && mypy && ruff check . && black --check .
cd ../../waypoint_monitor && python -m unittest discover tests && mypy && ruff check . && black --check . \
  && node --test static/tests/*.test.mjs
```

All green, including the regression tests for runs written by library 0.2.0 and 0.3.0.

## 2. Seed demo data

```bash
cd waypoint_monitor
python -m tests.seed_demo qa            # now also seeds: finish records with started_at/duration_ms,
                                        # an old-style run (no start times), a slow run, and events
python -m app.main -c qa                # http://localhost:8080
```

## 3. Duration (spec User Stories 1 and 2)

1. Open a completed demo run: the headline shows the total, each step a duration, the slowest step is tagged
   "Slowest" in List and in Graph (the tag has an icon and text, not only colour).
2. Open the old-style run (no step start times): step durations show `≈` and the tooltip says "estimated from the
   previous step"; the run total is exact.
3. Open a running run: the open step and the run show `…` and the value increases on refresh.
4. Open the failed demo run: the failed step shows time until the failure.
5. History of the demo pipeline: Duration column present; "Run duration" chart shows median and p95; the seeded slow
   run is labelled "Slower than usual" and no other run is. A pipeline with fewer than 5 completed runs says
   "Not enough history yet" and flags nothing.
6. Failed and Died runs do not move the median (compare with the stat line before and after seeding them).

## 4. Events (spec User Stories 3 to 7)

1. Open any run → **Events**. Without any author events (old-style run) the list is the derived timeline and the note
   says the pipeline does not send events.
2. Open the demo run that has author events: derived and author entries interleave in time order; a message sent inside a
   step is chip-linked to that step. Filter by level and by step; the URL hash carries the filters; reload keeps them.
3. Failed run: the timeline has an `error` entry for the step with the error type and message, a "Run stopped at"
   entry, and no traceback text.
4. Run in progress: add events while watching:

   ```bash
   python - <<'PY'
   import waypoint_etl
   from waypoint_etl import PipelineSpec, StepSpec
   spec = PipelineSpec("demo_events", steps=(StepSpec("load"),))
   waypoint_etl.init(pipeline=spec, redis_url="redis://localhost:6379/0", env="qa")
   @waypoint_etl.audited_step("load")
   def load():
       import time
       for i in range(5):
           waypoint_etl.log(f"batch {i}", rows=100 * i)
           time.sleep(2)
       waypoint_etl.warn("slow source", retries=2)
       waypoint_etl.error("one batch skipped")
   load()
   PY
   ```

   New entries appear within one refresh without losing the filters; afterwards the Home card and the History row show
   `1 warning` and `1 error`.
5. Limits: send 5,000 info events plus 3 errors in one run:

   ```bash
   python - <<'PY'
   import waypoint_etl
   from waypoint_etl import PipelineSpec, StepSpec
   waypoint_etl.init(pipeline=PipelineSpec("demo_cap", steps=(StepSpec("load"),)), redis_url="redis://localhost:6379/0", env="qa")
   @waypoint_etl.audited_step("load")
   def load():
       for i in range(5000): waypoint_etl.log(f"i{i}")
       for i in range(3): waypoint_etl.error(f"e{i}")
   load()
   PY
   redis-cli llen waypoint:demo_cap:qa:<run_id>:events:info    # 500
   redis-cli llen waypoint:demo_cap:qa:<run_id>:events:error   # 3
   ```

   The timeline shows the note "N events were dropped"; all 3 errors and every derived entry are present.
6. Privacy: run with `init(..., capture_error_message=False)` and send `log("secret-marker 123", note="secret-marker")`;
   `redis-cli --scan` + `lrange` show no `secret-marker`, the entry shows level, step and time with "message not stored".
7. Redis down: stop Redis, run a pipeline that logs 1,000 events: the pipeline finishes with the same result and exit
   code, at most one warning per minute is printed, and the run time is within a few percent of a run with no events.

## 5. Compatibility

- Point the *previous* monitor image at the new data (events lists, finish fields): it still shows runs as before.
- Run the *previous* library (0.3.0) against the new monitor: durations are approximate, the timeline is derived, no
  banner or error text mentions missing data.
- Read-only: with the monitor's account limited to `SCAN`, `MGET`, `PING`, `PTTL`, `LLEN`, `LRANGE` (+ `SET` on
  `waypoint:*:died`), everything above works; without `LLEN`/`LRANGE` every existing page still loads and the Events
  tab shows the derived timeline only (counts are 0).

## Results

Run on 2026-10-17 against a throwaway Redis 7 (`redis:7-alpine` on port 6390, the user's own Redis was not touched).

**Automated** (section 1): library 178 tests (baseline 117), monitor 341 (baseline 222), front end 148 (baseline 114);
`mypy --strict`, `ruff` and `black --check` clean in both packages.

**Manual** (sections 2-5), desktop 1440 and phone 390 (no horizontal scroll), light and dark:

| Check | Result |
|---|---|
| Section 3.1-3.4: exact and approximate step durations, Slowest tag in List and Graph, running run with `…`, failed step duration | Pass. Two layout bugs found and fixed: duration icon stacked above its text in the List and on Home cards, and a duration label overflowing the "Slowest" Graph node. |
| Section 3.5-3.6: History duration column and chart, only the 35 min run flagged, "Not enough history yet" below 5 runs, failed runs not in the median | Pass. The phone layout overlapped the date with a long "Slower than usual" pill: fixed. |
| Section 4.1-4.3: derived timeline for an old-style run, interleaving, filters in the address, failure as an error entry without a trace | Pass. Back-to-back steps in the same whole second were listed start-before-finish: fixed (research R4). |
| Section 4.4: counts on Home and History, a step's own events | Pass. Found that a running run's counting-up duration made every refresh redraw the page (details closed again): fixed by ignoring it in the redraw signatures, with tests. |
| Section 4.5: 5,000 info events plus 3 errors | `LLEN` info 500, error 3, TTL 30 days; 5,003 `log` calls took 0.02 s; the timeline says "100 events were dropped" in the demo run. |
| Section 4.6: capture off | No marker text in the stored events or the failure record (the source line of a traceback is code and shows by design; the test builds the text at run time). Markup typed into a message is shown as text. |
| Section 4.7: Redis down | Same results, one throttled warning for events, about +6% on a tiny 1,000-event loop (noise level). |
| Section 5: library 0.3.0 against the new monitor | Durations exact where a start marker still exists, derived timeline of 6 entries, no banner or error text. |
| Section 5: limited permission | With an account lacking `LLEN`/`LRANGE`: every page loads, counts are 0, the timeline holds only derived entries. With them: events and counts shown. |
| Section 5: previous monitor against the new data | Not run (no old image available); covered by `test_parsing` (unknown fields ignored) and the key layout (event lists live under keys no earlier scan pattern matches). |

**Known limits**: a retried step shows only its latest attempt in the timeline; a sub-second ambiguity remains for
events sent in the first fraction of a second after a back-to-back step started; `waypoint-etl` 0.4.0 is not tagged
yet (tag `waypoint-etl-v0.4.0` at release; the READMEs pin 0.3.0 until then).
