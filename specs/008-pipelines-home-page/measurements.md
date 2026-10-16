# Measurements (T028)

Measured 2026-10-16 in a browser against a fake in-memory store (`FakeStore`, 4 pipelines, 2 environments, 2 to 3
runs per pipeline: far below 30 runs and no network delay, so these show the page's own cost only).

| Criterion | How measured | Result |
|---|---|---|
| SC-001 two selections or fewer | Counted: open the monitor, select one card | 1 selection (a card opens `#/p/<name>`) |
| SC-003 filter result in under 1 s | `performance.now()` from the radio click to the new note and list, 4 switches prod/qa | 12 to 21 ms |
| SC-004 every run shown belongs to the chosen environment | Opened each listed run's drawer after switching | Every drawer showed the chosen environment's tag; API test `test_newest_run_across_environments_labels_its_environment` and the `/api/runs?env=` call make the limit server-side |
| SC-002 (20 pipelines in under 10 s) | Not measured with 20 live pipelines; the grid, grouping and order are covered by tests | open |
