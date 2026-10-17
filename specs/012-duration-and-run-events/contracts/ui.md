# Contract: what the operator sees

## Duration

- **Format**: `37s`, `4m 05s`, `1h 04m`, `2d 03h`; under one second `<1s`; unavailable `—`; approximate `≈4m 05s` with a
  tooltip "estimated from the previous step"; running `4m 05s…` (trailing ellipsis, updates on refresh).
- **Run page**: total duration in the headline; duration beside each step in the List; a duration label under each Graph
  node name; the bottleneck step carries a "Slowest" tag with an icon, in List and Graph, plus a line in the headline
  ("Slowest: <step>, 62% of the run"). Not shown with fewer than two durations.
- **Home card**: latest run's duration (with `…` while running).
- **History**: a Duration column in the runs list; a "Run duration" chart next to "Step trend" (point per run, dashed
  median line, p95 band, flagged runs with a marker and label, tooltip with value and median); a stat line "Typical
  <median> · slow end <p95> · <n> runs", or "Not enough history yet (needs <min> completed runs)".
- **Slower than usual**: a pill with a clock icon and text, in the History row, the run page headline and the chart
  tooltip, e.g. "Slower than usual: 35m vs 10m typical". It is never in the attention group.

## Events

- **Run page tabs**: `Steps | Events` (hash query `?tab=events`). Events shows, newest last, a table-like list: time
  (`hh:mm:ss`, tooltip full time), level (icon + word), step (chip linking to the step), message, fields as small
  `name value` chips. Derived entries carry a small "monitor" tag.
- **Filters**: level checkboxes (info, warning, error) and a step select; "N of M events"; filters live in the hash query
  (`level`, `step`) so the view is shareable and survives refresh.
- **Paging**: first 200, then "Load more" until `has_more` is false.
- **Live**: while the run is running the loaded pages are refetched each `REFRESH_SECONDS`; filters and scroll position
  are kept; new events at the bottom are announced politely to screen readers.
- **Notes** (above the list): "N events were dropped (limit reached)" when `dropped > 0`; "This pipeline does not send
  events. Upgrade the library to 0.4.0 to add your own." when `recorded == 0`; "N unreadable event records skipped."
- **Step details**: the step's events (up to 10 newest) with "View all in timeline" linking to `?tab=events&step=<name>`.
- **Home card and History row**: `⚠ 2` and `⛔ 1` chips with the words "warnings" / "errors" in the accessible name; nothing
  when both are zero.
- **Text**: all event text is rendered through the escaping helpers; never as HTML.
- **States**: loading (skeleton rows), empty ("No events match the filters"), error ("Could not load events", retry).
