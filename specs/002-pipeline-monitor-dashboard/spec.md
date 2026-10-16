# Feature Specification: Pipeline Monitor Dashboard

**Feature Branch**: `002-pipeline-monitor-dashboard`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "now we have redis store all data related to all steps in my pipeline, now I want to build a simple web application to view/monitor the data with beautiful UI"

## Clarifications

### Session 2026-10-15

- Q: Where should the web app live in the repository? → A: In a new `performance_monitoring_app` folder, separate from the existing pipeline code.
- Q: Which visual design should the app follow? → A: The approved prototype in `docs/design/pipeline-monitor-degisn` (notes in `DESIGN_NOTES.md`, screenshots in `screenshots/`); where this spec and the prototype differ, this spec has been aligned to the prototype.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the health of the latest run at a glance (Priority: P1)

An operator opens the dashboard and immediately sees the most recent pipeline run for the chosen environment (prod or qa): when it ran, how long ago, how long it took, whether it looks complete, three headline numbers (accounts, calls, saved statistics) with their change versus the previous run, a one-line map of all steps showing which are fine, lost data or are missing, and each step in order with its input counts and output count (for example "Read accounts: in none, out 10").

**Why this priority**: This replaces running Redis commands by hand and answers the daily question "did last night's job work and where did data drop?"

**Independent Test**: With stored records for one run, open the dashboard and confirm all steps appear in pipeline order with the same counts as the stored records, and that the run's status is shown.

**Acceptance Scenarios**:

1. **Given** a complete run exists, **When** the operator opens the dashboard, **Then** the latest run is shown with run time, "time since run", overall status, and every step with its input and output counts.
2. **Given** a run is missing some of the expected steps (the job stopped part-way), **When** it is displayed, **Then** it is marked incomplete and the first missing step is highlighted.
3. **Given** a step has input items but zero output items, **When** it is displayed, **Then** it is visually flagged as a possible data loss.
4. **Given** the environment selector, **When** the operator switches between prod and qa, **Then** the view shows that environment's latest run.
5. **Given** a run, **When** it is displayed, **Then** a single sentence states whether it worked (for example "Last night's run completed", "Run stopped before the end", "Run finished, but one step lost data") and names the first missing or data-losing step.
6. **Given** a step that returns nothing (no output count), **When** it is displayed, **Then** it shows "n/a" with "returns nothing", and its recent-trend line uses its input count instead.

---

### User Story 2 - Browse run history and compare runs (Priority: P2)

The operator can list past runs (the most recent 30, within the 30-day retention), open any of them in a detail panel, and see how a step's counts changed from run to run, for example a trend of calls read per run.

**Why this priority**: Spotting a gradual drop or a sudden spike needs history, but the latest-run view already delivers value on its own.

**Independent Test**: With several stored runs, open the history, pick an older run and see its steps; view the trend for one step and confirm it matches the stored counts.

**Acceptance Scenarios**:

1. **Given** multiple runs, **When** the operator opens history, **Then** runs are listed newest first with date, status and headline counts.
2. **Given** a run in the list, **When** the operator selects it, **Then** its step details are shown as in User Story 1.
3. **Given** a step, **When** the operator views its trend, **Then** a chart shows its count per run over the last 30 runs, with a value and change versus the run before when hovering or keyboard-focusing a point.
4. **Given** a run whose count differs from the previous run, **When** shown, **Then** the change is visible as a percentage up or down ("new" when the previous value was zero, nothing when either value is missing).
5. **Given** the detail panel is open, **When** the operator presses Escape, clicks outside it or uses its close control, **Then** it closes and focus returns to the run that opened it.

---

### User Story 3 - Stay current and handle problems gracefully (Priority: P3)

The page refreshes itself periodically so it can stay open on a screen, and always shows when it was last updated. It warns when the latest run is older than expected, and shows a clear message (not a broken page) when no data exists, when some records could not be read, or when the data store cannot be reached.

**Why this priority**: Makes it usable as a monitor rather than a one-off viewer.

**Independent Test**: Leave the page open while a new run is stored and see it appear without manual reload; stop the data store and see a clear "unavailable" message.

**Acceptance Scenarios**:

1. **Given** the page is open, **When** a new run is stored, **Then** the page shows it within the refresh interval without user action.
2. **Given** the latest run is older than the expected window, **When** the page loads, **Then** a prominent "stale" warning is shown.
3. **Given** no runs exist for the environment, **When** the page loads, **Then** a friendly empty state explains there is no data yet.
4. **Given** the data store is unreachable, **When** the page loads or a refresh fails, **Then** an error message replaces all numbers (no old data is shown as current), a "Retry now" control is offered, and the page retries automatically.
5. **Given** some records of a run could not be read, **When** the page loads, **Then** a notice shows how many, and the affected run is marked in History.

### Edge Cases

- A stored record is malformed or has missing fields: skip it, show the rest, and note that some data could not be read.
- A step produced "nothing" (no output count): shown as "n/a", not zero.
- An environment with only one run: trend and comparisons still render, with no change shown.
- A step missing from a run leaves a gap in trend lines rather than a zero; a zero caused by data loss is drawn as a distinct red point.
- A record that is present but unreadable counts as that step not reporting, and is included in the unreadable count.
- Runs expire after 30 days: older runs simply disappear; history never promises more.
- Narrow screens (phone/tablet): layout stays readable.
- The dashboard is read-only: it can never modify or delete stored records.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST show, for the selected environment, the latest pipeline run with its start time, time since it finished, duration, and overall status (complete or incomplete), plus a separate stale warning when applicable.
- **FR-002**: For each step of a run, the dashboard MUST show step name, named input counts, output count and finish time, in pipeline order.
- **FR-003**: The dashboard MUST flag a step whose input count is greater than zero but whose output count is zero.
- **FR-004**: A run missing any of the expected pipeline steps MUST be marked incomplete, with the first missing step identified.
- **FR-005**: The user MUST be able to switch between environments (prod, qa).
- **FR-006**: The dashboard MUST list the most recent runs (up to 30) newest first, with date, status, headline counts and problem flags, and allow opening any run's details.
- **FR-007**: The dashboard MUST show a recent-trend line for each step in the latest-run view (last 14 runs), a trend chart for a chosen step in History (last 30 runs), and the percentage change versus the previous run for headline numbers and chart points. A step's value is its output count, or its input count when the step returns nothing.
- **FR-008**: The dashboard MUST refresh its data automatically at a configurable interval (default 60 seconds) without losing the user's current tab, environment, run or step selection, and MUST show how long ago it was last updated.
- **FR-009**: The dashboard MUST show a stale warning when the latest run finished longer ago than a configurable expected window (default 26 hours).
- **FR-010**: The dashboard MUST show clear empty-state and data-unavailable messages instead of errors or blank pages; the data-unavailable message MUST replace all numbers, offer a "Retry now" control and retry automatically (every 30 seconds).
- **FR-011**: The dashboard MUST be read-only and MUST display only the counts and metadata already stored; no caller PII is available to it.
- **FR-012**: The dashboard MUST follow the approved design in `docs/design/pipeline-monitor-degisn`, support light and dark appearance (following the system setting until the user chooses, and remembering the choice), and be usable from 375 px to wide desktop widths with no horizontal scrolling.
- **FR-013**: Malformed records MUST be skipped without breaking the page, with a visible notice of how many could not be read and a marker on each affected run in History.
- **FR-014**: The latest-run view MUST show three headline numbers (accounts read, calls read, statistics saved) with the change versus the previous run, and a step map of all steps marked fine, possible data loss, or not reported.
- **FR-015**: Status MUST never be conveyed by colour alone (icon and text as well), all interactive elements MUST be keyboard operable with visible focus, and animations MUST be disabled when the user prefers reduced motion.

### Key Entities

- **Environment**: A deployment target (prod or qa) whose runs are viewed.
- **Pipeline Run**: One execution, with run time, environment, overall status and an ordered set of step records.
- **Step Record**: Step name, input counts by name, output count (or none), finish time (defined by the Pipeline Step Audit Trail feature).
- **Trend Point**: A step's value (output, or input for steps that return nothing) for a given run, used to draw trends and compute change.
- **Step Group**: A named section of the pipeline (CallRail, Google Ads, Merge, Persist) used to organise the step map and list.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can tell whether the latest run completed and where data dropped within 10 seconds of opening the dashboard.
- **SC-002**: The latest-run view is fully displayed within 3 seconds for a month of retained runs.
- **SC-003**: 100% of displayed counts match the stored records exactly.
- **SC-004**: A new run appears on an open page within one refresh interval (default 60 seconds) with no manual reload.
- **SC-005**: An operator can find any run from the last 30 days and open its details in under 30 seconds.
- **SC-006**: With the data store down, 100% of page loads show an explanatory message rather than a blank or broken page.
- **SC-007**: In a review with 3 operators, at least 90% rate the interface as clear and visually appealing, and the key views are usable at a 375px-wide screen.

## Assumptions

- The data is the step records created by feature 001 (counts only, 30-day retention, one set of records per run per environment); this feature depends on it.
- Users are internal operators; the dashboard is deployed on an internal network and v1 has no login. If it will be exposed beyond the internal network, access control must be added first.
- The expected pipeline steps are the nine defined in feature 001's data model; the step list is maintained alongside the pipeline.
- The pipeline runs about once a day, hence the default 26-hour stale window; both it and the refresh interval are configurable.
- Read-only; no alerting by email or chat, no editing, and no re-running the pipeline are in scope for v1.
- A single dashboard serves both environments from the same data store.
- The visual design is the approved prototype in `docs/design/pipeline-monitor-degisn`; its optional web font may fall back to the system font without affecting function.
- The app is delivered as its own project in the `performance_monitoring_app` folder, separate from the pipeline; it only reads the stored records and shares no code with the pipeline at runtime.
