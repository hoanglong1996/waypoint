# Feature Specification: Self-Describing Pipeline Graph

**Feature Branch**: `005-self-describing-pipeline-graph`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "I want the graph is dynamic, the redis itself needs to include all metadata to draw the chart for me to bring step_audit and performance_monitoring_app web app to apply for other pipeline"

## Clarifications

### Session 2026-10-16

- Q: For runs stored before this change (no flow description), keep the old CallRail graph or draw a plain graph from step records? → A: Draw a simplified graph (steps in recorded order, no stored hand-offs) with a clear "no flow description" note; the monitor keeps no built-in pipeline knowledge. (Applies to new-layout runs missing a description; see next answer for old-layout records.)
- Q: How does the monitor learn which pipelines exist? → A: Automatically from the data store; every pipeline that writes records appears in the picker, with no monitor setting.
- Q: How should records in the old key layout (no pipeline name) be handled? → A: Ignored. The old data has been deleted; history starts at the first new-layout run. No legacy compatibility is needed.
- Q: What if a run's flow description differs from the pipeline's previous run? → A: Each run is always drawn from its own description; no cross-run comparison or remapping.
- Q: Where does a pipeline's step description come from? → A: The developer declares the full step list once (names, inputs, producers, optional hints); it is stored at run start. Steps do not announce themselves.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Graph is drawn from what a run records (Priority: P1)

An operator opens the monitor for a pipeline run. The graph of steps, the hand-offs between them, the
step groupings, the friendly names and the left-to-right order are all built from information the run
itself stored alongside its step records. The monitor holds no built-in knowledge of any particular
pipeline's steps.

**Why this priority**: This is the core of the request. Without it the monitor stays tied to one
pipeline and every new or changed step needs a monitor change.

**Independent Test**: Store a run for a made-up pipeline whose step names the monitor has never seen.
Open the monitor: the full graph (nodes, arrows with counts, groups, labels) appears and looks
sensible, with no change to the monitor.

**Acceptance Scenarios**:

1. **Given** a run whose stored description lists steps, their inputs and their groups, **When** the operator opens the graph, **Then** every step is drawn as a node, every input as an arrow from its producing step, and nodes are grouped and labelled as described.
2. **Given** the existing pipeline adds, renames or removes a step in its code, **When** its next run finishes, **Then** the graph for that run shows the change with no monitor change or redeploy.
3. **Given** two runs of the same pipeline whose steps differ, **When** the operator views each, **Then** each graph reflects its own run's steps, not a shared fixed list.

---

### User Story 2 - A new pipeline adopts the audit and monitor with minimal effort (Priority: P1)

A developer of a different pipeline wants the same per-step audit trail and dashboard. They describe
their steps once, in their own pipeline, using the shared audit facility. After the pipeline runs,
its runs appear in the monitor, selectable alongside others, with a correct graph.

**Why this priority**: Reuse across pipelines is the stated purpose. Equal in value to Story 1 because
a self-describing graph is only useful if another pipeline can actually be onboarded.

**Independent Test**: Wire a second sample pipeline with three steps to the audit facility, run it, and
confirm it shows up in the monitor with a correct graph, without editing the monitor or the first pipeline.

**Acceptance Scenarios**:

1. **Given** a second pipeline that records its steps with the shared audit facility, **When** it runs, **Then** the monitor lists it and shows its runs and graph.
2. **Given** two pipelines writing to the same data store, **When** the operator picks a pipeline, **Then** only that pipeline's runs and graph are shown and the two never mix.
3. **Given** a pipeline that supplies no layout hints, **When** its graph is opened, **Then** a readable layout is produced automatically from the hand-offs alone.

---

### User Story 3 - Not-yet-run and failed steps still appear in the graph (Priority: P2)

When a run stops partway, the operator still sees the whole planned flow: steps that did not run are
shown as missing or not reached, and the stopping point is clear, as today.

**Why this priority**: Today the fixed step list is what lets the monitor show steps that never reported.
That behaviour must survive when the list comes from the data instead.

**Independent Test**: Store a run description with six steps but records for only the first three.
The graph shows all six, with the remainder marked as not reached.

**Acceptance Scenarios**:

1. **Given** a run whose description lists six steps and only three finished, **When** the operator views it, **Then** all six appear and the last three are marked missing or not reached.
2. **Given** a run that started but was interrupted before it could store its description, **When** the operator views it, **Then** the run is still shown from whatever records exist, with a clear note that its full flow is unknown.

---

### User Story 4 - Bad or missing descriptions never break the page (Priority: P2)

A run may lack a flow description (interrupted before it was written) or carry one that is malformed. The
monitor still works and tells the operator what is wrong. Records in the previous layout (no pipeline name)
are not supported: the old data has been deleted and the monitor ignores such records.

**Why this priority**: Protects the dashboard from bad input; not the headline value.

**Independent Test**: Store a run with records but no description, and another with a malformed description. Both open without error.

**Acceptance Scenarios**:

1. **Given** a stored run with records but no description, **When** the operator opens it, **Then** it is shown as a simplified graph (steps in recorded order, no hand-off arrows) with a clear "no flow description" note, never an error.
2. **Given** a description that is malformed or partly invalid (for example an arrow pointing at a step that does not exist), **When** the operator opens the run, **Then** the valid part is shown, the problem is called out, and the page keeps working.

---

### Edge Cases

- A step's declared input names a producer that is not among the run's steps: shown as a dangling input, not a crash.
- Circular hand-offs in a description: the graph still renders and the cycle is flagged.
- A very large number of steps (e.g. 50): the graph stays readable and usable.
- Two pipelines use the same step name: they must not be confused.
- Description present but no step has reported yet (run just started): the planned flow is shown with every step waiting.
- Description stored for the run disagrees with step records actually found (extra or missing step): extras are shown as unplanned, missing as not reached.
- Step labels, group names or descriptions containing unusual or very long text are displayed safely and truncated legibly.
- The description must never contain item contents or personal data, only structure and counts.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each pipeline run MUST store, with its audit records, a description of the run's flow: the list of steps, each step's named inputs and which step produces each input, and optional grouping, friendly label and ordering hints.
- **FR-002**: The pipeline developer MUST declare the full step list once, up front; the pipeline stores it when the run starts, before any step completes, so a run that fails early still has a known flow. Steps do not describe themselves as they run.
- **FR-003**: The monitor MUST build the graph (nodes, arrows, groups, labels, order) exclusively from stored data and MUST NOT contain a built-in list of any pipeline's steps. Each run MUST be drawn from its own description only, with no comparison against or remapping onto other runs.
- **FR-004**: The monitor MUST show runs from more than one pipeline held in the same data store, let the operator choose a pipeline, and keep each pipeline's runs and graph separate. Pipelines MUST be discovered automatically from the data store, with no monitor setting needed to add one.
- **FR-005**: A developer MUST be able to adopt the audit facility in another pipeline by declaring that pipeline's name and steps, without changing the monitor or other pipelines.
- **FR-006**: When no layout hints are supplied, the monitor MUST produce a readable layout automatically from the hand-offs; when hints are supplied they MUST be honoured.
- **FR-007**: Steps in the description that have no record MUST be shown as not reached or missing, preserving today's stopped-point and data-loss indications.
- **FR-008**: Runs (in the current layout) stored without a description MUST remain viewable without error, shown as a simplified graph (steps in recorded order, no hand-off arrows) with a "no flow description" note. The monitor MUST NOT keep a fallback list of any pipeline's steps.
- **FR-009**: Malformed, partial or inconsistent descriptions MUST NOT break the page; valid parts are shown and the problem is surfaced to the operator.
- **FR-010**: The description MUST contain only structural information (names, labels, groups, order) and MUST NOT contain item contents or caller data. A recording failure MUST NOT change what the pipeline does.
- **FR-011**: The stored description and records MUST expire on the same schedule as existing audit records, so no data outlives the retention period.
- **FR-012**: The stored format MUST be documented as a contract that another pipeline's developer can follow without reading monitor source.
- **FR-013**: The monitor MUST remain read-only toward the data store.
- **FR-014**: Records in the previous key layout (no pipeline name) MUST be ignored: not shown and not treated as errors.

### Key Entities

- **Pipeline**: A named, independently scheduled flow of steps (e.g. the existing CallRail flow); the unit the operator selects in the monitor.
- **Run Description**: The per-run statement of the flow: pipeline name, run identifier, steps, hand-offs, groups, labels, ordering hints, and a format version.
- **Step Definition**: One planned step: name, optional friendly label, optional group, named inputs, each with its producing step.
- **Step Record / Start Marker**: Existing per-step results and in-progress markers, now tied to a pipeline.
- **Run**: One execution of a pipeline, identified by pipeline, environment and run identifier.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adding, renaming or removing a step in a pipeline requires zero changes to the monitor; the change appears in the graph after the next run.
- **SC-002**: A developer can onboard a new pipeline, from first reading the contract to seeing its graph in the monitor, in under half a day, with no edits to the monitor.
- **SC-003**: A second pipeline's runs appear alongside the first with 0 cross-contamination of runs, steps or counts in acceptance testing.
- **SC-004**: 100% of tested runs with a missing or malformed description open without errors and with a visible explanation.
- **SC-005**: A run interrupted at any step still shows its whole planned flow, with the stopping point identified, in 100% of tested cases.
- **SC-006**: For a pipeline with up to 30 steps and no layout hints, an operator can follow every hand-off without overlapping or hidden arrows in review.
- **SC-007**: No stored description or record contains item contents or caller data in review of the stored data.

## Assumptions

- The data store is the single shared channel between pipelines and the monitor; no direct connection between them is introduced.
- Pipelines remain single-sequence flows run by one process; parallel execution inside a run is out of scope.
- Records in the previous key layout are out of scope: that data has been deleted and the monitor ignores any that remain. Step records and start markers are extended with a pipeline name; retention stays the same as today.
- The monitor stays read-only, with no login, as in earlier features.
- Extracting the audit facility into a reusable, separately versioned package is out of scope; sharing is by documented contract and a small, copyable facility.
- The existing CallRail pipeline is converted to describe itself as the reference example.
- Layout hints (group, order, position) are optional; automatic layout covers their absence.
- Per-pipeline access control and pipeline-specific alerting are out of scope.
