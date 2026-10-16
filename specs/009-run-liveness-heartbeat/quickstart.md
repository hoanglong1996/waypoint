# Quickstart: validating run liveness

Prerequisites: Python 3.12, a throwaway Redis (e.g. `docker run --rm -p 6390:6379 redis:7`), the repository
checked out. Use QA data only. Contracts: [redis-keys](contracts/redis-keys.md), [api](contracts/api.md).

## 1. Automated checks (no Redis)

```bash
cd packages/waypoint_etl && python -m unittest discover tests            # heartbeat tests included
cd ../../waypoint_monitor && python -m unittest discover tests            # parsing, judgement, API, store
node --test static/tests
black . && ruff check . && mypy .                                         # in both folders
```

Expected: all green; the legacy no-heartbeat tests are unchanged (SC-003).

## 2. Dead run (User Story 1, SC-001)

```bash
export REDIS_URL=redis://localhost:6390/0
cd waypoint_monitor && python -m app.main -c qa &          # serves http://localhost:8080
```

In another shell, run a small throwaway script (kept outside the repository) that calls `waypoint_etl.init(..., heartbeat_seconds=2)`, starts a step that sleeps, and
kill it with `kill -9`. After about 90 s (set `HEARTBEAT_DEAD_SECONDS=10` for a quick check) the run page shows
**Died**, the open step is Died with a last-seen time, and the home card is flagged. `redis-cli keys 'waypoint:*:died'`
shows one item.

## 3. Hung versus dead (User Story 2)

Run the same script but block the step without killing the process: the run shows Running, then Stalled after
`STALL_SECONDS`, never Died. Kill it: it turns Died within the death-detection time.

## 4. Permanent verdict (FR-007a, SC-006)

After step 2, restart the monitor and, separately, write a fresh `...:alive` item with a current `beat_at` for
that run: the run stays Died.

## 5. Legacy and safety (User Stories 3 and 4)

- Write a run without an alive item: status identical to today.
- Stop Redis while a pipeline runs: it finishes with the same result; only warnings appear.
- Give the monitor a read-only Redis account: Died still shows per view and a warning is logged.

## Results of the run on 2026-10-16 (measured against a throwaway Redis and the real library and monitor)

Setup: throwaway Redis on port 6390, monitor on port 8089 with `HEARTBEAT_DEAD_SECONDS=6` and `STALL_SECONDS=5` for speed,
a small pipeline using the real `waypoint_etl` 0.2.0 with `heartbeat_seconds=1`. Automated checks first (section 1):
library 77 tests, monitor 182 tests, front end 91 tests, `black`, `ruff` and `mypy` clean in both folders (before the
change: 61, 120 and 80 tests).

| Scenario | Observed |
|---|---|
| 2. Dead run (`kill -9` mid-step) | Running while beating; Stalled 3 s after the kill (beat still younger than 6 s); **Died 9 s after the kill**; one `...:died` key stored, expiring with the heartbeat item |
| 3. Hung versus dead | Beating, step stuck 33 s: Stalled the whole time, never Died; after `kill -9`: Stalled at +3 s, **Died at +9 s** |
| 4. Permanent verdict | After a monitor restart and after writing a fresh heartbeat for the dead run: still Died, `recorded: true`, still one died key |
| 5a. Legacy run (heartbeat off) | Stuck 10 s and 12 s after the kill: Stalled, `died: null`, no alive and no died key |
| 5b. Redis unreachable | Same result `[1, 2, 3]`, 0.00 s, only warnings |
| 5c. Read-only monitor account (ACL without write) | Died shown on all three views with `recorded: false`, no died key written, one warning logged; then the full-access monitor judged it and stored the key |

UI checked in a browser (home card, run page in graph and list view): the Died pill, card, step node and legend render in
the error colour with a solid border, distinct from Stalled. Fixed after looking: the card reason wording, and the
"finished ... ago" line, which is now hidden for a Died run.

Not measured: the 2-minute figure of SC-001 at the default 90 s (checked with 6 s; the logic is the same threshold), and
a real Redis outage while a step runs (only "Redis unreachable from the start" was run).
