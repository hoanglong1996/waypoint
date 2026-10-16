> **Historical.** This prompt produced the approved design in `docs/design/pipeline-monitor-graph-update`. That design and spec.md are now authoritative where they differ from this prompt.

# Claude Design prompt: Pipeline directed graph

Copy everything below the line into Claude Design. Attach `docs/pipeline-monitor-degisn/` (index.html, styles.css, app.js, screenshots/) and `docs/pipeline-graph.html` as references.

---

Design a **directed-graph view** of a data pipeline run for an existing monitoring dashboard. It must match the attached design system (tokens, typography, status icons, light and dark themes in `styles.css`). It is an additional view next to the existing step list in the "Latest run" tab and in the History run drawer.

## Purpose
An operator must see at a glance **which step feeds which**: an arrow from step A to step B means "A's output is B's input". They must also see where data dropped or the run stopped, and what is downstream of it.

## Graph (fixed structure, 9 nodes)
Groups: CallRail, Google Ads, Merge, Persist. Edges are `producer -> consumer (input name)`:
1. `read_callrail_account` -> `read_callrail_call` (accounts)
2. `read_partners` -> `read_instances` (partners)
3. `read_instances` -> `read_campaigns` (instances)
4. `read_instances` -> `read_gads_clickview` (instances)
5. `read_callrail_call` -> `merge_calls_clickview` (calls)
6. `read_campaigns` -> `merge_calls_clickview` (campaigns)
7. `read_gads_clickview` -> `merge_calls_clickview` (clickview)
8. `merge_calls_clickview` -> `record_call_statistics` (call_statistics)
9. `merge_calls_clickview` -> `save_call_statistics` (call_statistics)

Two independent branches (CallRail; Google Ads) start separately and join at `merge_calls_clickview`, which then fans out to two sinks. Sources: `read_callrail_account`, `read_partners`. Sinks: `record_*` and `save_*`, which "return nothing" (no output count, show "n/a", no outgoing arrow). The shape is identical for every run; only counts and states change.

## Content
- **Node**: step name (mono), friendly label, group colour/tag, output count (large tabular numeral) or "n/a · returns nothing", finish time, state pill.
- **Edge**: arrow with a label chip `inputName · count` (e.g. `accounts · 10`). Edge thickness or opacity may hint at magnitude (log scale). The count is the consumer's recorded input.
- **States** (never colour alone: icon + text + pattern):
  - *Fine*: check icon.
  - *Possible data loss*: input > 0 but output 0. Red, `!`, outgoing edge shows `0` and is styled as "empty".
  - *Not reported* (run stopped): dashed, hatched node; incoming edge dashed/inactive; downstream nodes look "not reached".
- Include a small legend (node states, edge states, group colours) and a one-line summary above the graph ("Data flows left to right").

## Interaction
- Click/keyboard-select a node: highlight its direct upstream and downstream nodes and connecting edges, dim the rest, open the step details (reuse the existing step card/drawer).
- Escape or empty-space click clears. Hover shows a tooltip with the full input/output text and the "from" step.
- A "List | Graph" segmented control (radio style like the environment switch), choice remembered.
- Optional subtle flow animation on edges, off under `prefers-reduced-motion`.

## Layout and responsive
- Left to right layered layout at desktop (1200 px column): sources on the left, sinks on the right, minimal edge crossings, curved edges with arrowheads, comfortable spacing so edge labels never overlap nodes.
- Tablet: keep the layout, scale nodes down.
- 375 px mobile: no horizontal page scroll. Propose either a top-to-bottom flow or a self-contained scroll panel with a visible hint; pick the more readable one and show it.
- Compact variant for the History drawer (680 px wide): smaller nodes, labels on hover/focus.

## Screens/states to deliver (light and dark)
1. Healthy complete run, desktop
2. Run with a data-loss step (`read_campaigns` output 0)
3. Incomplete run (stopped before `read_gads_clickview`): missing nodes and inactive edges
4. A node selected with neighbours highlighted
5. Mobile 375 px
6. Drawer compact variant
7. Loading skeleton and empty state for the graph panel

## Deliverable and constraints
Static HTML/CSS/vanilla JS prototype like `docs/pipeline-monitor-degisn` (mock data, `?state=` URL params, no build step, no JS libraries; inline SVG for edges). Reuse the existing CSS variable names; add new tokens only for edge states and group accents. Keep WCAG AA contrast, visible focus rings, 44 px touch targets, and write short DESIGN_NOTES.md sections explaining layout rules, edge routing, states and responsive choices so they can be implemented directly.
