# Map step: design handoff for Waypoint Monitor

> **v2:** see `CHANGES-v2.md`. The item flow strip now reuses the main graph's node and edge style, and the item detail page has a List | Graph switch for its inner steps.

This package holds the design for one new feature, the **Map step** (a loop inside a pipeline). Build only this feature. Do not redesign the rest of the dashboard.

## What is in this folder

`mockups/*.dc.html` are design mockups. Each file is plain HTML and CSS: one `<x-dc>` block holding the markup and a `<helmet><style>` block holding the CSS. Some files have a small `<script type="text/x-dc">` block that only feeds sample rows into `<sc-for>` loops. That script is not real app code. Use these files as the visual and markup reference only: copy class names, structure, spacing and tokens, but don't copy the `x-dc` / `sc-for` / `sc-if` runtime.

| File | What it shows |
|---|---|
| `MapNodes.dc.html` | 3.1, the map step node in the graph. All variants: Running (with and without failures), Failed, Done, Done with data lost, 0 started, 0 items, Stalled, Died, selected (expanded), large counts / long name, narrow screen |
| `MapSpec.dc.html` | Spec tables (node states, item pills, inner-step pills, chips / search / sort) and the interaction notes. **Read this first.** |
| `MapRunning.dc.html` | Panel: running, 4 items in parallel, no failures |
| `MapRunningFail.dc.html` | Panel: still Running but 1 item failed; a slow running item; an item with data lost |
| `MapFailed.dc.html` | Panel: Failed, with the Failed chip pre-selected. The `renderVals()` in this file is a working example of the filter, search and sort logic |
| `MapLarge.dc.html` | Panel: 10,000 items, with the partial-detail notice, the "37 failed items have no record" notice and Show more |
| `MapEdge.dc.html` | Edge states: 0 started, 0 items (Done), no match, Stalled, Died, item without its own record |
| `ItemFailed.dc.html` | 3.3, item detail for a failed item (error block, stack trace, copy, not run, metrics, events) |
| `ItemRunning.dc.html` | Item detail for a running item (live timer, Waiting step, live refresh banner) |
| `MobilePanel.dc.html` | Mobile 390 px: vertical graph, panel, stacked item rows |
| `MobileItem.dc.html` | Mobile 390 px: item detail with data lost at `transform` |

## Where it sits in the existing app

- **Node:** goes in the existing Run detail page → Steps tab → Graph view (`js/views/graph.js`, `js/graph-model.js`). A map step is drawn as one node.
- **Panel:** opens directly **under the graph card** when the node is selected.
- **Item detail:** a new route, for example `#/p/<pipeline>/runs/<env>/<run>/steps/<mapStep>/items/<key>`. Follow the style of `routes.md`. Panel state goes in the query: `?items=failed&slow=1&sort=duration-desc&q=acct`.

## Hard data rules (must follow)

1. **There is never a total N.** Show only items that have started: "6 done · 4 running · 1 failed". Never write "6 of 10", and never draw a progress or percentage bar.
2. **Item status:** running, done, failed. **Inner-step status inside an item:** done, running, failed, not run (after a failed step), waiting (the item is running and this step has not been reached yet).
3. **Map step status:**
   - **Running:** the loop is still open, even when some items have failed. Failures are still counted and shown as a pill.
   - **Failed:** the loop has closed and at least 1 item failed.
   - **Done:** the loop has closed and no item failed. This includes 0 items, which shows as "0 items".
   - **Stalled / Died:** taken from the run's status. Running items are displayed with that status.
4. **Scale:** up to about 10,000 items, but only about 1,050 have a detailed record: the first 1,000, the failed ones and the 50 slowest. Totals are always correct for every item. The list, search and filters only cover items that have a record. Show this as: "Showing items with a record: 1,050 of 10,000. Totals cover every item." When it applies, also show "N further failed items have no record of their own."
5. **Paging:** never render every item. The list pages 50 rows at a time with a "Show more" button.
6. **Durations:**
   - Show the loop duration.
   - Show median and p95 as approximations ("≈"), only once at least 5 items have finished. Before that, show "percentiles need 5 finished items".
   - Show the slowest item as a link.
   - An item is **slow** when its duration is more than about 2× the median.
7. **Data loss:** an inner step received input but produced 0 output. Flag it on the item ("data lost") and on the node ("items lost data").
8. **Text:** all strings (keys, step names, errors, events) are plain text. Never use innerHTML with them. Long strings wrap (`overflow-wrap:anywhere`) and are never truncated. Item keys are at most 64 characters from `[A-Za-z0-9_.-]`.
9. **Status is never colour only:** every status always has a text label and an icon.
10. **Read-only:** no retry, stop or re-run buttons.
11. **Concurrency limit** (for example "concurrency limit 5") is information only.

## Design tokens

Reuse the existing CSS variables from `styles.css`. The mockups add one new pair, which must be added to the light block **and both dark blocks**:

```css
/* light */
--map: #6a3fc4;  --map-bg: rgba(115, 73, 204, .07);
/* dark (both dark blocks) */
--map: #b9a2ff;  --map-bg: rgba(185, 162, 255, .08);
```

`--map` is used only to identify a map step (the loop icon and the MAP tag). It is never used for a status.

The node's "stacked card" look is pure CSS:

```css
box-shadow: 5px 5px 0 -1.5px var(--surface), 5px 5px 0 0 var(--border-strong),
            10px 10px 0 -1.5px var(--surface), 10px 10px 0 0 var(--border-strong);
```

## Accessibility and interaction (summary; full notes in MapSpec)

- **Node:** a real `<button>` with `aria-expanded` and `aria-controls`.
  - Enter, Space or a click toggles the panel.
  - When the panel opens, focus moves to the panel heading.
  - Esc (with focus inside the panel) or the Close button closes the panel and returns focus to the node.
- **Status chips:** All / Failed / Running / Done are buttons with `aria-pressed` and work as a one-of-four group. **Slow** is a separate toggle that combines with the status chip (AND).
- **Default filter:** All, sorted by order started ascending. If the map step is **Failed**, the Failed chip is pre-selected and a hint offers "Show all". In the All view of a failed step, failed rows sort first.
- **Search:** case-insensitive "contains" on the key.
- **Sort:** a labelled select (Order started / Duration / Key) plus a direction button with an `aria-label`. Key sort is natural, so acct-2 comes before acct-10.
- **Result count:** shown in a `role="status" aria-live="polite"` line.
- **Item list:** a real `<ul>`, with each row one `<a>`.
  - Enter opens the item.
  - Esc or Back on the item page returns to the list, with the filters, scroll position and **focus on that row** restored.
- **Live refresh** (every 5 s while the run is active):
  - Merge items by key. New items are added at the end, and rows never jump.
  - Keep the filters, scroll position, focus and open panel.
  - Stop polling when the run ends, stalls or dies.
- **Mobile (≤ 720 px):**
  - The graph stacks vertically.
  - Item rows stack in three lines: key + status, then where / error, then duration · in → out · flags.
  - Touch targets are at least 44 px.

## Sample data used in the mockups

- **Map step:** `accounts` (label "Accounts"), concurrency limit 5, inner steps fetch → transform → load.
- **Running:** 6 done · 4 running · 0 failed.
- **Failed:** 9 done · 1 failed.
  - acct-7 failed at `transform` with ValueError "bad date" after 9.1 s.
  - Median ≈3.9 s, p95 ≈9.1 s, loop 41 s.
- **Large loop:** 10,000 started · 9,812 done · 188 failed.
  - 151 of the failed items have a record; 37 don't.
  - 1,050 items have a record.
- **Data lost:** acct-3, where `transform` took 48 rows in and returned 0.
- **Long key example:** `customer_00012345.part-0007`.
