# Implementation Plan: History-First Pipelines with Run Detail Pages

**Branch**: `010-history-first-run-detail` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-history-first-run-detail/spec.md`

## Summary

Change Waypoint Monitor (`waypoint_monitor/`) so a pipeline opens on its History page, the Latest page becomes a
generic **run detail page** reachable for any run, and the right-hand run drawer is removed.

Read from the code on 2026-10-16: the front end is hash-routed (`static/js/router.js`) with pages `home`,
`latest`, `history`, `notfound`. `views/latest.js` already renders a hero, flow strip and steps for `runs[0]`
(`renderLatest`); `views/history.js` opens a drawer (`openDrawer` / `fillDrawer`) that re-implements a smaller
version of the same content. The API already returns every run's full step data from `/api/runs`, so the plan is a
**front-end only change**: no server, record or library change.

Approach: add a route `#/p/<pipeline>/runs/<env>/<runId>`; make `renderLatest` take the chosen run instead of
`runs[0]`; make history rows links to that route; make `#/p/<pipeline>` mean history; delete the drawer, the Latest
tab and the Latest-only fetch (merged environments).

## Technical Context

**Language/Version**: ES modules in the browser, no build step; Python 3.12 server untouched

**Primary Dependencies**: none added

**Storage**: Redis, read only, unchanged. No new keys

**Testing**: `node --test` under `waypoint_monitor/static/tests` (router, state/model rules); `python -m unittest` under `waypoint_monitor/tests` stays green (no server change); manual browser pass from [quickstart.md](quickstart.md)

**Target Platform**: Modern desktop and phone browsers, served by the existing container

**Project Type**: Web application (small API plus static front end), inside the existing `waypoint_monitor/`

**Performance Goals**: A run detail page loads with one request (the pipeline's runs for one environment); opening a run from history needs no extra request when the run is already loaded

**Constraints**: Read only; works from a bookmarked address without server routing rules; reuses the existing 5 s refresh; no caller data (unchanged fields)

**Scale/Scope**: About 3 to 20 pipelines, 2 environments, up to 100 runs fetched for a detail page (the API maximum)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status |
|---|---|
| I. Layered architecture (`src/` layers) | Not affected: work is in `waypoint_monitor/static`, no Python layers change. |
| II. Caller PII protection | Pass. Same fields as today; no new data is fetched or displayed. |
| III. Type safety and quality | No Python changes; ruff, black and mypy stay unaffected. |
| IV. Test coverage | Pass by plan: router and view-selection rules get `node --test` tests, including a regression test for the old `#/p/<id>` address. |
| V. Resilient, observable execution | Pass. Store errors and not-found states reuse the existing error and not-found views. Read only. |

Gate result: pass, no violations. Re-checked after Phase 1: still pass.

## Project Structure

### Documentation (this feature)

```text
specs/010-history-first-run-detail/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── routes.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
integrations/callraill/waypoint_monitor/
├── static/
│   ├── index.html            # remove drawer markup, Latest tab; add run view section
│   ├── styles.css            # remove drawer styles; run rows become links
│   ├── js/
│   │   ├── router.js         # new 'run' route; '#/p/<id>' now history; titles
│   │   ├── app.js            # run view, fetch for run, back link, no drawer
│   │   ├── ui.js             # run-not-found HTML
│   │   └── views/
│   │       ├── latest.js     # becomes run detail: renderRun(el, run, runs, cfg)
│   │       └── history.js    # rows are links; drawer code removed
│   └── tests/
│       └── router.test.mjs   # updated and extended
└── README.md                 # page addresses
```

**Structure Decision**: Keep the existing `waypoint_monitor/static` layout. `views/latest.js` is renamed to
`views/run.js` in tasks (history imports `stepsHTML` from it); the exported helpers stay.

## Complexity Tracking

No constitution violations to justify.
