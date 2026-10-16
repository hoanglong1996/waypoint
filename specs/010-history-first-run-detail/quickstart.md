# Quickstart: validating History-First Pipelines with Run Detail Pages

Run from `integrations/callraill/waypoint_monitor`.

## Automated

```bash
node --test static/tests/*.test.mjs      # router, model and view-selection rules
python -m unittest discover tests        # server unchanged; must stay green
```

Expected: router tests cover `#/p/x` → history, `#/p/x/history?env=qa`, `#/p/x/runs/prod/20261015T020000Z` → run,
malformed run id → notfound, and `buildRoute` round-trips.

## Manual (browser)

1. Seed demo data and start the monitor (see `README.md`, `tests/seed_demo.py`), open `http://localhost:<port>/`.
2. Select a pipeline card → history opens (SC-002). No "Latest" tab exists.
3. Select the first row → a full page opens, no right-hand panel, hero + steps shown (SC-001, SC-003, SC-006).
4. Reload the page and open the address in a new tab → same run (SC-004).
5. Use "back" → history with the same environment filter (SC-005); browser Back/Forward follow visit order.
6. Open an older run → its own date, environment and counts; deltas compare with the run before it.
7. Edit the run id in the address → "Run not found" with a link to the history.
8. Open `#/p/<pipeline>` directly → history.
9. Open an in-progress run (seed one) → page keeps updating; List | Graph choice works.
10. Narrow the window to phone width → no side panel, no horizontal scroll.

## Baseline (2026-10-16, before changes)

`node --test static/tests/*.test.mjs`: 91 pass. `python -m unittest discover tests`: 182 pass.

## Results (2026-10-16, after changes)

- `node --test static/tests/*.test.mjs`: see the run recorded with the implementation (new `router` and `run-view` tests included).
- `python -m unittest discover tests`: 182 pass (server unchanged).
- Browser pass against a throwaway Redis seeded with several runs in prod and qa (Playwright, desktop 1440 and phone 390):
  steps 2 to 10 checked: card opens history on the environment of the run it shows; run rows open a full page with no
  drawer or tabs; reload and direct address keep the run; breadcrumb back link returns to the same environment's
  history; browser Back/Forward follow visit order; a wrong run id, a malformed id and an unknown environment show
  "Run not found" with a link to the history; an unknown pipeline shows "Pipeline not found"; `#/p/<pipeline>` opens
  history; an in-progress run shows "A run is in progress" and the List | Graph switch works; no horizontal scroll at
  390 px; no console warnings or errors. Heading receives focus on open.
- Not done: a full keyboard-only pass (T031) and a check of the phone layout in dark theme.
