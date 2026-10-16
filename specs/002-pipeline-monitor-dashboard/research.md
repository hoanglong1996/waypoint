# Research: Pipeline Monitor Dashboard

## Decision 1: FastAPI backend serving a JSON API plus static files
- **Rationale**: Small, typed, async-friendly, built-in OpenAPI docs and `TestClient`; one process serves API and UI.
- **Alternatives**: Flask + Jinja (server-rendered pages make auto-refresh and charts clunkier); Streamlit/Grafana (fast, but "beautiful, custom UI" and a plain deployable are requested; Grafana would also need a Redis data source plugin).

## Decision 2: Front end is plain HTML/CSS/JS (ES modules) with no build step and no JS dependencies
- **Rationale**: "Simple" app; nothing to compile; easy to ship in the same container. The approved design (`docs/design/pipeline-monitor-degisn`) is already plain HTML/CSS/vanilla JS with tokens for light/dark. The only external request is one optional Google Fonts family (Geist); when it cannot load (internal network) the system font stack is used with no functional change.
- **Alternatives**: React/Vite (build toolchain overkill); Chart.js from a CDN (external dependency, offline breakage); self-hosting the font (possible later, not needed for v1).

## Decision 3: Charts are small hand-built SVG (sparklines and one trend area chart)
- **Rationale**: Data is tiny (≤ 30 points per step); SVG is crisp, themeable via CSS variables and dependency-free; the design already specifies them (128×36 sparkline over 14 runs, 240 px trend chart over 30 runs with hover/keyboard tooltip).
- **Alternatives**: Chart.js, uPlot (add a dependency for little gain).

## Decision 4: Read records with `SCAN MATCH callrail:audit:{env}:*` then `MGET`
- **Rationale**: Keys are few (~270 per env), SCAN never blocks Redis like `KEYS`. Run id and step come from the key; the JSON value supplies counts. Results cached in memory for 10 s so concurrent browsers and auto-refresh don't hammer Redis.
- **Alternatives**: `KEYS` (blocking); an index key written by the pipeline (requires changing feature 001 and was rejected in its clarification).

## Decision 5: Run status derivation
- **complete**: all 9 expected steps present. **incomplete**: any missing; first missing step (by order) reported. **stale** is a separate flag: `generated_at − ended_at > STALE_HOURS` (default 26), where `ended_at` is the latest step finish time (as in the design: "finished 32h ago"). A run may be incomplete and stale at once.
- **Data-loss flag**: a step with any input count > 0 and output exactly 0.
- Steps with `output: null` display "n/a" and are never flagged.
- Run start time is parsed from `run_id` (`YYYYMMDDTHHMMSSZ`); end time and duration come from step `finished_at` values.
- The UI shows, for the hero pills, "Possible data loss" and "Stale" next to Complete/Incomplete; they are independent flags.

## Decision 6: Configuration through environment variables
`REDIS_URL` (required), `ENVIRONMENTS` (default `prod,qa`), `STALE_HOURS` (26), `REFRESH_SECONDS` (60), `RETRY_SECONDS` (30), `PORT` (8080). The UI reads the intervals and the pipeline definition from `/api/config` so nothing is hard-coded in the front end.

## Decision 7: No authentication in v1
- Per spec assumptions: internal network, counts only. Documented in the README; an optional reverse-proxy or basic-auth layer is the extension point.

## Decision 8: Malformed records are skipped and counted per run
- Invalid JSON, missing fields or wrong types → skip, increment that run's `unreadable` (and `unreadable_total`), so the UI shows the banner and the per-run marker (FR-013). The step then counts as not reported. Extra unknown fields are ignored.

## Decision 9: One endpoint returns the recent runs with full step detail
- **Rationale**: The design computes sparklines (14 runs), deltas, history rows, the drawer and the 30-run trend chart from the same list, so one cheap call (≤ 30 runs × 9 steps) is simpler than per-run and per-step endpoints, and keeps the latest view and history consistent.
- **Alternatives**: `/runs/latest`, `/runs/{id}`, `/trends` (many round trips and duplicated derived data).

## Decision 10: Where rules live
- Server (authoritative, tested in Python): parsing, validation, grouping, completeness, missing/loss/stale flags, end time and duration.
- Front end (presentation, tested with `node --test`): `metric`, `headline`, change %, series building, formatting. The prototype's `analyse()` is reduced to reading the API's flags instead of recomputing them.
