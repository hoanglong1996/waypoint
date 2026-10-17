# Feature Specification: Map Step (Loop Inside a Pipeline)

**Feature Branch**: `014-map-step-fan-out`

**Created**: 2026-10-17

**Status**: Done - library version 0.6.0 (release tag and install URLs are updated at release time)

**Input**: User description: "Map step / fan-out, please do this feature, it allow my pipeline support a loop inside" — roadmap item 7 (Map step / fan-out) in `specs/roadmap.md`.

## Problem

Many real pipelines contain a loop: one big step repeats the same small flow for every account, file, customer or batch (for example `A → B → [for each account: fetch → transform → load] → C → D`). Waypoint Monitor can only draw a pipeline as a fixed sequence of steps, so such a loop is a single opaque box. When one iteration fails or runs slowly, the operator sees "step failed" or "step took 40 minutes" and must open logs to learn *which* item, at *which* inner step, and how many of the others were fine. Per-item counts, durations, errors and events are invisible, and a lost row in one item hides inside the loop's total.

## Proposed approach

The pipeline author declares a **map step**: a step that runs a small inner flow (the **item flow**) once per **item**, possibly several items at the same time up to a declared limit. Inside the item flow the author records steps exactly as today; each recording is automatically tied to the item that is running. The monitor shows the map step as one expandable node with progress ("7 done, 2 running, 1 failed"), a combined result, and an item list the operator can search, filter and sort. Opening an item shows that item's own inner steps, counts, errors, events and metrics. The map step's overall state is derived from its items, so a failure in one item is never hidden inside a green total.

Pipelines that do not use a map step, and runs from earlier library versions, behave and look exactly as before. Recording stays safe: it never breaks the pipeline, never stores data content, and a very large loop never floods the monitoring store.

## Clarifications

### Session 2026-10-17

- Q: Should the item flow be only a linear sequence of inner steps, or also support branches and parallel inner steps? → A: Linear sequence only; parallelism between items is supported, branches inside an item flow are out of scope for this release.
- Q: When an item's error aborts the whole loop, how are items that never ran shown? → A: (Superseded by the total-count answer below.) The map step is failed because of the failed item; items that never started are not known to the monitor.
- Q: Beyond the detail limit, which items keep detailed records besides failed ones? → A: The 50 slowest items seen so far in that map step (fixed, not configurable).
- Q: How does the monitor learn the total number of items of a map step? → A: It never does. The author does not declare a total; the monitor counts only items that have started, and the map step ends when the author's loop leaves the map step block. Progress is shown without a denominator.
- Q: When the same item key starts a second time in one map step of a run, is it a retry or a duplicate? → A: A duplicate key is an author error: the first record is kept, the later start is ignored with one warning. Item retries are not modelled; a retry the author does inside an item is part of that item.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See live progress and the exact failing item of a loop (Priority: P1)

A pipeline author declares a map step "accounts" over ten accounts, with an item flow of three inner steps and up to five items at the same time. The operator opens the run while it is in progress and sees the map step as a single node on the graph with progress ("6 done, 4 running, 0 failed") that updates on the normal refresh. When item "acct-7" fails in its second inner step, the node shows one failed item. Opening the node lists the items; the failed one shows which inner step failed and its error, without reading any log.

**Why this priority**: This is the core value: turning an opaque loop into something where the failing item and inner step are visible. Everything else builds on items being tracked at all.

**Independent Test**: Run a map step with 10 items, concurrency 5, where one item raises in its second inner step; while it runs confirm the progress numbers are right, and afterwards confirm the failed item, the failed inner step and its error are shown and the other nine items show as done.

**Acceptance Scenarios**:

1. **Given** a run whose map step has 10 items and 4 are running, 6 finished and none failed, **When** the operator views the run, **Then** the map step node shows "6 done, 4 running" (10 started) and the numbers match the true state within one refresh interval.
2. **Given** an item that failed in its second inner step, **When** the operator opens the map step, **Then** the item is listed as failed and its details name the inner step and show the error.
3. **Given** a map step with at least one failed item **When** the run is shown, **Then** the map step and the run are marked failed, consistent with how a failed ordinary step is treated.
4. **Given** a map step with items still running, **When** it is shown, **Then** it is marked running, and it becomes done only when every item has finished successfully.
5. **Given** a map step whose block has started but no item has started yet, **When** the run is shown, **Then** it is shown as running with "0 started" rather than empty or broken.
6. **Given** item keys or step names containing markup characters, **When** displayed, **Then** they appear as plain text.

---

### User Story 2 - Declare a loop and record per-item steps with one extra line (Priority: P1)

The pipeline author describes the map step in the pipeline description (name, which earlier step supplies the items, how many run at once, and the inner steps) and wraps the body of their existing loop so each pass is identified by a short item key. The inner steps are recorded with the same tools used for ordinary steps. The author does not change how the loop itself runs: it may be a plain loop, a thread pool or an async fan-out.

**Why this priority**: Adoption depends on it being a few lines on top of existing code. Without a simple authoring path there is no data for the monitor to show.

**Independent Test**: Convert a plain `for` loop and a thread-pool loop to use the map step; confirm that in both cases every item and inner step appears in the monitor with correct keys, and that items running in parallel are never mixed up.

**Acceptance Scenarios**:

1. **Given** a pipeline description containing a map step with inner steps, **When** the pipeline starts, **Then** the monitor shows the map step node with its item flow before any item has run.
2. **Given** a loop body wrapped with an item key, **When** inner steps run inside it, **Then** each inner step record belongs to that item and no other.
3. **Given** items running in parallel across several threads or async tasks, **When** each records inner steps, counts, errors, events and metrics, **Then** each record is attributed to the correct item with no cross-contamination.
4. **Given** the map step declares a concurrency limit, **When** the monitor shows the step, **Then** it displays the limit and, while running, never claims more simultaneous items than the observed running ones.
5. **Given** a call that records an inner step outside any item, **When** it is made, **Then** it is treated as an ordinary step or ignored exactly as today, and nothing raises.
6. **Given** an invalid item key (empty, too long, disallowed characters), **When** it is used, **Then** it is rejected or replaced by a safe form without raising, with a warning logged once, and the pipeline continues.
7. **Given** an inner step of the map step that is also declared with the name of a top-level step, **When** the pipeline description is validated, **Then** the description is invalid in the same way a duplicate step name is today, so tracking is off and the usual warning names the problem.

---

### User Story 3 - Find slow and failing items in a big loop (Priority: P2)

For a map step with hundreds or thousands of items, the operator opens the item list and filters to failed, running or slow items, searches by item key, and sorts by duration. The map step summary shows how long the whole loop took, and the typical (median) and slow-end (95th percentile) item duration, plus the slowest item, so one outlier is spotted immediately.

**Why this priority**: Per-item visibility pays off most at scale, but needs the P1 stories to exist first.

**Independent Test**: With a map step of 200 items where three are failed and five are noticeably slower than the rest, filter by failed (3 shown), filter by slow (the five), sort by duration (slowest first), and search a key; confirm the summary durations are correct.

**Acceptance Scenarios**:

1. **Given** a map step with many items, **When** the operator filters by failed, running, done or slow, **Then** the list shows exactly the matching items.
2. **Given** an item list longer than one page, **When** the operator moves between pages, **Then** items are not repeated or skipped and the filter and sort stay applied.
3. **Given** finished items with different durations, **When** the summary is shown, **Then** it shows the total loop duration, the median and 95th-percentile item durations, and names the slowest item.
4. **Given** the operator types part of an item key, **When** the list is searched, **Then** only items whose key matches are shown.
5. **Given** a map step with fewer finished items than the minimum needed for a meaningful percentile, **When** the summary is shown, **Then** it shows durations without percentile figures instead of misleading ones.

---

### User Story 4 - Inspect one item's own steps, counts, errors, events and metrics (Priority: P2)

The operator selects one item and sees its inner steps in order with the state of each inner step, how many records went in and out of each, how long each took, any error, the item's events, and the metrics its steps recorded. A discrepancy in one item (for example 100 in, 80 out) is visible there even though the loop total looks plausible.

**Why this priority**: Makes per-item data loss and per-item errors diagnosable, which is the main reason to have a map step.

**Independent Test**: Run an item whose last inner step outputs fewer records than it received; confirm that the item's detail flags the loss and the item's events and metrics show only that item's data.

**Acceptance Scenarios**:

1. **Given** an item with three inner steps, **When** its details are opened, **Then** each inner step shows state, in and out counts, duration and any error.
2. **Given** an item whose inner step output fewer records than its input, **When** shown, **Then** the loss is flagged the same way a loss on an ordinary step is.
3. **Given** events and metrics recorded inside an item, **When** its details are opened, **Then** they show only that item's events and metrics.
4. **Given** the map step's summary, **When** it is shown, **Then** in and out counts of the map step equal the sums over its items, and any item-level loss is reflected in a "records lost" indicator on the map step.
5. **Given** an item that is still running, **When** its details are open, **Then** the view updates on the normal refresh without losing selection or scroll position.

---

### User Story 5 - Keep a huge loop from flooding the monitoring store or the screen (Priority: P2)

A map step iterates over 10,000 items. The library keeps detailed per-item data only up to a fixed number of items per map step; beyond that it keeps counts for all items but detailed records only for failed and slow ones, so the monitoring store does not fill up. The monitor stays responsive and states clearly when detail is partial.

**Why this priority**: Without a cap, the first very large loop could harm the shared monitoring store, which is a risk to every pipeline.

**Independent Test**: Run a map step of 10,000 items; confirm the monitor opens the run quickly, the totals cover all 10,000 items, detailed records exist for failed items (up to the failure detail limit) and the 50 slowest items, and the screen states that only some items have detail.

**Acceptance Scenarios**:

1. **Given** a map step over more items than the detail limit, **When** it runs, **Then** summary counts include every item while detailed per-item records are kept up to the limit plus up to 1,000 further failed items and the 50 slowest items.
2. **Given** a map step in that state, **When** it is shown, **Then** the screen states that item detail is partial and how many items have detail.
3. **Given** a map step over 10,000 items, **When** the operator opens the run page, **Then** the page is usable in under 3 seconds and does not draw every item at once.
4. **Given** a failed item beyond the detail limit (and within the failure detail limit), **When** the map step is shown, **Then** that item is still listed with its error type and short message.
5. **Given** more failed items than the failure detail limit, **When** the map step is shown, **Then** all failures are counted, the first ones are listed, and the screen states how many failures have no record of their own.

---

### User Story 6 - Existing pipelines and older libraries keep working unchanged (Priority: P1)

An operator running pipelines that do not use map steps, or that run on an older library version, sees them exactly as before, and a mixed environment (some upgraded, some not) shows no errors or banners.

**Why this priority**: The monitor is shared by every pipeline; a regression here would affect everything already in use.

**Independent Test**: Open runs recorded before this feature, runs from the previous library version and runs from a pipeline with no map step; confirm identical display, no errors, and that the previous library version is unaffected when the monitor is upgraded first.

**Acceptance Scenarios**:

1. **Given** a run from a pipeline with no map step, **When** shown, **Then** it displays exactly as before.
2. **Given** a monitor with this feature and a pipeline on an older library, **When** the run is shown, **Then** it displays without errors or warnings about missing item data.
3. **Given** a pipeline using a map step whose monitor is older, **When** the older monitor shows it, **Then** it ignores item data safely and does not fail (the map step may appear as an ordinary step).

---

### Edge Cases

- **Loop aborted by an item's error**: items that never started are unknown to the monitor and are not shown; the map step is failed because of the failed item and the map step block ends with the loop.
- **Zero items**: a map step whose block ends without any item starting completes as done with "0 items", not as waiting forever or failed.
- **Total never known**: progress always shows done, running and failed counts and the number started, never "n of N".
- **Map step block never ends**: if the loop block is not left cleanly (for example the process dies), the map step is treated like a running ordinary step: running until the run ends, stalled or died as the run does.
- **Duplicate item key**: when an item key starts a second time in the same map step of a run, the first record is kept, the later start and everything it would record are ignored, and one warning is logged per key. Re-running a failed item as a new item is not supported; a retry the author performs inside the item's own code is part of that one item.
- **Item that fails midway**: inner steps after the failed one did not run for that item and are shown as "not run", not as failed or done.
- **Branching item flow**: declaring branches or parallel inner steps inside an item flow makes the description invalid with a clear warning and tracking falls back to off.
- **Nested map step**: a map step inside an item flow of another map step is not supported in this release; declaring one makes the description invalid with a clear warning and tracking falls back to off.
- **Process dies mid-loop**: running items are treated as stalled or died exactly like a running ordinary step, and the map step shows how many items had finished.
- **Worker in a separate process**: items executed in child processes are not attributed unless the child sets up recording itself; this is a known limit and is documented rather than hidden.
- **Item keys that look like content**: keys are identifiers or short indices, never data content; long or unusual keys are shortened or rejected rather than stored as given.
- **More items running than the declared limit**: the monitor shows the observed number and does not fail; the limit is informational.
- **Item still running after the map step's other items finished**: the map step stays running; the slow item is highlighted in the list.
- **Monitoring store unreachable or the library not set up**: recording does nothing and raises nothing; the loop runs unchanged.
- **A damaged item record**: it is skipped and counted as unreadable; the rest of the map step and run are shown.
- **Pagination while items change**: moving between pages while items finish never shows an item twice or hides one permanently.
- **Item events and metrics beyond existing per-step limits**: the existing limits apply per item and per step; beyond them, entries are dropped with one warning, as today.

## Requirements *(mandatory)*

### Functional Requirements

**Declaration and recording**

- **FR-001**: The pipeline description MUST allow declaring a map step with a name, an optional reference to the earlier step that supplies its items, an optional concurrency limit, and an item flow made of one or more inner steps run one after another in a fixed order (with the same optional details as ordinary steps). Branches or parallel inner steps inside one item are not supported.
- **FR-002**: The declaration MUST be published with the pipeline's self-describing structure so the monitor shows the map step and its item flow before any item has run.
- **FR-003**: The library MUST offer a way to mark the whole loop as the map step block, and a way to mark a block of code inside it as one item, identified by a short item key, such that every inner step, count, error, event and metric recorded inside the item block belongs to that item. The author never declares a total item count.
- **FR-004**: Item attribution MUST be correct when several items run at the same time in threads or async tasks, and MUST NOT require the author to pass the item key to each inner step manually.
- **FR-005**: Item keys MUST be short identifiers or indices, never data content. Key length and allowed characters MUST be limited; invalid keys MUST be rejected or replaced by a safe form without raising, with one warning logged per key. A key that starts a second time in the same map step of a run MUST be ignored (first record kept) with one warning logged per key.
- **FR-006**: The system MUST no longer assume that steps of a run execute one at a time: several items and their inner steps MUST be able to be in progress simultaneously without overwriting each other's state.
- **FR-007**: Recording items MUST do nothing and raise nothing when the library is not set up, setup failed or the store is unreachable; at most a warning is logged. It MUST NOT block the loop or add materially to its run time.
- **FR-008**: Everything recorded for items MUST expire together with the rest of its run's data, and MUST NOT include data content: only names, keys, counts, times and short diagnostic text, as for ordinary steps.
- **FR-009**: Inner steps inside an item MUST support the same recording as ordinary steps: finish with in/out counts, failure with error, events, and metrics, each carrying the item key.
- **FR-010**: A map step declared with the name of an existing step, an empty item flow, a duplicate inner step name, or a nested map step MUST make the pipeline description invalid, with tracking off and a warning naming the problem, consistent with existing validation.

**Scale and limits**

- **FR-011**: The library MUST limit the number of items per map step for which detailed per-item records are kept (default 1,000). Beyond the limit, counts for all items MUST still be aggregated, and detailed records MUST still be kept for every failed item for the first 1,000 further failed items (as compact records: error type and a short message, no stack trace), and for the 50 slowest items seen so far in that map step (all fixed in this release, not configurable). Failures beyond that are counted and their number is shown, but have no record of their own.
- **FR-012**: Aggregate counts (total, done, running, failed, skipped) for a map step MUST remain correct for all items, including those beyond the detail limit.
- **FR-013**: The monitor MUST state clearly when item detail is partial and how many items have detail.

**Monitor: state and numbers**

- **FR-014**: The monitor MUST derive a map step's state from its block and items: running from when the map step block starts until it ends; failed once the block has ended if any item has failed (while the block is open the step stays running and the failed count is shown); done when the block has ended and every item that started finished successfully (including when no item started). Skipped items do not make a map step failed.
- **FR-015**: The monitor MUST show a map step's progress as counts of done, running, failed and started items, without any total, updated on the normal refresh interval.
- **FR-016**: The monitor MUST compute a map step's in and out counts as the sums over its items, and show per-item loss using the same rule as for ordinary steps; the map step MUST indicate when any item lost records.
- **FR-017**: The monitor MUST provide, for each map step, the loop duration and the median, 95th-percentile and slowest item durations; percentiles MUST be shown only when enough items have finished.
- **FR-018**: The monitor's "slow" classification and filter for items that have detailed records MUST reuse the existing slow-duration setting and rule (spec 012); no new setting is introduced. This is separate from which items the library retains beyond the detail limit (FR-011).
- **FR-019**: The monitor MUST return map step data in summary form by default (counts, durations, failed and slow items) and provide the item list separately, paged, filterable by state (failed, running, done, slow) and by item key text, and sortable by duration or key.
- **FR-020**: Paging MUST be stable: while items change, no item is shown twice on consecutive pages in one pass and the sort order is deterministic.
- **FR-021**: The monitor MUST provide, for one item, its inner steps with state, in/out counts, duration, error, events and metrics, so clients do not recompute them.

**UI**

- **FR-022**: The run graph MUST show a map step as one node that can be expanded and collapsed, showing progress (done, running and failed counts) and the number of failed items even when collapsed, with state conveyed by label or icon and not by colour alone.
- **FR-023**: Expanding a map step MUST show its item flow with aggregate state per inner step across items (for example "9 done, 1 running") without drawing every item.
- **FR-024**: The item list MUST support search by key, filters by state, sorting by duration, and paging, and MUST not render all items at once for large maps.
- **FR-025**: The item details view MUST show that item's inner steps in order, counts, durations, errors, events and metrics, and refresh with the run while keeping selection and scroll position.
- **FR-026**: All item keys, step names, error text and event text MUST be displayed as plain text, never interpreted as markup.
- **FR-027**: The existing run-level status, "needs attention" grouping and history views MUST treat a failed map step like any failed step, with no new states introduced.

**Compatibility**

- **FR-028**: Runs and pipelines without map steps MUST display correctly with no errors or warnings about missing data and no change to layout.
- **FR-029**: A new monitor MUST read runs from older library versions, and an older monitor MUST ignore item data safely.
- **FR-030**: The data format for item records MUST be versioned so that older and newer components remain compatible.
- **FR-031**: The monitor MUST remain read-only toward item data; it never triggers, retries or re-runs items.
- **FR-032**: A damaged item record MUST be skipped and counted as unreadable without hiding the rest of the run.
- **FR-033**: Items processed in a separate process MUST NOT be attributed incorrectly; the known limit MUST be documented.

### Key Entities

- **Map step**: A step that runs an item flow once per item; attributes: name, source step (optional), concurrency limit (optional), item flow, aggregate state and counts, durations, partial-detail indicator.
- **Item flow**: The ordered sequence of inner steps run for each item; shares the naming and uniqueness rules of ordinary steps but has no branches.
- **Item**: One pass of the item flow for one key within a map step in a run; attributes: key, state, start and end times, per-inner-step results.
- **Item key**: A short identifier or index naming an item; never data content.
- **Inner step result**: The result of one inner step for one item: state, in/out counts, duration, error, events, metrics.
- **Map step summary**: Aggregated numbers for all items of a map step: counts per state, in/out sums, loop duration, median, 95th percentile, slowest item, failed and slow items.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a map step with 10 items and concurrency 5, the progress shown during the run matches the true number of done, running and failed items within one refresh interval in 100% of tested states.
- **SC-002**: When one item fails in one inner step, an operator identifies the item and the inner step from the run page in under 15 seconds without opening logs.
- **SC-003**: With 8 workers each processing items in parallel and recording inner steps, 100% of records are attributed to the correct item in tested runs.
- **SC-004**: A map step over 10,000 items makes the run page usable in under 3 seconds, adds no more than a fixed, documented amount of data to the monitoring store per map step, and still reports correct totals for all 10,000 items.
- **SC-005**: A loop recording items adds no more than 5% run time compared to the same loop without recording (excluding the time of the loop's own work).
- **SC-006**: With the monitoring store unreachable, a pipeline using map steps behaves identically (same results and errors) in 100% of tested cases.
- **SC-007**: In a map step with a single item that loses records, the loss is visible at the item and at the map step in 100% of tested cases.
- **SC-008**: Runs without map steps and runs from the previous library version display with no error banners and unchanged layout in 100% of tested states.
- **SC-009**: Filtering and sorting a map step with 1,000 items returns the first page in under 1 second.
- **SC-010**: A pipeline author converts an existing loop to a map step by adding one declaration and one wrapper, with no other change to the loop's logic, in the documented example.

## Assumptions

- Waypoint remains a monitor: it observes items, it does not start, retry, schedule or re-run them. Per-item retry as a control action is out of scope; a retry the pipeline performs inside an item's own code is part of that item, and the same key starting twice is treated as a duplicate (see Edge Cases).
- The map step's overall success is "all items succeeded"; partial success is shown (counts and failed items) but is not a separate run state. A map step with failed items is failed, consistent with ordinary steps.
- Typical loop sizes are tens to hundreds of items, with a supported upper range of about 10,000; the default detail limit is 1,000 items per map step and is fixed in this release.
- Concurrency in the loop is created by the author's own code (threads, async, or plain loop); the map step declaration documents the intended limit and the monitor displays it, but the library does not run the loop.
- Item keys are provided by the author and are identifiers (ids or indices), not names or contact data; the author is responsible for not using personal data as a key, and the library limits length and characters to reduce the risk.
- Item flows are a linear sequence of inner steps (decided in clarification); branches inside an item flow and nested map steps are out of scope. Parallelism between items is supported.
- Items executed in separate processes need the author to set up recording in the child; automatic cross-process attribution is out of scope.
- Heartbeat and liveness stay at run level; an item is never considered alive on its own.
- Existing limits for events and metrics (spec 012 and 013) apply per item and per step; no new limits are introduced for them except the item detail limit.
- This requires a new record format version and a new minor library release; the monitor must work before any pipeline is upgraded.
- The "slow" threshold is the existing global setting (spec 012); per-pipeline or per-map-step thresholds are out of scope.
- Roadmap prerequisites #1, #2, #3 and #5 (failures, durations, events, metrics) are complete; the item key is added as a new dimension to them.
