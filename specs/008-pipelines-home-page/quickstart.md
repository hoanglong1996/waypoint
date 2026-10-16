# Quickstart: validating the Pipelines Home Page

Run from `waypoint_monitor/`.

## Automated checks

```bash
python -m unittest discover tests            # includes test_overview.py and the /api/overview cases
node --test static/tests                     # includes router.test.mjs and overview.test.mjs
ruff check . && black --check . && mypy .    # new Python must pass (constitution III)
```

## Manual walk-through (about 5 minutes)

1. Seed demo data in both environments: `python -m tests.seed_demo qa` and `python -m tests.seed_demo prod`
   (this feature extends the seed to add demo `facebook` and `google_ads` pipelines next to `demo`; CallRail appears once it has run).
2. Start the monitor: `python -m app.main -c qa` and open `http://localhost:8080/`.
3. **Home** (US1): one card per pipeline with status, environment label, age and three counts. Pipelines with
   problems come first. Select a card: the Latest page of that pipeline opens, address is `#/p/<name>`.
4. Reload the page and open the address in a new tab: the same pipeline page shows. Use the back link: Home.
5. **History filter** (US2): open History. Choose `qa`, then `prod`: the run list, the trend chart and a run's
   details change to that environment only. Reload: the choice is kept. Edit `?env=` by hand to an environment with
   no runs: it stays selected with a "no runs" hint and the page says "No runs in this environment".
6. **New pipeline** (US3): run `python -m tests.seed_demo qa` with a new pipeline name; within one refresh
   (5 s) its card appears. Let a pipeline's last run age past `STALE_HOURS` (set `STALE_HOURS=0.001`): its card
   shows stale.
7. **States**: stop Redis: Home shows the error with retry. Start with an empty Redis: friendly empty state.
8. **Phone width** (resize to 375 px) and keyboard only (Tab, Enter): cards and filter are usable.

Expected results map to spec FR-001 to FR-015 and SC-001 to SC-006; interface details are in
[contracts/api.md](contracts/api.md) and [contracts/routes.md](contracts/routes.md).
