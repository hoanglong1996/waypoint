# Implementation Plan: Pipelines Home Page

**Branch**: `008-pipelines-home-page` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-pipelines-home-page/spec.md`

## Summary

Add a home page to Waypoint Monitor (`waypoint_monitor/`) that lists every pipeline that has reported, one card
per pipeline showing its newest run across all environments (status, environment label, age, headline counts).
Selecting a card opens that pipeline's Latest page. Pages get their own addresses (hash routes), and the History
page gets an environment filter that restricts runs, run details and step trends to one environment.

Read from the code on 2026-10-16: the monitor already discovers pipelines from Redis, has per-environment
`/api/pipelines` and `/api/runs`, and the front end merges runs across environments with a header pipeline
dropdown and two tabs (Latest, History). The plan therefore adds **one read-only endpoint** (`/api/overview`)
for the cards, and changes the front end from "dropdown + tabs" to "routes". Records, keys and the library are
unchanged.

## Technical Context

**Language/Version**: Python 3.12 (server); ES modules in the browser, no build step

**Primary Dependencies**: FastAPI and the existing Redis store (server); none added in the browser

**Storage**: Redis, read only, existing key layout (`specs/007-rename-to-waypoint/contracts/redis-keys.md`). No new keys

**Testing**: `python -m unittest` under `waypoint_monitor/tests` (API and parsing, fake store); `node --test` under `waypoint_monitor/static/tests` (pure front-end rules)

**Target Platform**: Modern desktop and phone browsers, served by the existing container

**Project Type**: Web application (small API plus static front end), inside the existing `waypoint_monitor/`

**Performance Goals**: Home page data in one request; the home page shows 20 pipelines readable in under 10 s (SC-002); changing the environment filter shows its result in under 1 s for 30 runs (SC-003)

**Constraints**: Read only; counts and names only, no caller data; uses the existing 2 s server cache and 5 s refresh; works from a bookmarked address without server routing rules

**Scale/Scope**: About 3 to 20 pipelines, 2 environments, 30 runs per view

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status |
|---|---|
| I. Layered architecture (`src/` layers) | Not affected: the work is in `waypoint_monitor/`, which has its own `api/domain/infrastructure` split. New code follows it (summary logic in `domain/`, route in `api/`). |
| II. Caller PII protection | Pass. The overview returns only pipeline names, environment names, status flags, times and counts already exposed by `/api/runs`. No new free-form fields. |
| III. Type safety and quality (mypy strict, ruff, black) | Applies to new Python in `waypoint_monitor/app`; run before merge. |
| IV. Test coverage | Pass by plan: unit tests for the overview rules, the route, and the front-end routing and filter rules. No live services. |
| V. Resilient, observable execution | Pass. Store failures return the existing 503 and the home page shows the existing error state with retry. Read-only, so re-runs are safe. |

Gate result: pass, no violations to justify. Re-checked after Phase 1: still pass.

## Project Structure

### Documentation (this feature)

```text
specs/008-pipelines-home-page/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md          # new GET /api/overview
│   └── routes.md       # page addresses and filter parameter
├── checklists/requirements.md
└── tasks.md            # created later by /speckit-tasks
```

### Source Code (repository root)

```text
waypoint_monitor/
├── app/
│   ├── api/routes.py            # + GET /api/overview
│   └── domain/overview.py       # NEW: pick newest run across envs, rank by attention
├── static/
│   ├── index.html               # header: remove pipeline dropdown; add home/back links
│   ├── styles.css               # cards, filter
│   ├── js/
│   │   ├── router.js            # NEW: parse/build hash routes (pure)
│   │   ├── app.js               # route-driven shell replaces dropdown + tab state
│   │   ├── api.js               # + loadOverview; loadRuns takes one env or all
│   │   ├── model.js             # + env filter and attention-order rules (pure)
│   │   └── views/home.js        # NEW: pipeline cards, empty/error states
│   └── tests/
│       ├── router.test.mjs      # NEW
│       └── overview.test.mjs    # NEW
└── tests/
    └── test_overview.py         # NEW (also extend test_api.py)
```

**Structure Decision**: Extend the existing `waypoint_monitor/` app in place. One new domain module and one new
route on the server, one new view and one new router module in the browser. No new top-level project and no
change to `src/` or `packages/`.

## Complexity Tracking

No constitution violations. Two choices worth noting, both the simpler option: hash routes instead of server
routing (no server change for deep links), and one overview endpoint instead of the browser calling `/api/runs`
once per pipeline and environment.
