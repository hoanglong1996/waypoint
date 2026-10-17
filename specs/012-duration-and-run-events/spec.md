# Feature Specification: Run Duration and Run Events

**Feature Branch**: `012-duration-and-run-events`

**Created**: 2026-10-17

**Status**: Done - released in waypoint-etl 0.4.0 (monitor first)

**Input**: User description: "let's implement #2 and #3 in this spec" — roadmap items 2 (Duration) and 3 (Run log/events) in `specs/roadmap.md`.

## Clarifications

### Session 2026-10-17

- Q: Should event messages get the same privacy controls as error messages? → A: Yes. The same setting and cleaning function apply to error messages and event messages: one switch turns off or cleans all free text the library stores.
- Q: When the per-run event limit is reached, can automatic events be dropped? → A: No. Automatic events (run started, step started/finished/failed) are always kept and do not count toward the limit; the limit applies only to author-sent events, dropping info before warning and error.
- Q: Should single steps also be flagged Slower than usual? → A: No. Only whole runs are flagged; steps show their duration and the bottleneck highlight.

## Problem

Waypoint Monitor now says *which step failed and why*. Two questions are still unanswered:

- **How long did it take?** Start and finish times are recorded, but the operator sees no duration for a step or a run, cannot tell which step is the bottleneck, and cannot notice that a run is far slower than usual until it times out or stalls.
- **What did the run do?** The operator sees counts per step, but not the order of things that happened, nor anything the pipeline wanted to say along the way ("loaded batch 3", "skipped 12 rows"). To find out, they must open the log on the machine that ran the pipeline.

## Proposed approach

**Duration** is computed from information already recorded, so every completed run, including runs from the previous library version, gets a duration. The monitor shows durations per step and per run, builds a typical (median and slow-end) duration per pipeline and environment from recent runs, and flags runs that are much slower than typical.

**Events** are short messages attached to a run. The pipeline author sends their own with a one-line call. The monitor builds one time-ordered **timeline** per run from those events plus automatic ones it derives (run started, step started/finished/failed, run died, run stalled), and shows it on the run page, in a step's details, and as warning/error counts on cards and History rows. Automatic events are derived by the monitor from records that already exist, so only author-sent events need new data. The two features ship together because the timeline also shows each step's timing, and a failure is simply an `error` event.

Sending an event is always safe: it never blocks, slows down materially, or breaks the pipeline, and it never stores data content.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See how long each step and run took (Priority: P1)

An operator opens a finished run and sees the total duration in the headline and a duration next to each step. A running step shows how long it has been running so far, and the run's duration keeps counting while it runs. The step that took most of the time is highlighted as the bottleneck.

**Why this priority**: It is the simplest, most requested answer, and it works for all existing runs with no pipeline change.

**Independent Test**: View a completed run produced by the previous library version; confirm the run and each step show a correct duration and the slowest step is highlighted. View a running run and confirm the open step shows an elapsed time that increases.

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the operator opens it, **Then** the total duration and every finished step's duration are shown in a readable form (for example `1h 04m`, `37s`).
2. **Given** a run in progress, **When** the operator views it, **Then** the running step and the run show elapsed time to now, marked as still running.
3. **Given** a run whose steps take different times, **When** it is shown, **Then** the step with the largest share of the total is highlighted as the bottleneck, in the list and in the graph, and the highlight is not conveyed by colour alone.
4. **Given** a Failed step, **When** the run is shown, **Then** its duration is the time from start until the failure.
5. **Given** the Home page, **When** a pipeline card is shown, **Then** it shows the duration of that pipeline's latest run.

---

### User Story 2 - Notice a run that is slower than usual (Priority: P1)

An operator looks at a pipeline's History. Next to the run list, a chart shows durations over time, with the typical duration and the slow end marked. Runs that took much longer than typical are flagged **Slower than usual**, so a creeping slowdown is visible before it becomes an outage.

**Why this priority**: Spotting slowness early is the main reason to track duration at all.

**Independent Test**: With a pipeline whose recent runs take about 10 minutes, add one that took 35 minutes; confirm it is flagged, the others are not, and the typical and slow-end values are shown.

**Acceptance Scenarios**:

1. **Given** enough recent completed runs of a pipeline in an environment, **When** the operator opens History, **Then** the typical (median) and slow-end (95th percentile) durations for that pipeline and environment are shown.
2. **Given** a run whose duration exceeds the slow threshold (a multiple of the typical duration, 2× by default), **When** it is listed or opened, **Then** it is labelled **Slower than usual** with its duration and the typical duration.
3. **Given** History, **When** it is shown, **Then** each run row has a Duration column and a duration-over-time chart sits next to the existing trend chart.
4. **Given** too few completed runs to define "typical", **When** History is shown, **Then** no run is flagged and the page says there is not yet enough history.
5. **Given** a run still in progress that has already exceeded the slow threshold, **When** it is shown, **Then** it is flagged Slower than usual while it is still running.

---

### User Story 3 - Read what a run did, as a timeline (Priority: P1)

An operator opens a run and chooses the **Events** tab. It lists, in time order, what happened: run started, each step started and finished (with its duration and counts), any step failure (as an error), and a final line saying how the run ended. The operator can filter by level (info, warning, error) and by step, and a running run keeps adding new events without a manual reload.

**Why this priority**: This answers "what happened in this run, in what order" without opening any machine's log. It works from automatic events alone, with no change to pipeline code.

**Independent Test**: Run a three-step pipeline whose second step fails. Without adding any custom event, open the Events tab and confirm it shows run start, step 1 start/finish, step 2 start, step 2 error with the error type and message, and the stopped-at outcome, in order.

**Acceptance Scenarios**:

1. **Given** any run, **When** the operator opens Events, **Then** events are shown oldest to newest, each with time, level, step (if any) and message, coloured by level and with a text/icon cue for level.
2. **Given** a Failed step, **When** the timeline is shown, **Then** it contains an `error` event for that step with the error type and shortened message, and a link to the step's details.
3. **Given** a run that Died or Stalled, **When** the timeline is shown, **Then** the monitor adds an event saying so, marked as inferred by the monitor, not sent by the pipeline.
4. **Given** the level and step filters, **When** the operator applies them, **Then** only matching events are listed, and the filtered count is shown.
5. **Given** a run in progress, **When** new events arrive, **Then** they appear within the normal refresh interval, without losing the operator's filters or scroll position.
6. **Given** a run with many events, **When** the timeline is opened, **Then** events load in pages and the operator can load older/newer ones.

---

### User Story 4 - Send my own events from a pipeline (Priority: P1)

A pipeline author adds one-line calls in their code, such as logging "Loaded batch 3" with a level, an optional step and a few small named values (such as a row count). These show up in the run's timeline in the right place. A call made outside a running pipeline, before setup, or when the monitoring store is down does nothing and raises nothing.

**Why this priority**: Automatic events say *that* things happened; custom events say *what* happened inside a step, which is what an operator needs when a step is slow or odd but not failed.

**Independent Test**: Call the event function from inside a step, from outside any step, before setup, and with the store unreachable; confirm the first appears in the timeline attached to that step and the others do nothing and raise nothing.

**Acceptance Scenarios**:

1. **Given** a running pipeline, **When** the author sends an event with a message, **Then** it appears in the run's timeline with the time it was sent.
2. **Given** an event sent inside a running step with no step named, **When** it is shown, **Then** it is attached to that step.
3. **Given** the author sends warning- and error-level events, **When** the run is shown, **Then** they are counted and visible as such (US5).
4. **Given** the library is not set up, setup failed, or the store is unreachable, **When** the author sends an event, **Then** nothing is raised, the step's behaviour is unchanged, and at most a warning is logged.
5. **Given** several threads send events at once, **When** the run is shown, **Then** no event is lost or corrupted.
6. **Given** a message or named values that are too long or too many, **When** the event is recorded, **Then** they are shortened or dropped to fixed limits and values that are not numbers or short text are not stored.
7. **Given** message capture is turned off, **When** the author sends an event whose message contains a marker string, **Then** the marker appears nowhere in stored or displayed data, and the event still appears with its level, step and time.
8. **Given** a cleaning function is configured, **When** an event or a step failure is recorded, **Then** the stored message is the cleaned text in both cases.

---

### User Story 5 - Warnings and errors visible without opening a run (Priority: P2)

Home cards and History rows show the number of warning and error events for the latest/each run. Opening a step in the graph shows only that step's events in its details.

**Why this priority**: Adds triage value on top of the timeline but the timeline is useful without it.

**Independent Test**: Run a pipeline that emits two warnings and one error; confirm the card and History row show 2 warnings and 1 error, and the step's details list only that step's events.

**Acceptance Scenarios**:

1. **Given** a run with warning or error events, **When** its Home card or History row is shown, **Then** the counts are shown, and nothing is shown for runs with none.
2. **Given** a step with events, **When** the operator opens its details, **Then** the step's events are listed there, with a link to the full timeline filtered to that step.

---

### User Story 6 - Pipelines never get slower or break because of events (Priority: P1)

The author's pipeline must stay fast and safe even if it sends thousands of events. The number and size of events kept per run is capped; when the cap is reached the oldest routine (info) events are dropped first and warnings and errors are kept. Events expire with the rest of the run's data.

**Why this priority**: Monitoring must never change the outcome of what it observes, and storage must not grow without limit. This is a standing Waypoint principle.

**Independent Test**: Send 5,000 info events and a few errors in one run; confirm the stored events stay within the cap, all errors are kept, the step does not wait on the store, and the run still completes normally.

**Acceptance Scenarios**:

1. **Given** a run that sends more author events than the per-run cap, **When** the run is shown, **Then** the timeline has at most the cap of author events, with the oldest info events dropped first, every automatic event still present, and a note that some events were dropped.
2. **Given** the monitoring store is slow or unreachable, **When** events are sent, **Then** the step is not delayed beyond a small fixed bound and its result and errors are unchanged.
3. **Given** a run's data expires, **When** its events are looked up, **Then** they are gone with it.

---

### User Story 7 - Older pipelines and monitors keep working (Priority: P1)

Runs from the previous library version have no events and no recorded durations beyond start/finish times. The monitor shows durations for them, builds their timeline from the information it has (run and step start/finish, failure), and shows no errors about missing events. An older monitor ignores the new data without breaking.

**Why this priority**: Pipelines are upgraded one by one; neither side may break or mislead the other.

**Independent Test**: View a run produced by the previous library version: durations are correct, the Events tab shows the derived timeline, and nothing reports missing data.

**Acceptance Scenarios**:

1. **Given** a run with no recorded events, **When** the operator opens Events, **Then** a timeline derived from step and run records is shown and a note says custom events are available only for upgraded pipelines.
2. **Given** a damaged event record, **When** the monitor reads the run, **Then** it is skipped and counted as unreadable, the rest of the timeline is shown.
3. **Given** a run whose timestamps are missing or inconsistent (a finish earlier than its start), **When** it is shown, **Then** that duration is omitted or shown as unavailable instead of negative or wrong.

---

### Edge Cases

- A step that retried: the step shows the duration of its latest attempt, and the timeline shows the latest attempt of each step (earlier attempts that left no record of their own are not listed).
- A run that Died or Stalled: its duration runs from the first step start to the last known activity, labelled as incomplete, not counted toward typical durations.
- Failed, Died and Incomplete runs are excluded from the typical-duration calculation, so one fast crash does not lower "typical".
- Clocks differ between the pipeline machine and the monitor: durations between two pipeline timestamps are unaffected; elapsed time for a running step uses the monitor's clock and states that small clock offsets can show.
- A run with a single step, or an instant step: duration shows `<1s` rather than `0s`.
- A step name or event message containing markup characters is displayed as plain text, never interpreted.
- Events with identical timestamps keep a stable order (the order they were sent).
- A pipeline with a very long step list or many events: the timeline pages instead of loading everything at once.
- Events sent for a step that is not in the declared pipeline structure are shown with that step name and do not break the display.
- Very long runs (days): durations show days and hours (`2d 03h`).

## Requirements *(mandatory)*

### Functional Requirements

**Duration**

- **FR-001**: The monitor MUST compute and show a duration for each finished step, each failed step (start to failure) and each run (first step start to last step end, or to now while running), including runs from the previous library version. A run's duration is measured from the run's own start (so it includes any time before its first step) to its last activity. For a step of a run from a library version that did not record the step's start time, the duration MUST be derived from the previous step's end (or the run's start for the first step) and shown as approximate (for example `≈2m 10s`); pipelines on the new library version record exact step durations.
- **FR-002**: For a running step and a running run, the monitor MUST show elapsed time to now, visibly marked as still running.
- **FR-003**: Durations MUST be shown in a readable form (seconds, minutes, hours, days) and as unavailable when the underlying times are missing or inconsistent; a negative or nonsensical duration MUST never be shown.
- **FR-004**: The run page MUST show total duration in the headline, a duration beside each step in the list, and a duration label on each graph node.
- **FR-005**: The step with the largest share of a run's duration MUST be highlighted as the bottleneck in list and graph, by a label or icon and not by colour alone; no highlight when there is only one step.
- **FR-006**: The Home card MUST show the duration of the pipeline's latest run.
- **FR-007**: The monitor's run data MUST include the duration of each step and run so clients do not recompute it.

**Typical duration and slow runs**

- **FR-008**: For each pipeline and environment, the monitor MUST compute the median and 95th-percentile duration over a window of the most recent completed runs.
- **FR-009**: Only runs that finished (status Completed, including Completed with Lost data) MUST count toward typical durations; Failed, Died, Stalled, Incomplete and running runs MUST NOT.
- **FR-010**: A run MUST be flagged **Slower than usual** when its duration exceeds a configurable multiple of the median (default 2×), including a run still in progress that has already exceeded it. No flag MUST be shown when there are fewer than a minimum number of completed runs (default 5).
- **FR-011**: The window size, the slow multiple and the minimum run count MUST be configurable on the monitor with the defaults above; a per-pipeline override is out of scope.
- **FR-012**: History MUST show a Duration column, a duration-over-time chart beside the existing trend, the typical and slow-end values, and the Slower than usual label on flagged runs.
- **FR-013**: The Slower than usual flag is a visible indicator only; it MUST NOT change the run's status or its position in the "needs attention" group. The flag applies to runs only; individual steps are never flagged, and typical durations are computed per run, not per step.

**Events: recording**

- **FR-014**: The timeline MUST include events for run started, step started, step finished and step failed with no change to the author's code. These automatic events are derived by the monitor from the run and step records the library already writes, so they exist identically for runs from every library version and are never stored as separate events.
- **FR-015**: The library MUST offer a one-line way to send an event with a message, a level (info, warning, error), an optional step name and a few small named values. Convenience shortcuts for warning and error levels MUST exist.
- **FR-016**: An event sent while a step is running and without a step name MUST be attached to the running step.
- **FR-017**: Sending an event MUST do nothing and raise nothing when the library is not set up, setup failed, or the store is unreachable; at most a warning is logged.
- **FR-018**: Sending an event MUST NOT block the pipeline (it never waits on the network; at process exit the final delivery waits at most 2 seconds) and MUST be safe to call from several threads at once.
- **FR-019**: Named values MUST accept only numbers and short text; the number of values, text length and message length MUST be limited and excess shortened or dropped.
- **FR-020**: Author-sent events MUST be capped per run. Automatic events (FR-014) MUST always be kept and MUST NOT count toward the cap. When the cap is exceeded, the oldest author-sent info events MUST be dropped first and warning and error events kept; the run MUST record that events were dropped.
- **FR-021**: Events MUST expire together with the rest of their run's data.
- **FR-022**: No data content MAY be stored in events beyond names, numbers, times and the short author-written text defined above. The author MUST be able to turn off storing event message text, and to supply a cleaning function applied to it before it is stored, using the same setting and the same cleaning function that already apply to error messages (spec 011); one setting covers both. When message text is off, level, step, time and named values are still recorded. The documentation MUST still tell authors to keep data values out of event text.

**Events: displaying**

- **FR-023**: The monitor MUST provide the events of a run, with filtering by level and by step and with paging, and MUST merge recorded events and events derived from run and step records into one time-ordered timeline with a stable order for equal times.
- **FR-024**: The monitor MUST add derived events when a run is judged Died or Stalled, clearly marked as inferred.
- **FR-025**: A step failure MUST appear in the timeline as an `error` event with the error type and shortened message and a link to the step's details.
- **FR-026**: The run page MUST have an **Events** tab showing the timeline with level colours plus a text or icon cue, level and step filters, and the filtered count.
- **FR-027**: The step details MUST show that step's events with a link to the timeline filtered to that step.
- **FR-028**: While a run is in progress, the timeline MUST pick up new events on the normal refresh interval without resetting filters or scroll position.
- **FR-029**: The Home card and History rows MUST show warning and error counts for the run, and nothing when both are zero. The counts cover events the pipeline sent; a step failure is already shown by the Failed status and is not counted again.
- **FR-030**: The timeline MUST show a note when events were dropped, and when a run has no recorded events (older pipelines), a note that custom events need the upgraded library.

**Compatibility and limits**

- **FR-031**: Runs from pipelines without events or durations MUST display correctly: durations from existing times, timeline derived from existing records, no errors or warnings about missing data.
- **FR-032**: A damaged event record MUST be skipped and counted as unreadable, without hiding the rest of the run.
- **FR-033**: The monitor MUST remain read-only toward event data, apart from the verdict records it already writes.
- **FR-034**: All text from events and steps MUST be displayed as plain text, never interpreted as markup.
- **FR-035**: The new data format MUST be versioned so that an older monitor ignores it safely and an older library's data stays readable.

### Key Entities

- **Duration**: How long a step or run took or has taken so far; attributes: start, end (or still running), value, whether it is complete.
- **Typical duration**: Median and 95th-percentile duration for a pipeline and environment over recent completed runs; attributes: window, sample size, slow threshold.
- **Run event**: One entry in a run's timeline; attributes: time, level, optional step, message, optional small named values, source (library, author, or monitor-inferred).
- **Timeline**: The merged, time-ordered list of a run's events with paging and filters.
- **Event cap**: The per-run limit on stored events and the dropped-events note.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of completed runs, including those from the previous library version, the run shows a correct duration; every finished step shows its exact duration when the pipeline uses the new library version and an approximate one (marked as such) when it does not.
- **SC-002**: An operator can name the slowest step of a run and its duration from the run page alone in under 15 seconds.
- **SC-003**: In a test set of runs with one deliberately slow run (more than 2× typical), that run is flagged and no other run is flagged.
- **SC-004**: For a run in progress, the elapsed time and the timeline update within one refresh interval (5 seconds by default) of a new event or step change.
- **SC-005**: Without any change to pipeline code, the Events tab of a failed run lets an operator state what ran, in what order, and where it stopped, in under 30 seconds.
- **SC-006**: A pipeline sending 5,000 events in one run completes with no more than 5% added run time compared to sending none, and stored author events never exceed the per-run cap, with 100% of warning, error and automatic events kept when the cap is hit.
- **SC-007**: With the monitoring store unreachable, a pipeline that sends events behaves identically (same results and errors) in 100% of tested cases.
- **SC-008**: Runs from the previous library version display with correct durations and a derived timeline and with no error banners, in 100% of tested states.
- **SC-009**: A timeline of 500 events opens and shows its first page in under 2 seconds.
- **SC-010**: With message capture turned off, a marker string placed in an event message or an error message appears in 0% of stored or displayed data.

## Assumptions

- Run duration needs no new information (the run id carries its start time). A step's own start time is recorded only briefly (a start marker that expires after 24 hours) and in failure records (spec 011), not in finish records, so the new library version also writes the step's start time and duration in the finish record; older runs get approximate step durations derived from the previous step's end.
- "Typical" uses the median; "slow end" the 95th percentile; the default window is the last 30 completed runs per pipeline and environment, the minimum is 5 runs, and the slow multiple is 2×. These are global settings; a per-pipeline threshold can be added later.
- The per-run cap on author-sent events is 500 info events, plus up to 200 warning and 200 error events kept separately (the oldest of a level is dropped first), the message limit to 300 characters, named values to at most 10 per event with text up to 100 characters. Limits are fixed in this release.
- The event channel is part of the library's normal connection to the monitoring store; how events are stored and read is a planning decision. If it requires additional read permission for the monitor, the Security section of the documentation is updated.
- The library ships a new minor version for events (`0.4.0`); duration is delivered by the monitor alone and works with `0.2.0` and `0.3.0` runs.
- Custom events are sequential-step only; parallel / fan-out steps (roadmap item 7) are out of scope.
- Event levels are info, warning and error only; there is no debug level.
- Per-step typical durations and step-level Slower than usual flags are out of scope (the bottleneck highlight covers step-level attention).
- Notifications and SLA ("late", "max duration") are out of scope (roadmap items 4 and 6); the Slower than usual flag is display only.
- Custom metrics (roadmap item 5) are out of scope, though event named values are numbers/short text that can be reused later.
- The monitor and the library are released independently; the monitor must work before any pipeline is upgraded.
