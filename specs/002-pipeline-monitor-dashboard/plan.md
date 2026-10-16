# Implementation Plan: Pipeline Monitor Dashboard

**Branch**: `002-pipeline-monitor-dashboard` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-pipeline-monitor-dashboard/spec.md`

## Summary

A small, read-only web app in a new `performance_monitoring_app/` folder. A FastAPI backend scans the
step records written by feature 001 (`callrail:audit:{env}:{run_id}:{NN}-{step}`), groups them into runs, derives
status (complete / incomplete, plus stale and data-loss flags), and serves a JSON API. A single-page front end
(plain HTML, CSS and ES-module JavaScript, no build step, hand-drawn SVG charts) renders the latest run,
run history, trends, auto-refresh, and light/dark themes. It is built from the approved design
prototype in `docs/design/pipeline-monitor-degisn` (tokens, CSS, markup and rendering logic reused; mock data
and the preview switcher removed). It ships as its own container.

## Technical Context

**Language/Version**: Python 3.12 (backend); vanilla ES2020 JavaScript, HTML5, CSS3 (front end)

**Primary Dependencies**: `fastapi`, `uvicorn`, `redis` (read-only client); front end has no JS dependencies (one optional Google Fonts family, Geist, with system-font fallback)

**Storage**: Redis (existing; read only: `SCAN`, `MGET`/`GET`, never writes or deletes)

**Testing**: `unittest` + FastAPI `TestClient` (httpx) with an in-memory fake store; front end: `node --test` (Node ≥ 18, tests only) on the pure functions in `static/js/model.js`, plus visual comparison with the design screenshots via the quickstart

**Target Platform**: Linux container on the internal network; modern desktop and mobile browsers

**Project Type**: Web application (backend + static front end in one deployable)

**Performance Goals**: Latest-run view in < 3 s with 30 days of runs (≈ 270 keys per environment); `/api/runs` returns ≤ 30 runs × 9 steps

**Constraints**: Read-only; counts only (no PII); works with Redis down (clear message); no login in v1

**Scale/Scope**: A handful of operators, 2 environments, ~9 steps per run, ≤ ~30–100 runs retained

## Constitution Check

The constitution governs the CallRail ETL project; this app lives beside it as a separate project, so
the principles apply by analogy.

| Principle | Status | Notes |
|---|---|---|
| I. Layered Architecture | Pass | Own layers: `domain/` (models, status rules), `infrastructure/` (Redis reader), `api/` (routes); domain imports nothing from infrastructure |
| II. Caller PII Protection | Pass | Only reads counts and step names; unknown fields in records are dropped, never forwarded; no Sentry/logs of record bodies |
| III. Type Safety and Code Quality | Pass | Fully typed Python; `mypy` strict, `ruff`, `black` (line length 100) |
| IV. Test Coverage | Pass | Python unit tests for parsing, run analysis and API with fake store (no live Redis); `node --test` for front-end pure rules |
| V. Resilient, Observable Execution | Pass | Redis errors map to a 503 with a message the UI shows; short Redis timeouts; read-only so re-runs are safe |

Re-check after design: still passes. No complexity violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-pipeline-monitor-dashboard/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root: `integrations/callraill/`)

```text
performance_monitoring_app/
├── app/
│   ├── main.py                    # FastAPI app factory, static mount, run entry
│   ├── config.py                  # REDIS_URL, ENVIRONMENTS, STALE_HOURS, REFRESH_SECONDS, RETRY_SECONDS
│   ├── domain/
│   │   ├── models.py              # StepRecord, Run, StepDefinition
│   │   ├── steps.py               # EXPECTED_STEPS: order, group, inputs (+from), returns_nothing
│   │   ├── parsing.py             # key + JSON parsing and validation
│   │   └── analysis.py            # build_runs: 9-step runs, status, loss, ended_at, stale
│   ├── infrastructure/
│   │   ├── store.py               # RecordStore protocol
│   │   └── redis_store.py         # RedisRecordStore (SCAN + MGET, read only)
│   └── api/
│       └── routes.py              # /api/health, /api/config, /api/runs
├── static/                        # built from docs/design/pipeline-monitor-degisn
│   ├── index.html                 # shell from the design (preview switcher removed)
│   ├── styles.css                 # design tokens + components, copied as-is
│   ├── js/
│   │   ├── app.js                 # shell: tabs, env, theme, live indicator, polling, banners
│   │   ├── api.js                 # fetch + map API JSON to view shape (dates, camelCase)
│   │   ├── model.js               # pure rules: metric, headline, delta, series, formatting
│   │   ├── chart.js               # sparkline() and drawTrend()
│   │   ├── ui.js                  # icons, pills, delta chip, banners, empty/error/skeleton HTML
│   │   └── views/
│   │       ├── latest.js          # hero, flow strip, steps timeline
│   │       └── history.js         # trend card, runs list, drawer
│   └── tests/
│       └── model.test.mjs         # node --test
├── tests/
│   ├── fakes.py
│   ├── test_parsing.py
│   ├── test_redis_store.py
│   ├── test_analysis.py
│   └── test_api.py
├── requirements.txt
├── pyproject.toml                 # black/ruff/mypy settings
├── Dockerfile
└── README.md
```

**Structure Decision**: Self-contained project in `performance_monitoring_app/` with its own
requirements, Dockerfile and tests, sharing nothing with the pipeline at runtime other than the
documented record format (`specs/001-pipeline-step-audit/contracts/step-record.md`). The design
source of truth is `docs/design/pipeline-monitor-degisn/` (`DESIGN_NOTES.md`, `index.html`, `styles.css`,
`app.js`, `screenshots/`); it is copied into `static/` and adapted, not referenced at runtime.

## Complexity Tracking

No violations.
