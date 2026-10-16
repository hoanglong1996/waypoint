# Quickstart: Validating the Pipeline Monitor Dashboard

## Prerequisites
- Redis holding step records from feature 001 (run `python main.py -c qa` with `REDIS_URL` set, or seed a few records by hand using `contracts/step-record.md` in feature 001)
- `cd performance_monitoring_app && pip install -r requirements.txt`

## 1. Unit tests
`python -m unittest discover tests` from `performance_monitoring_app/`; expect all to pass with no Redis. Then `node --test static/tests` for the front-end rules.

## 2. Run the app
`REDIS_URL=redis://localhost:6379/0 python -m app.main`, then open <http://localhost:8080>.

## 3. Walk through the stories
1. **Latest run**: compare against `docs/design/pipeline-monitor-degisn/screenshots/01` and `02`: hero with status pill and title sentence, three KPIs with change chips, flow strip, steps timeline with chips, magnitude bars and sparklines; counts match `redis-cli get <key>`; start time, "finished … ago" and duration shown.
2. Delete (in a test Redis only) the keys for steps 8 and 9 of the latest run: the run shows **incomplete** with `record_call_statistics` as first missing step.
3. Seed a step with input 5 and output 0: it is flagged as possible data loss.
4. **History** (screenshots 03, 04): several runs listed newest first; open one in the drawer (Esc closes it, focus returns); pick a step to view its trend, hover or use arrow keys for the tooltip and change vs previous run.
5. Switch environment prod ↔ qa.
6. **Auto-refresh**: set `REFRESH_SECONDS=5`, store a new run; it appears without reloading and "Updated Ns ago" resets.
7. **Stale**: set `STALE_HOURS=0`; the stale banner shows.
8. **Problems** (screenshots 07–13): stop Redis: the error card replaces all numbers, "Retry now" works and it retries every 30 s. Environment with no runs: empty state. Corrupt one record of a run: "unreadable" banner and marker in History.
9. Resize to 375 px (screenshots 05, 06, 14) and toggle light/dark: no horizontal scroll, layout matches the design. Check keyboard: tabs with arrows, drawer focus trap, focus rings; enable reduced motion and confirm animations stop.

## 4. Quality gate
`black .`, `ruff check .`, `mypy .` inside `performance_monitoring_app/`.

## 5. Container
`docker build -t pipeline-monitor performance_monitoring_app && docker run -p 8080:8080 -e REDIS_URL=... pipeline-monitor`
