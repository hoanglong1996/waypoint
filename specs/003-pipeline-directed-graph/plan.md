# Implementation Plan: Pipeline Directed Graph View

**Branch**: `003-pipeline-directed-graph` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-pipeline-directed-graph/spec.md`

## Summary

Add a "Graph" view beside the existing "List" view of a run in `performance_monitoring_app/`. It is a
front-end-only change: `/api/config` already returns every step's group and inputs with a `from` producer
(`expected_steps[].inputs[].from`), and `/api/runs` already returns per-step counts. The approved design is
`docs/design/pipeline-monitor-graph-update` (`DESIGN_NOTES.md` §8, reference `graph.js`, screenshots in
`screenshots/graph/`). Its layout is a fixed, hand-tuned column/row table (no auto-layout) in three
responsive forms (desktop LR, compact LR, phone top-to-bottom), drawn as absolutely-positioned HTML node buttons
over one inline SVG layer for edges, with no library. The build ports the design's IIFE (`window.PM`,
`PMGraph`) to ES modules, splitting pure rules (`graph-model.js`) from rendering (`views/graph.js`).

## Technical Context

**Language/Version**: vanilla ES2020 JavaScript (ES modules), HTML5, CSS3 (front end). Python 3.12 backend is unchanged.

**Primary Dependencies**: none new (no graph/layout library)

**Storage**: N/A (view preference in `localStorage['pm-steps-view']`, try/catch, same as the theme)

**Testing**: `node --test` on pure functions in `static/js/graph-model.js` (node states incl. stopped/unreached, affected set, edge state and count, edge width, layout picker, unknown-step fallback); one Python API contract test; visual comparison with `screenshots/graph/` via the quickstart

**Target Platform**: modern desktop and mobile browsers (375 px to wide)

**Project Type**: web application (existing; static front end only)

**Performance Goals**: graph visible in < 3 s together with the rest of the latest-run view; relayout on resize debounced (120 ms)

**Constraints**: read-only; counts only (no PII); no new endpoint; reuse existing tokens; add only `--grp-callrail/gads/merge/persist` (+ `-bg`) and `--edge`, `--edge-hl`, `--edge-empty`, `--edge-inactive`, `--edge-flow` in the light block AND both dark blocks; API values inserted via escaping/`textContent`; no horizontal page scroll at 375 px

**Scale/Scope**: 9 nodes, 9 edges, 2 environments

## Design Alignment Decisions

| Topic | Decision |
|---|---|
| Layout | Fixed position table keyed by step name (design §8.3): sizes desktop w154 h128 gap88, compact w100 h72 gap28; no auto-layout |
| Breakpoints | By the panel's inner width: ≥880 desktop LR (scaled `min(1, w/1138)`); 600–879 compact LR (scaled `min(1.35, w/628)`, also the 680 px drawer); <600 top-to-bottom, 2 lanes. Rebuild on resize, keep selection |
| Node states | `stopped` (first missing), `unreached` (later missing), `loss`, `ok`; plus `affected` badge on `ok` steps downstream of a loss |
| Edge states | `ok`, `empty`, `inactive` (+ `ghost` while loading/empty); width `1.25 + 2.75·log10(count+1)/log10(max+1)` px |
| Edge source | `/api/config` `from` + `group`; friendly labels and positions are a front-end table (spec FR-012) |
| Unknown step | rendered in an "Other steps" row below the graph, unconnected |
| View default | Graph (deliberate deviation from the prototype, which defaults to List); key `pm-steps-view`; `?view=` not carried over |
| Selection | click toggles; Esc clears and refocuses the node (capture phase, so in the drawer first Esc clears, second closes); flow animation off while selecting |
| Step card | extract `stepItemHTML` from `stepsHTML` in `views/latest.js`; the Selected-step panel reuses it |
| Not carried over | preview switcher, mock data, fixed NOW, `?state=` and `?select=` |

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Layered Architecture | Pass | Pure rules in `graph-model.js`; rendering in `views/graph.js`. No backend change |
| II. Caller PII Protection | Pass | Only step names and counts are shown; values escaped |
| III. Type Safety and Code Quality | Pass | No Python changes beyond one test; JS pure functions unit-tested |
| IV. Test Coverage | Pass | `node --test` for graph model; one API contract test |
| V. Resilient, Observable Execution | Pass | Graph uses loading, empty and unavailable states; unknown steps degrade gracefully |

Re-check after alignment: still passes. No complexity violations.

## Project Structure

### Documentation (this feature)

```text
specs/003-pipeline-directed-graph/
├── plan.md
├── research.md
├── data-model.md
├── design-prompt.md       # historical: the prompt given to Claude Design
├── quickstart.md
├── contracts/ui.md
└── tasks.md
```

### Design source (approved)

```text
docs/design/pipeline-monitor-graph-update/
├── DESIGN_NOTES.md (§8 Graph view), CHANGES.md, graph.js (reference), app.js, styles.css (§10), index.html
└── screenshots/graph/ (g00–g09)
```

### Source Code (changes only)

```text
performance_monitoring_app/
├── static/
│   ├── index.html            # load nothing extra (ES modules); toggle markup rendered by JS
│   ├── styles.css            # new tokens (3 blocks) + graph section from design §10
│   └── js/
│       ├── graph-model.js    # NEW pure: node/edge states, affected, widths, layout table, layout picker, neighbours
│       ├── views/graph.js    # NEW mountGraph(el, {run, runs, mode, details, prefer}): render, wire, resize
│       ├── views/latest.js   # extract stepItemHTML; List|Graph head; mount graph
│       ├── views/history.js  # drawer: toggle + compact graph; Esc order
│       └── ui.js             # new icons (flow, list, graph, octagon/gap/down/arrowIn if missing); view pref helpers
├── tests/test_api.py         # contract test for `from` links
└── static/tests/graph-model.test.mjs   # NEW node --test
```

**Structure Decision**: extend the existing front end only; the list stays and the graph is a sibling view over the same run object.
