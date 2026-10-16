# Research: History-First Pipelines with Run Detail Pages

Read from source on 2026-10-16 (`waypoint_monitor/static/js`, `waypoint_monitor/app/api/routes.py`).

## 1. Address of a run

**Decision**: `#/p/<pipeline>/runs/<env>/<runId>`.

**Rationale**: A run key in Redis is `pipeline:env:runId`; the same `runId` (a UTC timestamp, `YYYYMMDDTHHMMSSZ`) can
exist in two environments, so the environment must be part of the address. It also tells the page which single
environment to fetch, and gives the back link its filter for free.

**Alternatives**: `#/p/<pipeline>/runs/<runId>?env=` (env optional, so ambiguous); a numeric position in the list
(changes as new runs arrive, breaks sharing).

## 2. Where the run data comes from

**Decision**: No API change. The run page fetches `/api/runs?env=<env>&pipeline=<p>&limit=100` and picks the run by id.

**Rationale**: `/api/runs` already returns full step data per run (what the drawer and Latest page render). 100 is the
API maximum and exceeds the 30 the history list shows, so every listed run opens. Runs older than the newest 100 show
"run not found"; records expire after 30 days anyway (`ttl_days=30`).

**Alternatives**: a new `/api/run` endpoint (server change, tests, contract) for a case the spec calls an edge case;
reusing the history's 30-run set (a shared link to run 31+ would break).

## 3. Meaning of `#/p/<pipeline>`

**Decision**: It resolves to the history page (FR-012). `buildRoute` for history omits `/history` only if the
route is built without a page; `parseRoute` accepts both forms and the app canonicalises nothing (no redirect).

**Rationale**: Old bookmarks and the home cards keep working; the spec asks for no redirect notice.

## 4. Latest page → run detail

**Decision**: Generalise `renderLatest(el, runs, cfg)` to `renderRun(el, run, runs, cfg)`. The hero's "previous run"
deltas and sparklines already use `runs` and the run's position in it, so they work for any run. The hero title text
"Last night's run completed" and "Latest run completed — but it's old" is latest-specific and is reworded for a
non-latest run (use the run's date; keep the stale wording only when the run is the newest).

**Rationale**: One renderer, one set of tests, same content as FR-004 requires.

**Alternatives**: keep the drawer markup and render it full page (two implementations of the same content, which is
what we have today).

## 5. Removing the drawer

**Decision**: Delete drawer markup, styles, `openDrawer`/`closeDrawer`/`syncDrawer`/`wireDrawer`/`refreshDrawer` and
their calls in `app.js`; history rows become `<a class="run-row" href="#/p/…/runs/…">`. Anchors give back/forward,
open-in-new-tab and keyboard activation without code.

## 6. Back control and environment

**Decision**: The run page shows a back link to `#/p/<pipeline>/history?env=<run env>`; the context bar replaces the
Latest | History tabs with a breadcrumb: All pipelines › Pipeline › Run time. Browser Back is also correct because
each navigation is a hash change.

## 7. Auto refresh

**Decision**: Reuse `refresh()` in `app.js`: for a run route it loads that run's environment and re-renders on
signature change, so an in-progress run keeps updating (FR-008). A run that disappears yields the run-not-found view.

## 8. Scroll and focus

**Decision**: Keep `window.scrollTo(0, 0)` on route change; on opening a run, focus the page heading; on returning
to history, no focus restoration beyond the browser default (the drawer's focus trap is deleted with it).
