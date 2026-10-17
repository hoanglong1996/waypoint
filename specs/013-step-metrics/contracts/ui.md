# Contract: What the operator sees

## Step details (run page list, and the graph's "Selected step" panel)

- A **Metrics** block under the step's counts, only when the step has metrics. A compact table: name (label when declared, the
  name in a tooltip), value with unit (`150 rows`), and a flag cell.
- Declared first (declared order), then undeclared alphabetically. Declared but not reported: value shown as `not reported`
  in muted text, never `0`, never flagged.
- Flag cell: icon plus text (`above 100`, `below 90`), not colour alone, with the threshold.
- While the run is live the block updates on the normal refresh without resetting scroll or selection.
- Values are formatted compactly (`12.3k`, `0.25`); the exact value is in the tooltip.
- Names, labels and units are escaped plain text.

## Step list and graph

- A small badge on a step with at least one flagged metric: a warning icon and the count (`1 metric over limit`), shown in the
  step card header (list) and on the node (graph). The badge text is in the accessible name.

## History

- A **Metric trend** card below Step trend, shown only when the shown runs declare at least one metric.
- Two selects: step (steps that declare a metric) and metric (that step's declared metrics, label or name).
- Line chart oldest to newest; runs where the metric was not reported are gaps; a dashed median line when at least
  `duration_min_runs` runs reported it (over the newest `duration_window_runs`); a threshold line for each declared limit; a
  flagged point has a distinct marker shape; tooltip with run, value, unit.
- No metric picker and no card when nothing is declared.

## Unchanged

Home cards, status pills, "needs attention" order, Events tab, durations.
