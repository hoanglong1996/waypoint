# Research: Map Step (Loop Inside a Pipeline)

All findings come from reading the code on 2026-10-17 (library `0.5.0`, monitor at spec 013). No open
clarifications remain; each item below is a decision with its reasons and the alternatives rejected.

## R1. What the map step is at run level

**Decision.** The map step *block* is an ordinary step: entering it calls `begin(name)` (start marker, index `NN`),
leaving it normally calls `finish` (step record), leaving it with an exception calls `fail` (failure item). Its
step record carries `inputs` from the declared `over` source when the author passes it and `output` = number of
items that started. Everything per item is separate (R3).

**Why.** Every existing rule (running, stalled, died, done, "needs attention", heartbeat, History, duration,
alerting later) already works on that triple of records. An **older monitor** therefore shows the map step as one
ordinary step, which is exactly the compatibility the spec asks for (FR-029, US6 scenario 3). The block ending
cleanly is also what ends the map step (spec Clarifications: no total is declared).

**Rejected.** A new record type for the map step alone: the old monitor would show the step as missing.

## R2. How inner steps know their item, and the author's lines

**Decision.**
- A context variable `current_item` (a `ContextVar`, like `current_step` in `events.py`) holds the item scope.
  `StepAuditor.begin`, `finish`, `fail`, `record_metric` and `send_event` check it first and route to the item
  tracker when it is set. `@audited_step`, `waypoint_etl.log` and `waypoint_etl.metric` therefore need no new
  arguments (FR-004, "no manual item key per call").
- Authoring is `with waypoint_etl.map_step("accounts"):` around the whole loop and `with waypoint_etl.item(key):`
  around one pass. Both work in `async` code too (`async with` is accepted as well).
- `item()` finds its map in this order: an explicit `map=` argument, the `current_map` variable, the one open map
  block of the run. This last rule is needed because a `ThreadPoolExecutor` worker does **not** inherit the
  caller's context variables; the usual pattern (`with map_step(...): pool.map(process, accounts)` with `item()`
  inside `process`) must work. No match: nothing is recorded, one warning.
- An inner step's local index is a per-item counter (1, 2, 3 …). The decorator passes it back to `finish` and
  `fail` unchanged, as it does today.
- An exception that leaves an `item()` block is never suppressed. It marks the item failed (item-level error) when
  no inner step already failed.

**Why.** Context variables are right per thread and per asyncio task, so concurrent items cannot mix up (SC-003).
The decorator and the two entry points stay the only things authors touch.

**Rejected.** Passing `item=` to every inner step (noisy, error-prone); a thread-local (wrong for asyncio);
making the loop itself a library call (`waypoint_etl.map(fn, items)`): it would force one concurrency model on
authors, while the spec says authors keep their own loop (Assumptions).

## R3. Where item data lives

**Decision.** Two new key families, matched by none of the monitor's existing `SCAN` patterns
(`*:step:*`, `*:running:*`, `*:failed:*`, `*:metrics:*`, `*:events:*`, `*:flow`, `*:alive`, `*:died`):

```
waypoint:{pipeline}:{env}:{run_id}:map:{map}            one aggregate per map step per run (small, always read)
waypoint:{pipeline}:{env}:{run_id}:item:{map}:{key}     one record per detailed item (read on demand only)
```

Item keys contain no `:` (R9), so no item key can match `*:step:*` or any other pattern.

**Why.** The monitor reads every key of a pattern on every cache window. Putting items in the run list would turn
a 10,000-item loop into tens of thousands of reads per refresh. The aggregate gives the run page everything
(progress, counts, durations, failures, slowest) for one small key; item records are fetched with one `SCAN` on
the run-and-map prefix when an operator opens the item list.

**Rejected.** Storing items inside the aggregate (rewritten every second, grows with N); a Redis list or stream
(more commands and permissions, and paging by filter needs the whole set anyway).

## R4. Writing: merge in memory, one background writer

**Decision.** `MapTracker` holds the live state under one lock. `MapWriter` (daemon thread, same loop shape as
`MetricWriter`) wakes at most once per `MAP_FLUSH_SECONDS` (1 s), takes the dirty item records and the aggregate,
and writes them with one pipelined `write_many` (`SETEX` each, one round trip). `flush` and `stop` skip the wait;
leaving the map block flushes (at most 2 s) so the final aggregate is stored before the step's finish record. A
failing store is logged at most once a minute and the batch is dropped; the changed records are written again in
full on their next change. `write_many` is optional on a store: without it the writer calls `write` in a loop.

**Why.** FR-007 and SC-005: the loop pays dictionary updates. A thousand items finishing in one second become one
write pass. The writer is the proven pattern from specs 012 and 013.

**Rejected.** Inline writes per call (stalls on a dead Redis, 2 s per call); reusing the event writer (append-only
lists, wrong shape for last-state records).

## R5. Retention beyond 1,000 items

**Decision.** Every item gets an arrival number. For each map step:
- The first `MAP_DETAIL_LIMIT = 1000` items keep full records (inner steps, counts, durations, error with stack
  trace cut to 2 KiB, metrics).
- Later items live in memory only while running. When one **finishes**: if it failed and fewer than
  `MAP_EXTRA_FAILED_LIMIT = 1000` such failures were kept, a **compact** record is written (key, state, failed inner
  step, error type, message cut to 200 characters, no trace, no metrics). Otherwise, if it is among the
  `MAP_SLOWEST_KEPT = 50` slowest later items so far, a compact record is written, and the displaced slow item's
  record is overwritten with `SETEX … 1` (it expires in one second). All other later items leave only the
  aggregate.
- The aggregate always holds exact counts for every item, so numbers never depend on retention.

**Why.** FR-011/FR-012 and SC-004 need a fixed bound. Worst case per map step per run is about 1,000 full
(≤ 5 KB with trace cut) + 1,000 compact (≤ 0.6 KB) + 50 slow, a few MB; typical loops are far below that. Using
`SETEX` with a 1-second TTL avoids asking for `DEL`.

**Spec adjustment made during planning.** The spec first said "every failed item" keeps a record. That cannot
satisfy SC-004 ("fixed amount of data") when all 10,000 items fail, so FR-011 now says up to 1,000 further failed
items keep a compact record, and the rest are counted and the number shown (spec US5 scenario 5). Running items beyond the
limit appear only in the counts; the screen says so.

**Rejected.** Keeping every failure with a trace (unbounded); sampling failures at random (an operator cannot trust
a partial list with no stated rule).

## R6. Map step state and the synthetic failure

**Decision.** The monitor reads the aggregate and derives the state:
- block open → `running` (or `stalled` or `died` by the run's existing rules, which already use the start marker);
- block ended and `failed == 0` → `done` (including zero items);
- `failed ≥ 1` (block open or ended) → `failed`.

For `failed ≥ 1` with no real failure item for that attempt, `analysis._build_run` adds a **synthetic failure** to
the `current` failures: type `ItemsFailed`, message `"{n} of {started} items failed"` (numbers only), empty trace,
timestamps from the aggregate. A real failure item (the block itself raised) always wins. From there run status,
the "needs attention" group, the run's `failed` object, History and the graph behave as for any failed step
(FR-014, FR-027). While the block is still open and an item has failed, the step is shown as `running` with the
failed count in its progress and as `failed` only once the block ends. This keeps "running" truthful and still
makes a swallowed item error visible at the end.

**Why.** FR-027 forbids new states, and the loop can legitimately swallow item errors (a thread pool that collects
exceptions). Without the overlay the run would be "complete" with failed items inside.

**Rejected.** Making the library raise at the end of the block when items failed: it changes the author's control
flow, which recording must never do.

## R7. Item list API: filter, sort, stable paging

**Decision.** `GET .../maps/{map}/items` with `state` (`failed|running|done`), `slow=1`, `q` (substring of the key),
`sort` (`index|duration|key`) and `order`, `limit` (default 50, max 200) and a keyset cursor `after`. The item
order is always the sort value, then the arrival number, then the key, so it is total and deterministic. The cursor
carries the last item's sort value and arrival number. An item that changes its sort value between two requests
(a running item finishing while sorted by duration) may be skipped in this pass but is never repeated; a fresh
first page shows it. Counts per state (of the items that have records) come back with every page.

**Slow.** An item with a record is slow when its duration exceeds `slow_run_multiple × median item duration` and
the map has at least `duration_min_runs` finished items (the existing settings; FR-018). The median comes from the
aggregate's histogram. No new setting.

**Why.** Offset paging repeats or skips items when items arrive during paging, which FR-020 forbids. Keyset paging
cannot repeat. 1,000 records are read per request at most, within SC-009.

## R8. UI: expand, panel, item view

**Decision.** The graph keeps one node per step; a map node adds a progress line (`6 done · 4 running · 0 failed`)
and a failed-items pill (label and icon, not colour alone). **Expanded** means the map panel is open: selecting the
node opens it under the graph (the existing "selected step" area), showing the item flow with aggregate state per
inner step (`9 done, 1 running`), the summary numbers (loop duration, median, 95th percentile, slowest item, records
lost) and the item list with search, state chips, a slow chip, sort and "Show more". Selecting an item opens the item
view: its inner steps in order (`not run` after a failed one), counts, durations, errors, events (the events
endpoint filtered by item) and metrics, reusing the existing error, metrics and event renderers. Item state and
selection survive refresh like step selection does.

**Why.** Drawing items in the SVG would not scale to 10,000 (FR-024) and would need a second layout engine. The
panel reuses the existing layout, scroll and refresh code.

**Rejected.** In-graph expansion of the SVG node into a sub-graph; a separate page per map step.

## R9. Item keys and privacy

**Decision.** Item key limit: `^[A-Za-z0-9_.-]{1,64}$`. Any other character becomes `_`, the key is cut to 64, an
empty key becomes `item_{arrival number}`; one warning per distinct raw key (bounded to 100 kept in memory). After
sanitising, a key that already started in this map step of this run is a duplicate (spec Clarifications): first
record kept, later start ignored (its recordings are dropped), one warning. Keys are never passed through
`redact` (it is for free text); the documentation says ids or indices only.

**Why.** FR-005 and the constitution's PII principle. The character set excludes the characters that identify
people in practice (spaces, `@`, `+`, accents) and cannot contain `:`, which also protects R3.

## R10. Durations, histogram and what the numbers mean

**Decision.** Item and inner-step durations use the monotonic clock in whole milliseconds. The aggregate keeps
`count`, `sum_ms`, the exact `max` item (`slowest`, top 5) and a sparse histogram `{bucket: count}` with bucket =
`floor(ln(ms) / ln(1.1))` for `ms ≥ 1` (about 190 buckets cover one millisecond to one day). Median and 95th
percentile are the nearest-rank bucket's geometric midpoint: **within 5% of the true value**. The monitor
shows percentiles only when `count ≥ duration_min_runs` (existing setting) and marks them as approximate with the
`≈` sign in the UI. The loop duration is the map step's own duration (start marker to finish record, the existing
step duration).

**Why.** 10,000 durations in one record would be 60 KB rewritten every second; the histogram is a few hundred
bytes and the error is irrelevant for finding outliers, which the exact `slowest` list covers.

## R11. Item events and metrics

**Decision.** Events gain an optional `item` field (set from `current_item`; the `step` field is the inner step's
name). Event lists keep their caps (500/200/200 per run), so a huge loop cannot flood them; the existing `dropped`
count tells the operator. The events endpoint takes an `item` filter. Metrics inside an item are merged per inner
step with the existing `MetricState` (one instance per item, same limits: 20 names per step) and stored in the
item's record, not in separate keys. Metrics for items beyond the retention limit are dropped with the item's
detail (they are not summed into any aggregate in this release).

**Why.** Reuses specs 012 and 013 without a new store path, and keeps item data in one record per item (R3).

## R12. Not-run inner steps, skipped items, died and stalled runs

**Decision.** The item flow is linear (spec Clarifications). In the item view, a declared inner step with no entry
after the last started one is `not run` when the item failed or ended, `waiting` when it is running. Item states
written by the library are `running`, `done` and `failed`; the spec's "skipped" is not produced in this release (no
API creates it) and the monitor leaves room for it by ignoring unknown states. When the map step is `stalled` or
`died` by the run's rules, items stored as `running` are shown with that state instead of running forever.

## R13. Record versions and compatibility

**Decision.** Aggregate and item records carry `"v": 1`; the flow record's `v` stays 1 because a map step is an
added step field (`kind`, `over`, `max_concurrency`, `steps`) that an older monitor ignores while still seeing the
map step as an ordinary step (R1). The new monitor reads flows with no map step exactly as before. A damaged
aggregate or item is skipped and counted unreadable for its run. Item data written by a newer library with a
higher `v` is shown as unreadable, not guessed.
