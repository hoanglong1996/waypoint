# Feature Specification: Live Step Running Indicator

**Feature Branch**: `004-step-running-indicator`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "for a step in the pipeline, please use a loading icon or processing bar for the step when the step is running and use a reload mechanism with interval 5s, i don't need to press refresh page."

## Clarifications

### Session 2026-10-15

- Q: Should the page reload every 5 seconds all the time, or only while a run is in progress? → A: Always every 5 seconds, whether or not a run is active.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See which step is running right now (Priority: P1)

An operator opens the monitor while the pipeline is mid-run. The step that is currently executing shows an animated loading indicator (a spinner or progress bar) and the label "Running", instead of looking like a step that was never reported. Steps already finished show their counts as today; steps that have not started yet are shown as "Waiting" rather than as a problem. The indicator appears wherever the step is drawn: on its graph node and on its list card.

**Why this priority**: This is the core request. Today a step with no record looks the same whether it is busy or the run broke, so the operator cannot tell "still working" from "stopped here".

**Independent Test**: Start a run, open the monitor, and confirm exactly one step shows the loading indicator and "Running" while the earlier steps show counts and the later steps show "Waiting".

**Acceptance Scenarios**:

1. **Given** a run in progress where step 3 has started and not finished, **When** the operator views the run, **Then** step 3 shows a loading indicator and "Running", steps 1–2 show their counts, and steps 4–9 show "Waiting".
2. **Given** a running step, **When** it is displayed, **Then** it is not counted as "Not reported", "Not reached" or "Data loss", and no stale or stop warning is raised for the run because of it.
3. **Given** a running step, **When** displayed, **Then** the running state is conveyed by icon, motion and text, not by colour alone.
4. **Given** the operator prefers reduced motion, **When** a step is running, **Then** the indicator is shown without animation and still reads "Running".
5. **Given** a step that has started, **When** its previous run's counts are known, **Then** the new run's step does not show the old counts as if they were current.

---

### User Story 2 - The page updates itself every 5 seconds (Priority: P1)

The monitor reloads its data on its own every 5 seconds, so the operator sees a run start and then advance (Running moves to the next step, counts fill in) without pressing the browser's refresh button. Selection, view (Graph or List), environment and open History run are kept across each reload, and the page does not flicker or jump.

**Why this priority**: The indicator is only useful if it stays truthful; without automatic reload the operator would have to refresh by hand to see it finish.

**Independent Test**: With a run in progress, leave the page untouched and confirm that within about 5 seconds of a step finishing, its counts appear and the indicator moves to the next step.

**Acceptance Scenarios**:

1. **Given** the page is open, **When** 5 seconds pass, **Then** the data is reloaded without user action and the "last updated" time advances.
2. **Given** a step finishes, **When** the next reload happens, **Then** that step shows its counts and the following step shows the loading indicator.
3. **Given** the operator has selected a step or opened a History run, **When** a reload happens, **Then** the selection and view are unchanged.
4. **Given** the last step finishes, **When** the next reload happens, **Then** no step shows the loading indicator and the run is displayed as complete.
5. **Given** no run is in progress, **When** a new run starts, **Then** its first running step appears within the next reload (about 5 seconds) with no user action.
6. **Given** a reload fails, **When** it fails, **Then** the existing data-unavailable message is shown and the page keeps retrying automatically.

---

### User Story 3 - Tell a stalled run from a slow step (Priority: P2)

If a step has been "Running" far longer than expected, or the run stops without ever finishing that step, the operator can tell it is no longer progressing. The step shows how long it has been running; once it exceeds a stall limit it changes from "Running" to "Stalled" (no longer animated) so it is not mistaken for a live job.

**Why this priority**: Without it, a crashed run would show a spinner forever. Useful but secondary to showing and updating the live state.

**Independent Test**: Leave a step marked as started with no further activity beyond the stall limit and confirm it shows "Stalled" with its elapsed time and no animation.

**Acceptance Scenarios**:

1. **Given** a running step, **When** displayed, **Then** it shows elapsed time since it started (e.g. "Running · 42 s").
2. **Given** a step marked running for longer than the stall limit, **When** displayed, **Then** it shows "Stalled", and the animation stops.
3. **Given** a run that crashed during a step, **When** viewed later, **Then** the step is never shown as "Running" indefinitely.

---

### Edge Cases

- A step finishes between two reloads: the operator may never see it as Running; this is acceptable, only the final counts matter.
- Two runs overlap (a new run starts before the old one finishes): the latest run's state is shown; an older run shows no running step.
- A run opened from History is old and complete: it never shows a running indicator.
- A stalled step is the run's stop point: the steps after it are shown as "Not reached" (not "Waiting"), the same as after any other stop.
- Steps that finish within a fraction of a second: no flicker of the indicator is required.
- The browser tab is in the background: reloading may slow or pause, and the page catches up on return.
- Clock difference between pipeline and browser: elapsed time must not show negative values.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST announce when each step starts, so the monitor can tell a running step apart from a step that has no record.
- **FR-002**: The monitor MUST show every step of a run in one of: Waiting, Running, Done (existing health states apply), or Stalled, in addition to the existing Fine, Data loss, Not reported and Not reached states.
- **FR-003**: A running step MUST show a loading indicator (spinner or progress bar) and the text "Running" on both its graph node and its list card.
- **FR-004**: A step that has not started because an earlier step of the same active run is still running MUST show "Waiting", not "Not reported" or "Not reached", and MUST NOT raise a stop or data-loss warning.
- **FR-005**: The monitor MUST reload its data automatically every 5 seconds, whether or not a run is in progress, without user action.
- **FR-006**: The 5-second interval MUST be configurable and replaces the dashboard's previous 60-second default refresh (spec 002 FR-008); the data-unavailable retry behaviour (FR-012) is unchanged.
- **FR-007**: Automatic reloads MUST preserve the current tab, environment, view, run and step selection, and MUST update the page without a full page reload or visible flicker.
- **FR-008**: A running step MUST show its elapsed time, and MUST change to "Stalled" (no animation) when it has been running longer than a configurable stall limit.
- **FR-009**: Running and Stalled states MUST be distinguishable by icon and text as well as colour, and the animation MUST be disabled under reduced-motion preferences.
- **FR-010**: The headline numbers, summary line and stale-run warning MUST treat a run in progress as in progress, not as failed or stale.
- **FR-011**: Recording that a step started MUST NOT change what the pipeline does, and MUST NOT store caller data (counts and timestamps only), consistent with the existing step audit.
- **FR-012**: If the data store is unreachable during an automatic reload, the existing data-unavailable message and retry behaviour MUST apply.

### Key Entities

- **Step Start Marker**: A short-lived record that a named step of a named run began at a given time; superseded by the step's finish record.
- **Step Live State**: The displayed state of a step in a run: Waiting, Running, Stalled, or finished with an existing health state.
- **Run Progress**: Whether the displayed run is in progress (at least one running step) or not; drives the running indicators and the in-progress summary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: During a run, an operator can name the currently running step within 3 seconds of looking at the page.
- **SC-002**: A step's completion appears on an open page within 5 seconds (plus the time to load) with no manual reload, in 95% of cases.
- **SC-003**: 0 runs in progress are reported as "Not reported", "Not reached" or stopped while their steps are still running.
- **SC-004**: A crashed run stops showing a running indicator within the stall limit, in 100% of cases.
- **SC-005**: The operator's selection and view survive 100% of automatic reloads.
- **SC-006**: A newly started run appears on an open page within 5 seconds (plus load time) in 95% of cases, and an open page makes no more than one data request per 5-second interval.

## Assumptions

- The pipeline currently records a step only after it finishes, so a start announcement is new and in scope (FR-001).
- Scope covers the whole monitor (latest run and History), not just one step type.
- The 5-second reload is always on (confirmed in clarification), at the cost of constant light polling by every open page; the interval is configurable.
- The default stall limit is 15 minutes and is configurable.
- A start marker expires automatically, like existing step records.
- The monitor remains read-only; no start, stop or re-run controls are in scope.
- Builds on specs 001 (step audit), 002 (dashboard) and 003 (directed graph); list and graph views stay otherwise unchanged.
