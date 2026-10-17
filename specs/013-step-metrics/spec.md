# Feature Specification: Optional Step Metrics

**Feature Branch**: `013-step-metrics`

**Created**: 2026-10-17

**Status**: Done - library version 0.5.0 (release tag and install URLs are updated at release time)

**Input**: User description: "Metric tuỳ chọn theo step. thực hiện feature này" — roadmap item 5 (Optional metrics per step) in `specs/roadmap.md`.

## Problem

Waypoint Monitor shows, for each step, how many items went in and out, how long it took (spec 012) and what happened along the way (events). It cannot show the few extra numbers that explain *why* a step behaves as it does: rows rejected, retries made, pages read. Today an author can put such numbers in an event's named values, but they are free-form, appear only in the timeline, cannot be summed or compared across runs, and cannot be flagged when they go out of range.

## Proposed approach

The pipeline author records **metrics**: named numbers attached to a step (for example `rejected = 42`). A metric can be set, accumulated or kept at its maximum with a one-line call, and may be called while the step is still running. Authors may optionally **declare** metrics up front with a label, a unit and a warning threshold. The monitor shows each step's metrics in its details, marks declared metrics that cross their threshold, and in History shows a trend of each declared metric across runs.

Recording a metric is always safe: it never blocks, slows down materially or breaks the pipeline, and it never stores data content, only names and numbers.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See a step's extra numbers while it runs and after (Priority: P1)

A pipeline author records `rejected = 42` inside a step. The operator opens the run, selects the step, and sees a table of that step's metrics with name and value. If the step is still running, the table shows the values recorded so far and updates on the normal refresh.

**Why this priority**: It is the core value, the extra diagnostic numbers, and works with no declaration.

**Independent Test**: Run a step that records two metrics; open the step's details while it runs and after it finishes; confirm both values are shown, current, and correct.

**Acceptance Scenarios**:

1. **Given** a step that recorded `rejected = 42`, **When** the operator opens the step's details, **Then** a metric table lists `rejected` with value `42`.
2. **Given** a running step that has recorded metrics so far, **When** the operator views it, **Then** the current values are shown and update within one refresh interval as new values arrive.
3. **Given** a step with no metrics, **When** its details open, **Then** no metric table is shown and nothing looks broken.
4. **Given** a run from a pipeline that never records metrics, **When** it is shown, **Then** it displays exactly as before.
5. **Given** a metric name or step name containing markup characters, **When** it is displayed, **Then** it is shown as plain text.

---

### User Story 2 - Choose how a number is combined (Priority: P1)

The author records the same metric many times (once per batch, per retry, per page). They choose, per call, whether the new value **replaces** the old one, is **added** to it, or is kept only if it is the **largest** so far. A call inside a running step needs no step name; it applies to the step currently running.

**Why this priority**: Without accumulation, authors would need their own counters, and the feature would be awkward to use in loops.

**Independent Test**: Record `retries` with add three times (1, 2, 3), `rows` with set twice (10 then 4), and `peak` with max (5, 9, 7); confirm the values shown are 6, 4 and 9.

**Acceptance Scenarios**:

1. **Given** three calls adding 1, 2 and 3, **When** the step is shown, **Then** the value is 6.
2. **Given** two calls setting 10 then 4, **When** shown, **Then** the value is 4.
3. **Given** three calls keeping the maximum of 5, 9 and 7, **When** shown, **Then** the value is 9.
4. **Given** a call inside a running step with no step name, **When** it is recorded, **Then** it is attached to that step.
5. **Given** a call outside any running step with no step name, **When** it is made, **Then** nothing is recorded and nothing fails.
6. **Given** several threads recording to the same metric, **When** all finish, **Then** the shown value equals the correct combination of all calls.

---

### User Story 3 - Declare a metric with a unit and a warning threshold (Priority: P2)

The author declares in the step's description that `rejected` is measured in `rows` and should warn above 100. The operator sees the label and unit in the step's details, and when the value crosses the threshold the metric is marked with a warning, visible in the step list and graph as a small badge so the operator does not need to open each step.

**Why this priority**: Thresholds turn raw numbers into attention signals, but the numbers are useful before thresholds exist.

**Independent Test**: Declare `rejected` with warn-above 100; record 150; confirm the metric is flagged in details, list and graph; record 50 in another run; confirm no flag.

**Acceptance Scenarios**:

1. **Given** a declared metric with a unit, **When** the details are shown, **Then** value and unit are displayed together (for example `42 rows`).
2. **Given** a declared metric with a warn-above threshold and a value above it, **When** the run is shown, **Then** the metric is marked as over threshold by a label or icon and not by colour alone, and the step shows a small warning badge in the list and the graph.
3. **Given** a declared metric with a warn-below threshold and a lower value, **When** shown, **Then** it is flagged the same way.
4. **Given** a value exactly equal to the threshold, **When** shown, **Then** it is not flagged.
5. **Given** a metric that was declared but never recorded in a run, **When** the details open, **Then** it is shown as "not reported", never as zero, and is not flagged.
6. **Given** a metric recorded but not declared, **When** shown, **Then** it appears with its name, no unit and no flag.
7. **Given** a metric over its threshold, **When** the run is shown, **Then** the run's status is unchanged: the flag is informational in this release.

---

### User Story 4 - Watch a metric trend across runs (Priority: P3)

On a pipeline's History page, the operator picks a declared metric and a step and sees a chart of that metric over recent runs with the typical (median) value marked, so a creeping rise in rejects is visible before it crosses the threshold.

**Why this priority**: Valuable for early warning, but it needs the first three stories and several runs of data.

**Independent Test**: With ten runs recording `rejected` with rising values, open History, choose the metric, and confirm the chart shows ten points in order, the median, and the declared threshold line.

**Acceptance Scenarios**:

1. **Given** a pipeline whose recent runs recorded a declared metric, **When** the operator picks it in History, **Then** a chart shows its value per run oldest to newest, with the median and threshold marked.
2. **Given** runs where the metric was not reported, **When** charted, **Then** those runs appear as gaps, not zeros.
3. **Given** no declared metrics for the pipeline, **When** History is shown, **Then** no metric chart control appears.
4. **Given** fewer than the minimum number of runs with the metric, **When** shown, **Then** values are charted but no median is marked.

---

### Edge Cases

- A step that retried: its metrics are those of its latest attempt; earlier attempts' values are not merged.
- A step that failed: metrics recorded before the failure are kept and shown beside the error.
- A metric recorded with an explicit step name for a step that has not started in this run: dropped without raising, with one warning (there is no attempt to attach it to).
- A metric recorded after the step finished: accepted and shown if the run's data is still available; no error.
- Non-numeric, not-a-number or infinite values are rejected without raising; the call is ignored and a warning is logged.
- Boolean values are rejected (they are not counted as numbers).
- Very large or very small numbers display in a compact readable form and are never rounded to a wrong value in the details.
- A name that is invalid (empty, too long, disallowed characters) is rejected without raising; a warning is logged once per name.
- More metrics than the per-step limit: new names beyond the limit are dropped with one warning; existing metrics keep updating.
- A metric name declared twice in one step: the pipeline description is invalid (the same rule as a duplicate step name), so tracking is off and the usual warning names the step and metric.
- Using `add` on a metric first recorded with `set` (or the reverse): the latest mode is applied to the current value; no error.
- A damaged metric record: it is skipped and counted as unreadable; the rest of the run is shown.
- The monitoring store is unreachable or the library is not set up: recording does nothing and raises nothing.
- Metrics sent for a step that is not in the declared pipeline structure are shown under that step name and do not break the display.
- The process exits right after recording: pending metric updates are delivered within the same short exit wait as events (spec 012), or dropped without failing.

## Requirements *(mandatory)*

### Functional Requirements

**Recording**

- **FR-001**: The library MUST offer a one-line call to record a metric with a name, a numeric value, an optional step name and a combination mode: replace (default), add, or keep-maximum.
- **FR-002**: A call made while a step is running and without a step name MUST apply to the running step. A call with no step name and no running step MUST do nothing and raise nothing.
- **FR-003**: Values MUST be whole or decimal numbers. Booleans, text, not-a-number and infinite values MUST be rejected without raising, with a warning logged.
- **FR-004**: Metric names MUST follow the same naming rules as step names and be limited in length; the number of metrics per step MUST be limited. Invalid names and metrics beyond the limit MUST be dropped without raising, with one warning logged per name; metrics already recorded MUST keep updating.
- **FR-005**: Recording a metric MUST do nothing and raise nothing when the library is not set up, setup failed, or the store is unreachable; at most a warning is logged.
- **FR-006**: Recording MUST NOT block the pipeline, MUST NOT add materially to run time even when called in a tight loop (repeated updates to the same metric are merged before delivery), and MUST be safe to call from several threads at once with correct combination results.
- **FR-007**: A metric recorded in a running step MUST be readable by the monitor before the step finishes.
- **FR-008**: Metrics MUST expire together with the rest of their run's data.
- **FR-009**: No data content MAY be stored in metrics: only the name, the number and the time of the last update.

**Declaration**

- **FR-010**: The step's description MUST allow an optional list of declared metrics, each with a name, an optional human label, an optional unit, and an optional warn-above and/or warn-below threshold.
- **FR-011**: Declarations MUST be published with the pipeline's self-describing structure, so the monitor knows labels, units and thresholds without any run having recorded the metric.
- **FR-012**: A declaration MUST NOT be required: undeclared metrics MUST still be recorded and shown. Recording a declared metric MUST work identically to an undeclared one.

**Monitor and display**

- **FR-013**: The monitor MUST provide each step's metrics (name, label, value, unit, over-threshold flag, last-updated time) within its run data, so clients do not recompute them.
- **FR-014**: A declared metric MUST be flagged as over threshold when its value is strictly above its warn-above or strictly below its warn-below. A declared metric not reported in the run MUST be shown as "not reported" and MUST NOT be flagged.
- **FR-015**: The step details MUST show a metric table (name or label, value with unit, flag), declared metrics first in declared order, then undeclared metrics alphabetically. While a run is in progress the table MUST refresh on the normal refresh interval without resetting scroll or selection.
- **FR-016**: The step list and the graph MUST show a small badge on any step that has at least one over-threshold metric, conveyed by a label or icon and not by colour alone, with the count of flagged metrics.
- **FR-017**: The over-threshold flag MUST be informational only: it MUST NOT change a run's status or its position in the "needs attention" group in this release. The monitor MUST expose the flag in a form that the alerting feature (roadmap item 6) can use later.
- **FR-018**: History MUST let the operator choose a step and one of its declared metrics and show that metric's value per run (oldest to newest) with the median marked when enough runs exist, the threshold shown, and not-reported runs as gaps.
- **FR-019**: The metric trend median MUST be computed over the same window and minimum run count settings as typical durations (spec 012); no new setting is introduced. Only runs that reported the metric count toward the median.
- **FR-020**: All metric names, labels and units MUST be displayed as plain text, never interpreted as markup.

**Compatibility and limits**

- **FR-021**: Runs and pipelines without metrics or declarations MUST display correctly with no errors or warnings about missing data. An older monitor MUST ignore metric data safely, and a new monitor MUST read runs from older library versions.
- **FR-022**: A damaged metric record MUST be skipped and counted as unreadable, without hiding the rest of the run.
- **FR-023**: The monitor MUST remain read-only toward metric data.
- **FR-024**: The new data format MUST be versioned so that older monitors and older libraries stay compatible.

### Key Entities

- **Metric**: A named number on a step in a run; attributes: name, value, last-updated time.
- **Metric declaration**: Optional description of a metric on a step; attributes: name, label, unit, warn-above, warn-below.
- **Threshold flag**: Whether a declared metric's current value is outside its warning limits.
- **Metric trend**: A declared metric's value per run for a step in a pipeline and environment, with median.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A metric recorded in a running step appears in that step's details within 8 seconds at the default settings (up to 1 second to write, 2 seconds of server cache, one 5-second refresh), and its final value is correct for 100% of tested set, add and keep-maximum sequences.
- **SC-002**: With 8 threads each recording 1,000 additions to one metric, the final value equals the exact total in 100% of tested runs.
- **SC-003**: A loop that records a metric 100,000 times adds no more than 5% run time compared to the same loop without it.
- **SC-004**: With the monitoring store unreachable, a pipeline that records metrics behaves identically (same results and errors) in 100% of tested cases.
- **SC-005**: For a declared threshold, 100% of tested over-threshold values (above, below, equal) are flagged or not flagged exactly as specified, and flagged steps are recognisable in the list and graph without opening them.
- **SC-006**: An operator can find a step's rejected-row count and whether it is over its limit from the run page in under 15 seconds.
- **SC-007**: Runs from the previous library version and runs with no metrics display with no error banners and unchanged layout in 100% of tested states.
- **SC-008**: In History, a metric trend over 30 runs opens in under 2 seconds.
- **SC-009**: Invalid names, invalid values and over-limit metrics never cause a pipeline error in 100% of tested cases.

## Assumptions

- Metric values are numbers only; text and boolean metrics are out of scope. Event named values (spec 012) remain separate and are not turned into metrics.
- Defaults: up to 20 metrics per step; names up to 64 characters using the same character rules as step names; a declared label up to 40 characters and unit up to 16; these limits are fixed in this release.
- Metrics are per step per run; there is no per-run (step-less) metric and no per-item metric (roadmap item 7 will add an item dimension later).
- Where metrics are stored (inside the step's record or as a separate record per step) is decided during planning (roadmap open decision 8). The requirement is only that values are readable while the step runs (FR-007) and merged to avoid many store calls (FR-006).
- Merged delivery means a value may reach the monitor a short delay after the call (about one second); this is acceptable for FR-007 and SC-001.
- The library ships as the next minor version after `0.4.0` (`0.5.0`); the monitor must work before any pipeline is upgraded.
- Thresholds are per declaration, static numbers; relative thresholds (such as "above 2× median") and notifications are out of scope (notifications are roadmap item 6).
- Only declared metrics get History trends; undeclared metrics appear in step details only.
- Run-level aggregation (for example summing a metric across steps) is out of scope.
- The over-threshold flag does not change run status; promoting it to a status or alert is left to roadmap item 6.
