# Feature Specification: Step Failure Errors

**Feature Branch**: `011-step-failure-errors`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Lỗi của step (failed + stack trace) (roadmap.md)" — roadmap item 1 in `specs/roadmap.md`.

## Clarifications

### Session 2026-10-17

- Q: Should a step's error message be stored by default (author opts out) or left out by default (author opts in)? → A: Stored by default (shortened); the author can turn it off or pass it through a cleaning function.
- Q: If a pipeline catches a step's error and carries on, should the run still be shown as Failed? → A: No. The run is Failed only if the error stopped the pipeline (the failed step is the last one reached); a handled error marks only that step as Failed.
- Q: When a step fails and the process then also stops, should the run be shown as Failed or Died? → A: Failed. The failure record takes precedence over the missing alive signal, and the error details are shown.

## Problem

When a pipeline step raises an error, nothing is recorded about it. Waypoint Monitor sees only that the step started and never finished, so:

- A step that **failed** is indistinguishable from one that is **Running**, **Stalled** or **Died**. The operator cannot tell "the code raised an error" from "the process vanished" or "the step is slow".
- The monitor has **no error information**: not what kind of error, not the message, not where in the code it happened. The operator must find the machine that ran the pipeline and read its logs.
- Until the stall or death threshold passes, a failed run keeps looking healthy.

## Proposed approach

When a step ends with an error, the pipeline records a small **failure record** for that step: error type, a shortened error message, and a shortened stack trace, plus the time the step started and failed. The pipeline's own behaviour is unchanged: the error still propagates exactly as before. Waypoint Monitor reads the failure record and shows the step and run as **Failed** at once, with the error details one click away.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See immediately which step failed and why (Priority: P1)

An operator opens Waypoint Monitor after a pipeline step raised an error. Within a few seconds of the error, the run is shown as **Failed**, naming the step that failed. Opening that step shows the error type, the error message and the stack trace, so the operator can usually diagnose the problem without opening any log.

**Why this priority**: This is the core pain: a failure must be recognisable at once, unambiguous, and explained.

**Independent Test**: Run a pipeline whose second step raises an error. Without waiting for any stall or death threshold, confirm the run and that step show as Failed, later steps show as not reached, and the step's details show the error type, message and stack trace.

**Acceptance Scenarios**:

1. **Given** a step that raises an error, **When** the operator views the run within a few seconds, **Then** the run is Failed, the step is Failed, and the page says the run stopped at that step.
2. **Given** a Failed step, **When** the operator opens its details, **Then** the error type, error message and stack trace are shown; the stack trace can be scrolled and copied.
3. **Given** a Failed run, **When** its steps are listed, **Then** steps after the failed one are shown as "Not reached", not "Waiting".
4. **Given** a Failed run, **When** the operator views the Home page, **Then** its card shows Failed and is listed first among the pipelines that need attention.
5. **Given** a Failed step, **When** the run is shown as a graph, **Then** the failed node is distinguishable by a dedicated icon and label, not by colour alone.

---

### User Story 2 - The pipeline behaves exactly as before (Priority: P1)

A pipeline author adopts the new version. The error that a step raised still reaches the caller unchanged (same type, same message, same stack), the step's return value is unaffected when it succeeds, and recording a failure never makes anything worse: if the data store is unreachable, the pipeline fails (or succeeds) exactly as it would have without monitoring.

**Why this priority**: Monitoring must never change the outcome of the pipeline it observes. This is a standing principle of Waypoint and a precondition for shipping.

**Independent Test**: Run a failing step with the monitoring store reachable and again with it unreachable; confirm the caller receives the identical original error in both cases, and that a succeeding step returns its normal value.

**Acceptance Scenarios**:

1. **Given** a step that raises an error, **When** the failure is recorded, **Then** the original error is raised to the caller unchanged, for both ordinary and asynchronous steps.
2. **Given** the data store is unreachable, **When** a step fails, **Then** the caller still receives the original error and only a warning is logged.
3. **Given** a step that raised an error, **When** the failure is recorded, **Then** the step is no longer treated as Running.

---

### User Story 3 - Keep sensitive data out of error reports (Priority: P2)

Error messages can contain data values (an email address inside a validation error, for example). The pipeline author can choose to omit error messages entirely or to pass them through a cleaning function before they are stored. Stack traces never include the values of variables.

**Why this priority**: Waypoint promises not to store data content. Failures are the one place data can leak in by accident, so the author needs control, but the core diagnosis works without it.

**Independent Test**: Configure message capture off; fail a step whose message contains a marker string; confirm the marker appears nowhere in stored or displayed data. Repeat with a cleaning function that replaces the marker.

**Acceptance Scenarios**:

1. **Given** message capture is turned off, **When** a step fails, **Then** the error type and stack trace are recorded, and no message is stored or shown.
2. **Given** a cleaning function is configured, **When** a step fails, **Then** the stored message is the cleaned text.
3. **Given** any failure, **When** the stack trace is recorded, **Then** it contains file names, line numbers and function names only, never variable values.
4. **Given** a very long message or stack trace, **When** it is recorded, **Then** it is shortened to a fixed maximum, keeping the most recent stack frames.

---

### User Story 4 - Failed runs stand out in History (Priority: P2)

An operator reviews a pipeline's History. Failed runs are marked as Failed, can be filtered together with other problem states, and the Failed count is reflected in the trend view where the trend shows run outcomes.

**Why this priority**: Spotting a pattern of repeated failures builds on the core view but is not needed to diagnose a single failure.

**Independent Test**: With a pipeline that has completed, failed and died runs in its history, confirm each failed run is labelled Failed, and the failure filter lists exactly those runs.

**Acceptance Scenarios**:

1. **Given** a pipeline with failed runs in its History, **When** the operator views it, **Then** each failed run is labelled Failed.
2. **Given** the History filter, **When** the operator filters by Failed, **Then** only Failed runs are listed.

---

### User Story 5 - Older pipelines keep working (Priority: P1)

Pipelines still using the previous version of the pipeline library send no failure records. Waypoint Monitor shows them exactly as it does today (Running / Stalled / Died / Incomplete, and so on) and does not report errors or warnings about the missing failure information.

**Why this priority**: Pipelines are upgraded one by one; the monitor must not break or mislead for those not yet upgraded.

**Independent Test**: View a run produced by the previous library version, in the states it can produce today, and confirm the display is unchanged.

**Acceptance Scenarios**:

1. **Given** a run with no failure records, **When** the operator views it, **Then** its status and details are the same as before this feature.
2. **Given** a damaged failure record, **When** the monitor reads the run, **Then** the record is ignored and counted as unreadable, the way other damaged records already are, and the rest of the run is still displayed.

---

### Edge Cases

- A pipeline catches a step's error and carries on to later steps: the step stays shown as Failed, but the run keeps its normal status (see FR-007).
- A later retry of the same step succeeds: the earlier failure is replaced and no longer shown as Failed.
- A step fails and the process then dies before finishing: the run must show Failed, not Died (the failure is the more specific explanation).
- A step that raises an error whose message is empty, or an error with chained causes: the type and trace are still shown; chained causes appear in the trace.
- An error raised by a step with no later steps: the run is Failed, and no "not reached" steps are listed.
- A failure record arrives for a step not in the declared pipeline structure: it is shown as a failed step; it does not break the display.
- The same step is recorded as failed more than once (for example a retry that fails again): the latest failure is shown.
- A step fails at the same moment the run's alive signal stops: Failed takes precedence over Died.

## Requirements *(mandatory)*

### Functional Requirements

**Recording failures**

- **FR-001**: When a step ends with an error, the system MUST record a failure for that step containing: the run it belongs to, the step name and position, the time the step started, the time it failed, the error type, a shortened error message, and a shortened stack trace.
- **FR-002**: The system MUST NOT change the outcome of the monitored step: the original error MUST be raised unchanged, and a successful step's result MUST be unchanged, for both ordinary and asynchronous steps.
- **FR-003**: A failure to record (for example, the data store being unreachable) MUST never alter or hide the step's own error and MUST only produce a logged warning.
- **FR-004**: A step that has recorded a failure MUST NOT be treated as running.
- **FR-005**: Error messages MUST be shortened to at most 500 characters, and stack traces to at most 8 KB, keeping the most recent frames when shortening.
- **FR-006**: Stack traces MUST NOT contain the values of local variables.
- **FR-006a**: Error messages MUST be stored by default (shortened per FR-005). The pipeline author MUST be able to turn off storing error messages, and to supply a cleaning function applied to the message before it is stored. When messages are off, the error type and stack trace are still recorded.

**Displaying failures**

- **FR-007**: The monitor MUST show a step as **Failed** when it has a failure record that has not been superseded by a later successful completion of the same step in the same run. The run MUST be shown as **Failed** only when the failure stopped the pipeline, meaning the failed step is the last step reached. When a pipeline continues past a failed step, that step is still shown as Failed but the run keeps the status it would otherwise have.
- **FR-008**: The run-status priority MUST be: Running, Failed, Died, Stale, Incomplete, Lost data, Completed. A run stopped by a failed step MUST NOT be shown as Died, Stalled or Running because of that step.
- **FR-009**: Steps after a Failed step MUST be shown as "Not reached", and the run MUST state which step it stopped at.
- **FR-010**: The monitor's run and overview data MUST include the error details of each failed step.
- **FR-011**: The Home page card for a Failed run MUST show the Failed state and MUST rank above all other states in the "needs attention" group.
- **FR-012**: A Failed step MUST be marked in the graph with its own icon and label, so that the state is not conveyed by colour alone.
- **FR-013**: The step details view MUST show the error type, message (when stored) and stack trace; the stack trace MUST be scrollable and copyable.
- **FR-014**: History MUST label Failed runs and include Failed in its problem-state filter, and MUST include Failed in any trend that reports outcomes.

**Compatibility and limits**

- **FR-015**: Runs from pipelines that send no failure records MUST be displayed exactly as before this feature.
- **FR-016**: A damaged failure record MUST be skipped and counted as unreadable, and MUST NOT prevent the rest of the run from being displayed.
- **FR-017**: Failure records MUST expire together with the rest of their run's data.
- **FR-018**: The monitor MUST remain read-only toward failure data: it MUST NOT create or modify failure records.
- **FR-019**: No data content may be stored beyond names, counts, times and the shortened diagnostic text defined above.

### Key Entities

- **Step failure**: The record that one step of one run ended with an error. Attributes: run, step name and position, start time, failure time, error type, shortened message (optional), shortened stack trace.
- **Step state (extended)**: The existing step states plus **Failed**.
- **Run state (extended)**: The existing run states plus **Failed**, with the priority order in FR-008.
- **Error details**: The error type, message and stack trace shown to the operator for a failed step.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a step raises an error, the operator sees the run and step as Failed, with error details, within 10 seconds of the error, without waiting for any stall or death threshold.
- **SC-002**: In a test with 20 intentionally failed steps, 100% are shown as Failed (none as Running, Stalled or Died) and each shows its error type.
- **SC-003**: A failed step's caller receives an identical error (type, message, stack) with and without monitoring, and identical behaviour when the data store is unreachable, in 100% of tested cases.
- **SC-004**: With message capture turned off, a marker string placed in the error message appears in 0% of stored or displayed data; no stack trace contains a variable value.
- **SC-005**: Recorded failure data never exceeds the stated limits (500-character message, 8 KB stack trace) for any error, however large.
- **SC-006**: Runs from pipelines using the previous library version display identically to before in 100% of tested states.
- **SC-007**: An operator can name the failed step and the error type from the Home page and run page alone, without opening any log, in under 30 seconds.

## Assumptions

- Run-state priority follows the roadmap proposal (Running, Failed, Died, Stale, Incomplete, Lost data, Completed). "Running" stays highest so a currently active retry is not hidden by an earlier failure.
- A run counts as Failed only when the failure stopped the pipeline; a failure later superseded by a successful retry of the same step is no longer shown, and a handled error that lets the pipeline continue marks only the step as Failed.
- By default the error message **is** stored (shortened); turning it off or cleaning it is opt-in by the pipeline author. This favours diagnosis, and the author controls the data-leak risk.
- The graph, list, Home and History views already exist; this feature extends them and adds a step details view section for errors.
- Timing figures (such as duration) are covered by the later "duration" roadmap item; this feature only records the step's start and failure times.
- Parallel / fan-out steps are out of scope; steps are sequential, as today.
- Sending notifications about failures is out of scope (roadmap item 6).
- The monitor and the pipeline library are released independently; the monitor must work before any pipeline is upgraded.
