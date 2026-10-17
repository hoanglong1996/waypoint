# Contract: What the operator sees

Plain text everywhere: map names, inner step names, item keys, error text and event text are escaped, never markup (FR-026).
State is shown with a label and an icon, never colour alone (FR-022).

## Graph and step list

- A map step is **one node**. Besides the usual state pill it shows a progress line `6 done · 4 running · 0 failed` (counts only,
  no total, no `n of N`) and, when any item failed, a pill `1 failed item`. Counts update on the normal refresh.
- Node text for assistive technology: `Accounts, map step. State: running. 6 done, 4 running, 0 failed. Concurrency limit 5.`
- A map step with `lost_items > 0` shows the existing data-loss pill with the text `items lost data`.
- A map step with `detail.partial` shows `item detail partial` in its panel (below), not on the node.
- Selecting the node **expands** it: the map panel opens in the existing "selected step" area (and in the step list's item for
  that step). `aria-expanded` on the node reflects it. Collapsing closes the panel. Selection survives refresh.
- A map step from an older library, or without an aggregate yet, is drawn as an ordinary step with no panel, and a map step
  whose block just started shows `0 started` and state running, not empty.

## Map panel

1. **Summary line**: state, `loop 41 s`, `median ≈3.9 s`, `p95 ≈9.1 s` (only when enough items finished; otherwise
   `percentiles need 5 finished items`), `slowest acct-7 (9.1 s)` as a button that opens that item, in and out sums, `concurrency limit 5`.
2. **Item flow strip**: the declared inner steps in order with aggregate state across items: `fetch 10 done`, `transform 7 done
   · 1 running · 1 failed`, `load 5 done · 1 running`.
3. **Notices**: when `detail.partial`: `Showing items with a record: 1,050 of 10,000. Totals cover every item.`; when
   `failed_without_record > 0`: `37 further failed items have no record of their own.`
4. **Item list** (one page at a time, never all items): search box (key substring), state chips `All`, `Failed`, `Running`,
   `Done` with the counts from the response, a `Slow` chip, sort control (`Order started`, `Duration`, `Key`) with direction,
   `Show more` (uses `next`). Row: key, state pill, duration, failed inner step and error type for failed items, in → out, and a
   `slow` or `data lost` marker. Filter, sort and search changes restart from the first page; refresh re-reads the pages already shown.
   Empty result: `No items match.`; map with no items: `No items started.`
5. **Failures first**: when the map failed, the failed chip is selected by default and the aggregate's `failed_items` show before
   the list loads.

## Item view

Opens on selecting a row (also from `slowest`); the URL carries it so a link reopens it. Shows: key, state, started and
duration; the **inner steps in order** with state, in and out counts, duration and (failed) the error block with the
stack trace exactly as for a step; `not run` for steps after a failed one and `waiting` while the item runs; the item's
**metrics** table (spec 013 renderer, declared units and thresholds); the item's **events** (the events renderer with the
`item` filter). A loss on an inner step uses the step data-loss pill. A running item refreshes with the run and keeps scroll
position and selection. An item with no record (beyond the limit) shows `This item has no record of its own (item detail is
partial).` with a link back to the list. Keys that look odd are shown as stored (already sanitised).

## History, Home and overview

No new column or state. A map step failed through items counts as a failed step: the run is `Failed`/`Incomplete`
exactly as with any failed step, and appears in "needs attention" the same way.

## States and empty cases

| Case | Display |
|---|---|
| Map step running, no item started | `0 started`, state running |
| Block ended, zero items | `0 items`, state done |
| Items failed, block still open | State running, `N failed` in the progress line, panel failed chip selected |
| Stalled or died run | Map state and running items show the run's state |
| Store unreachable | The existing error banner; no partial map panel |
| Damaged aggregate or item | Skipped, run `unreadable` count shown as today |
| Narrow screens | Item list rows stack: key and state first, then details; the panel scrolls with the page |

## Accessibility

Item list is a real list with `aria-live="polite"` for the match count; chips are toggle buttons with `aria-pressed`; the sort
control is a labelled select; focus returns to the row after closing the item view. Keyboard: Enter opens an item, Escape closes
the item view.
