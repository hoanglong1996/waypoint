# Map step design: v2 changes

This file covers what changed since the first handoff. Everything in `HANDOFF.md` still applies. If you already built v1, apply only the two changes below. If you have not started yet, build v1 with these changes included.

## Change 1: the item flow strip reuses the main graph's node and edge look

**Where:** the map step panel → "Item flow · counts across every item".
**Files:** `MapRunning`, `MapRunningFail`, `MapFailed`, `MapLarge` (desktop) and `MobilePanel` (mobile).

The old flat boxes with a small arrow icon between them are gone. Each inner step is now drawn with the **same visual language as the existing pipeline graph** (`.gnode` and `.gedge` in `styles.css`, `js/views/graph.js`). **Reuse those styles. Do not invent a second look.**

- **Node** (mockup class `.inode`, which corresponds to `.gnode`):
  - Head row: status pills (`Fine`, `N running`, `N failed`, `N lost data`, `N not run`, and `bottleneck` / `most failures` on the worst step).
  - Label row: group dot (`--map` colour) plus the inner step name.
  - Small mono line: "inner step 1".
  - Foot: big count of **items done at this step**, followed by "items done".
- **Node states:**
  - The step where items failed or lost data uses the loss style (same as `.gnode--loss`).
  - A step with running items uses the accent ring (same as the running / selected style).
- **Edge** (mockup class `.iedge`, which corresponds to `.gedge`):
  - A 3 px line, a count label box in the middle (`items 10`) and an arrowhead, like the main graph's `rows 120` labels.
  - The label shows the number of items handed to the next inner step, which is the previous step's done count.
- **Mobile (≤ 720 px):** nodes stack top to bottom and edges turn vertical, the same as the main graph's mobile layout.
- **Legend line:** "items handed to the next inner step · big number = items done at this step".
- **Hard rule still applies:** no totals and no percentage bars here.

## Change 2: item detail has a List | Graph switch for inner steps, like the run page's Steps section

**Where:** the item detail page → "Inner steps".
**Files:** `ItemFailed` (opens in List), `ItemRunning` (opens in Graph), `MobileItem` (opens in Graph).

The section header gets the same **segmented control** as the run page (`List` with the list icon, `Graph` with the graph icon). It is built from buttons with `aria-pressed`, and the choice is kept in the URL (`?view=graph`).

### List view (copy the run page's step list: `.steps`, `.step__rail`, `.step__node`, `.step__card`)

- **Rail:** a vertical rail with a numbered circle per step.
  - Green ring when the step is done, red when it failed or lost data, accent when running, dashed when not run or waiting.
- **Card:** three areas, `name | inputs | output`.
  - **name:** mono step name, with status, finish time and duration underneath.
  - **inputs:** an input chip such as `→ fetch 51`, or a dashed chip such as `input · 1 request` / `expects transform`.
  - **output:** the output count on the right ("rows out"), or a live timer for a running step.
- **Card states:**
  - **Failed step:** the card uses the loss style and the **error block sits inside the card** (type, message, stack trace that scrolls, Copy button).
  - **Not run / waiting:** the card has a dashed border with "skipped · transform failed" or "waiting for an earlier step".

### Graph view (same nodes and edges as Change 1, with rows instead of items)

- **Node:** status pill plus duration, step name, a small line (input / error type / start time), and a big count of rows out. A running step shows a live timer instead of the count.
- **Edges:**
  - Normal edge: `rows 51`, a solid line.
  - Data lost: `rows 0`, with a **red dashed line, red label and red arrowhead** (see `MobileItem`, acct-3).
  - Not run / waiting: a grey dashed line with the label "not run" or "waiting".
- **Nodes are buttons.**
  - Clicking one, or pressing Enter on it, selects it with the accent ring and `aria-pressed`, and shows that step's detail below the graph.
  - For a failed item, the failed step is selected by default, so the error block is visible straight away.
- **Mobile:** the graph runs top to bottom.

### Shared rules for both views

- Switching views keeps the scroll position.
- Live refresh keeps the selected view and the selected node.
- Status is always shown as a label plus an icon. Colour is never the only signal.

## Files touched in v2

`MapRunning.dc.html`, `MapRunningFail.dc.html`, `MapFailed.dc.html`, `MapLarge.dc.html`, `MobilePanel.dc.html`, `ItemFailed.dc.html`, `ItemRunning.dc.html`, `MobileItem.dc.html`.
