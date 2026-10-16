You are implementing the front-end UI of "Pipeline Monitor" in this repository.

## Context
Pipeline Monitor is a small, read-only internal dashboard. A nightly pipeline merges CallRail call data with Google Ads click data. After each run, every step stores a record with: step name, named input counts, output count (number or null), and finish time. Operators use the dashboard to answer: "Did last night's run work, and where did data drop off?" It shows counts only, never personal data.

The UI design is already finished. It is a working static prototype in `docs/pipeline-monitor-degisn/`. Your job is to turn it into the real front-end, following my task list.

## Read these first, before writing any code
1. `specs/002-pipeline-monitor-dashboard/tasks.md`, `plan.md`, `spec.md`, `research.md`, `data-model.md` and `contracts/api.md`. Do the front-end tasks: T020, T021, T022, T023, T024, T025, T026 (Latest view), T027, T029, T030, T031 (History), T033, T035, T036 (polling and states), and the front-end parts of T016, T037 and T039. The backend tasks are done separately. The app lives in `performance_monitoring_app/`; the front end goes in `performance_monitoring_app/static/`.
2. `docs/pipeline-monitor-degisn/DESIGN_NOTES.md`: layout decisions, breakpoints, the state table and the token list.
3. `docs/pipeline-monitor-degisn/index.html`, `styles.css`, `app.js`: the reference implementation.
4. `docs/pipeline-monitor-degisn/screenshots/*.png`: the target look. Open and look at them.
   01 Latest light, 02 Latest dark, 03 History + drawer, 04 trend hover, 05/06/14 mobile 375px, 07–13 the states.
5. `specs/002-pipeline-monitor-dashboard/contracts/api.md`: the real data contract (`/api/config`, `/api/runs`, `/api/health`). If the backend in `performance_monitoring_app/app/` already exists, check it matches.

After reading, give me a short plan: which files you will create or change and how each task maps to them. Then wait for my OK.

## Hard technical constraints
- Plain HTML, CSS and vanilla JavaScript (ES modules are fine). No framework, no build step, no CDN, no external JS libraries.
- Charts and sparklines are hand-drawn inline SVG, themed with CSS variables.
- Icons are inline SVG only.
- Fonts: the system font stack, plus at most the one Google Fonts family (Geist) used in the prototype (it must fall back cleanly to the system font when it cannot load).

## How to use the prototype
Reuse as-is:
- All design tokens in `styles.css` (light + dark, spacing, radius, shadows, type scale). Keep the two dark-theme blocks identical: the `prefers-color-scheme` one and the `[data-theme="dark"]` one.
- The component CSS: header, tabs, segmented control, pills, chips, banners, hero, flow strip, step timeline, sparkline, trend chart, runs list, drawer, skeletons, empty and error cards, and the responsive rules.
- The markup structure and ARIA: tablist with arrow keys, radio-based environment switch, drawer as role="dialog" with focus trap and Esc to close, role="alert" for errors and stale, role="status" for notices.
- The logic in `analyse()`, `isLoss()`, `headline()`, `metric()`, `deltaChip()`, `sparkline()`, `drawTrend()`.

Change:
- Remove the prototype-only parts: the "Preview state" switcher, the URL params (state/run/hover), the fixed NOW date, the mock data (`buildRuns`, `makeRun`, `BASE`, `rng`) and the hard-coded `STEPS` array (step order, groups, input names and "from" steps come from `/api/config` `expected_steps`).
- Load real data from `/api/runs?env=<env>&limit=30` (newest first). Map the snake_case JSON to the shape the views expect:
  run = { id: run_id, env, startedAt: Date, endedAt: Date, status, firstMissingStep, missingCount, lossSteps, ageSeconds, stale, durationSeconds, unreadable, steps: [ {name, inputs:[{name,value}], output: number|null, finishedAt: Date} | {name, missing:true} ] }
  The API already returns all 9 steps in order, with `{name, missing:true}` for steps that did not report.
- Split the code into modules under `static/js/`: `api.js` (fetch + mapping), `model.js` (pure rules: metric, headline, delta, series, formatting), `chart.js` (sparkline, trend chart), `views/latest.js`, `views/history.js`, `app.js` (shell: tabs, theme, env, live indicator, polling, banners). Put `node --test` tests in `static/tests/`.
- Use `textContent` or escaping for any value coming from the API. Do not inject raw API strings with innerHTML.

## Business rules (must match the design)
- The server is the source of truth for these flags: `status` (complete/incomplete), `first_missing_step`, `loss_steps` (output === 0 and at least one input > 0), `age_seconds` and `stale` (the newest run finished more than `stale_hours` ago, from `/api/config`). Read them; do not recompute them in the browser. Reduce the prototype's `analyse()` accordingly.
- Headline numbers: Accounts = output of read_callrail_account, Calls = output of read_callrail_call, Saved stats = the call_statistics input of save_call_statistics. Show "—" when the step is missing.
- Delta chips compare with the immediately previous run in the list: green up, red down, neutral for no change, with a percentage; previous 0 → "new"; no chip when either value is missing.
- A step with output null shows "n/a" plus "returns nothing", and its sparkline uses its first input.
- Sparklines show the last 14 runs. History shows up to 30 days, newest first.
- States map to real conditions:
  - Loading: the first fetch is in progress.
  - Empty: no runs for this env.
  - Data store unreachable: the fetch failed. Hide all numbers and show the retry button and the auto-retry hint.
  - Stale banner.
  - "Some records could not be read": the API reports unreadable or malformed records.
  - Incomplete run and data-loss step: as defined above.
- "Updated Xs ago" counts from the last successful fetch. Poll every `refresh_seconds` from `/api/config` (default 60); on a failed fetch show the error card and retry every `retry_seconds` (default 30), plus a "Retry now" button.
- Remember the theme choice in localStorage, wrapped in try/catch. With nothing saved, follow the OS setting.

## Quality bar
- The result must look like the screenshots at 1440px and 375px, in light and dark.
- No horizontal page scroll at 375px.
- Status is never shown by colour alone: always icon + text.
- Visible focus states. `prefers-reduced-motion` turns off the pulse, shimmer and slide animations.
- Add unit tests for the pure rules in `model.js` (metric, headline numbers, delta %, series with gaps, formatting). Use `node --test` (no build).
- Don't change backend behaviour unless a task asks for it.

## Working style
- Do one task at a time, in task order. After each task, tell me what changed and how to check it.
- If `contracts/api.md` is unclear or the backend doesn't match it, stop and ask me. Do not guess field names.
- When everything is done, run the tests, open the page with real or seeded data, and compare it against each screenshot. List any differences you couldn't fix.