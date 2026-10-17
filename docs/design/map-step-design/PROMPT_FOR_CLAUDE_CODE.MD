I'm adding a new feature to Waypoint Monitor: the "Map step" (a loop inside a pipeline).
The design is in ./map-step-design/. Read map-step-design/HANDOFF.md first, then
map-step-design/mockups/MapSpec.dc.html, then the other mockups as you need them.

The mockups are design references only: copy their markup structure, class names, spacing
and tokens into our real code, but do NOT copy the x-dc / sc-for / sc-if runtime or the
<script type="text/x-dc"> blocks.

Scope: build only the new parts. Do not redesign the rest of the dashboard.
1. Map step node in the Steps → Graph view (js/views/graph.js, js/graph-model.js).
2. Map step panel that opens under the graph when the node is selected: summary line,
   item flow strip, notices, item list with search, status chips + Slow toggle, sort,
   pagination of 50 rows with "Show more", and empty states.
3. A new item detail route with its own shareable URL (follow routes.md style) and the
   "no record of its own" partial state.

Hard rules (see HANDOFF.md, "Hard data rules"): never show a total N or a percentage bar;
use median/p95 only with ≥5 finished items; list only items that have a record and say so
in a notice; status is always label + icon, never colour only; all text is plain text (no
innerHTML); read-only, so no retry or stop buttons.

Tech constraints: plain HTML, CSS and vanilla JS ES modules. No framework, no CDN, no new
libraries. Reuse the existing CSS variables; add --map and --map-bg to the light block AND
both dark blocks in styles.css. Support light and dark theme, desktop and mobile (375–390 px).

Before writing code:
- Look at how the API (js/api.js) and models (js/model.js, js/graph-model.js) are shaped.
- Propose the data shape you need for map steps and items (counts per status, counts per
  inner step, records list, duration stats, record-limit info). If the backend does not
  send this yet, tell me and suggest a mock/fixture so the UI can be built first.
- Give me a short implementation plan (files to change or add) and wait for my OK.

After building:
- Add seeded demo data that covers every state in HANDOFF.md: running with no failures,
  running with 1 failed, failed, done, 0 started, 0 items, stalled, died, 10,000-item loop
  with partial detail, slow item, and data lost.
- Check the keyboard flow (Enter opens, Escape closes, focus returns to the row/node).
- Test light and dark themes, plus desktop and mobile widths.