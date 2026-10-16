# Feature Specification: Run Liveness Heartbeat

**Feature Branch**: `009-run-liveness-heartbeat`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "let's mention the problem and option 3 into the new specs, I want to fix this issue following SDD workflow" (option 3 = "Add a heartbeat" from the discussion of how Waypoint copes with pipelines that hang or die).

## Clarifications

### Session 2026-10-16

- Q: If a run has been shown as Died and its alive signals start arriving again, should the monitor switch it back to Running or Stalled? → A: No. Died is permanent: once a run has been judged Died, it stays Died.
- Q: Where should the "this run died" verdict be kept so it survives monitor restarts and several monitor instances? → A: The monitor writes one small "died" item per run into the same data store the first time it judges the run Died. This is the only write the monitor makes.

## Problem

A pipeline can hang or die at any moment (out-of-memory kill, pod eviction, hard kill, a step blocked on a network call). When that happens, Waypoint Monitor cannot tell what went wrong:

- A step that has started but not finished is shown as "Running" and, after the stall threshold (15 minutes by default), as "Stalled". The monitor **cannot tell a hung process from a dead one**: both look identical.
- A process killed without warning leaves nothing behind but the start marker of the step it was in. The operator learns about it only after the stall threshold, and even then sees only "Stalled", not "the process is gone".
- The stall threshold is a single guess for every step, so a legitimately long step is flagged as stalled while a dead run waits the full threshold before it looks wrong.

Pipelines that report nothing are therefore indistinguishable from pipelines that are slow, and the operator has no fast, trustworthy signal that a run has died and needs to be restarted.

## Proposed approach

While a run is alive, the pipeline periodically publishes a small "still alive" signal for that run. Waypoint Monitor compares the time of the latest signal with the current time:

- recent signal, step unfinished: the process is alive, so the step is running or hung (existing Running / Stalled behaviour);
- old signal, step unfinished: the process is gone, so the run is shown as **Died** immediately;
- no signal ever recorded: the run came from a pipeline that does not send it, so behaviour is exactly as today.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See at once that a run has died (Priority: P1)

An operator opens Waypoint Monitor after a pipeline was killed in the middle of a step. Within about a minute and a half of the process disappearing, the run is shown as **Died**, naming the step it was in and when it was last seen alive, instead of showing "Running" for up to 15 minutes and then only "Stalled".

**Why this priority**: This is the core pain: a silent death must be recognisable quickly and unambiguously so the operator can restart the run.

**Independent Test**: Start a run that sends the alive signal, stop it abruptly while a step is open, wait past the death-detection time, and confirm the run and that step show as Died with a last-seen time.

**Acceptance Scenarios**:

1. **Given** a run whose step has started but not finished and whose latest alive signal is older than the death-detection time, **When** the operator views the run, **Then** the run is Died, the open step is marked Died, and the last-seen time is shown.
2. **Given** a Died run, **When** it appears on the home page, **Then** its card is flagged as needing attention and listed with the other problem pipelines.
3. **Given** a Died run, **When** its steps are listed, **Then** later planned steps are shown as not reached (not as "Waiting"), and the run is never counted as running.
4. **Given** a run that died between two steps (no step open), **When** the death-detection time passes, **Then** the run is shown as incomplete and Died rather than "just started" or "Waiting".

---

### User Story 2 - Tell a hung run from a dead one (Priority: P1)

An operator sees a step that has been unfinished for a long time. Because the run is still sending alive signals, the monitor shows it as Running or Stalled (alive but not progressing), clearly different from Died. The operator knows the process exists and can investigate, rather than restart a run that is merely slow.

**Why this priority**: Restarting a slow run wastes work and may double-load data; leaving a dead run alone loses a day. The distinction is the value of the feature.

**Independent Test**: Start a run that keeps sending alive signals but never finishes a step; confirm it is shown as Running, then Stalled past the stall threshold, and never as Died. Then stop the signals and confirm it becomes Died.

**Acceptance Scenarios**:

1. **Given** an unfinished step and a recent alive signal, **When** the step is within the stall threshold, **Then** it is shown as Running.
2. **Given** an unfinished step and a recent alive signal, **When** the step exceeds the stall threshold, **Then** it is shown as Stalled (alive, not progressing) and not as Died.
3. **Given** a Stalled run, **When** its alive signals stop, **Then** the run changes to Died within the death-detection time.

---

### User Story 3 - Older pipelines keep working unchanged (Priority: P2)

Pipelines that do not send the alive signal (older versions, other jobs) continue to be shown exactly as today, with no new Died state and no errors. Newer pipelines work with an older monitor, which ignores the signal.

**Why this priority**: Several pipelines are deployed independently; the feature must not force a coordinated rollout or break existing views.

**Independent Test**: View a run recorded without any alive signal and confirm its status, steps and card are identical to current behaviour; view a run with the signal using an unchanged monitor and confirm nothing breaks.

**Acceptance Scenarios**:

1. **Given** a run with no alive signal recorded, **When** it is viewed, **Then** statuses are computed exactly as before, and it is never labelled Died.
2. **Given** a monitor without this feature and a pipeline that sends the signal, **When** the monitor lists pipelines and runs, **Then** it shows them as before and reports no unreadable records because of the extra signal.

---

### User Story 4 - Sending the signal never harms the pipeline (Priority: P2)

The alive signal is purely diagnostic. If the data store is slow or unreachable, the pipeline keeps running at the same speed and with the same results; the failure is only logged. The signal stops when the run ends or auditing is reconfigured, and it never keeps a finished process alive.

**Why this priority**: Constitution principle V and the existing Waypoint rule: auditing must never change what the pipeline does.

**Independent Test**: Run a pipeline with the data store unreachable and confirm it completes with the same output and exit status; end a run and confirm no further signals are sent and the process exits normally.

**Acceptance Scenarios**:

1. **Given** the data store is unreachable, **When** the pipeline runs, **Then** it completes normally and only warnings are logged.
2. **Given** a run that finished or auditing was cleared, **When** time passes, **Then** no further alive signals are sent.
3. **Given** the pipeline process is ready to exit, **When** the signal sender is still active, **Then** it does not delay or prevent exit.

---

### User Story 5 - Operator can tune how quickly death is declared (Priority: P3)

An operator can set how long without an alive signal is treated as dead, to suit their environment (for example clocks that differ slightly between the pipeline host and the monitor host).

**Why this priority**: A sensible default covers most cases; tuning is only for unusual environments.

**Independent Test**: Change the setting and confirm the Died threshold changes accordingly; confirm the default applies when unset.

**Acceptance Scenarios**:

1. **Given** no setting, **When** the monitor starts, **Then** a default death-detection time of 90 seconds is used.
2. **Given** the setting is changed, **When** a run's last signal is older than the new value, **Then** it is shown as Died; when younger, it is not.

---

### Edge Cases

- The pipeline host and monitor host clocks differ by less than the death-detection time: no false Died. A larger skew may produce false Died or delayed detection and is documented as a limit.
- A run finishes normally: all steps have records, so the stopped signal afterwards never turns a complete run into Died.
- A process is frozen but its signal sender keeps running: shown as alive (Stalled), because the signal proves a process exists, not that it makes progress.
- A step that spawns child processes: only the main process sends the signal; the death of a child alone is not detected.
- A run is restarted: the new run has its own identity and its own signal; the old run stays Died.
- The signal is present but malformed or has an unreadable time: treated as absent for that run (legacy behaviour), never an error.
- Two runs of one pipeline are active: each has its own signal and its own state.
- The data store is briefly unreachable while the run is alive: signals missed for longer than the death-detection time can cause the run to be judged Died; because Died is permanent, it stays Died even after signals resume. This is accepted: the signal interval and death-detection time leave room for six missed signals before that happens.
- Signals reappear for a run already judged Died (store outage ended, clock corrected): the run stays Died.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A running pipeline that has auditing enabled MUST publish an alive signal for its current run immediately at start and then at a regular interval (default 15 seconds) until the run ends or auditing is cleared.
- **FR-002**: The alive signal MUST contain only the run identity and the time of the latest signal; it MUST NOT contain item contents, caller data or any other business data.
- **FR-003**: The latest alive signal of a run MUST remain readable for as long as that run's other records are kept, so that "never sent" can be told apart from "stopped sending".
- **FR-004**: Failure to send the alive signal MUST NOT raise to the caller, change pipeline results, or noticeably delay the pipeline; it MUST only be logged as a warning.
- **FR-005**: The alive signal sender MUST NOT keep the process running after the pipeline ends and MUST stop when auditing is cleared or re-initialised.
- **FR-006**: The monitor MUST read the latest alive signal of each run together with the run's other records.
- **FR-007**: When a run has a recorded signal older than the death-detection time and at least one planned step is not finished, the monitor MUST mark the run Died, mark any open step Died, and exclude the run from "running".
- **FR-007a**: Once a run has been judged Died, the monitor MUST keep showing it as Died on every later view, including after the monitor restarts and after further alive signals arrive for that run. A run judged Died MUST NOT return to Running, Stalled or Complete.
- **FR-007b**: The first time the monitor judges a run Died, it MUST record that verdict for the run in the same data store, containing only the run identity, the time of the judgement and the time of the last alive signal seen. Every later view, by any monitor instance, MUST read this verdict and show the run as Died without re-evaluating signals.
- **FR-007c**: Recording the verdict MUST be the only write the monitor ever makes. It MUST NOT delete or modify any record written by a pipeline, and the verdict MUST expire together with the run's other records.
- **FR-007d**: If recording the verdict fails (store unreachable or read-only access), the monitor MUST still show the run as Died for that view, MUST NOT fail the request, and MUST retry on a later view.
- **FR-007e**: If two monitor instances record a verdict for the same run at the same time, the result MUST be a single consistent Died verdict (no duplicates, no conflicting values shown).
- **FR-008**: A Died run MUST be counted as incomplete, MUST report the first step not finished, and MUST report the time of its last alive signal.
- **FR-009**: When a run has a recent alive signal and an unfinished step, the monitor MUST keep the existing Running and Stalled behaviour (Stalled past the stall threshold) and MUST NOT mark it Died.
- **FR-010**: When a run has no valid alive signal, the monitor MUST compute status exactly as before this feature and MUST NOT mark it Died.
- **FR-011**: The death-detection time MUST default to 90 seconds and MUST be configurable through the monitor's existing configuration mechanism.
- **FR-012**: The home page, latest-run page and history MUST show the Died state distinctly from Running, Stalled and Complete, including the last-seen time, and a Died run MUST be treated as needing attention.
- **FR-013**: A run that finished with all steps recorded MUST never be shown as Died, regardless of how old its last signal is.
- **FR-014**: Introducing the alive signal MUST be backward compatible in both directions: a monitor without the feature MUST ignore the signal and the Died verdict without errors or unreadable-record counts, and a monitor with the feature MUST handle runs from pipelines that do not send it.
- **FR-015**: The two new stored items (alive signal and Died verdict), their meaning and their retention MUST be documented in the Redis key contract and the monitor README, including the new configuration setting, the clock-skew limit, and the fact that the monitor now has one permitted write (replacing the "never writes" statement and the security note).

### Key Entities

- **Alive signal**: A per-run record of "this run's process was alive at time T". Attributes: run identity (pipeline, environment, run id), latest signal time, format version. One per run, overwritten at each beat.
- **Run liveness**: The monitor's judgement for a run: Alive (recent signal), Died (old signal, unfinished work; permanent once reached), or Unknown (no signal, legacy).
- **Died verdict**: A per-run record stating "this run was judged dead at time T, last seen alive at time L". Written once by the monitor, read by every monitor instance, expires with the run. Contains no business data.
- **Death-detection time**: The age of the latest signal beyond which an unfinished run is considered dead.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a pipeline process is killed mid-step, the operator sees the run as Died within 2 minutes (default settings), versus at least 15 minutes to see "Stalled" today.
- **SC-002**: In test scenarios covering killed, hung (alive but stuck) and slow-but-progressing runs, 100% are classified correctly as Died, Stalled and Running respectively.
- **SC-003**: Runs from pipelines that do not send the signal show identical status and steps before and after the change in 100% of the existing monitor tests.
- **SC-004**: With the data store unreachable, a pipeline completes with the same results and exit status as with the store available, and pipeline duration increases by no more than 1 second.
- **SC-005**: An operator can distinguish "dead, restart it" from "alive but stuck, investigate" for any open step from the run page alone, without reading logs.
- **SC-006**: A run judged Died is still shown as Died after the monitor is restarted and after its alive signals resume, in 100% of test scenarios.
- **SC-007**: Rolling out the signal to one pipeline and the monitor update in either order causes no errors or missing data in the monitor.

## Assumptions

- The front-end Died indicator is part of this feature (User Story 1 and FR-012); it is not deferred to a later change.
- Default alive interval is 15 seconds and default death-detection time is 90 seconds (six missed beats), chosen to tolerate brief store outages and small clock differences; both are adjustable.
- Pipeline and monitor hosts keep their clocks within the death-detection time of each other; larger skew is a documented limitation, not handled.
- The signal proves a process exists, not that it makes progress; detecting an alive but frozen process remains the existing stall threshold's job.
- Only the main process of a pipeline sends the signal; child processes are out of scope.
- The record format version stays unchanged because the signal is an additive item; the Waypoint library receives a minor version bump.
- Recording failure reasons (exception class) and a run-level "finished" record, and making writes resilient to flaky storage, were discussed alongside this problem and are separate features, out of scope here.
- Push alerts (chat or email) when a run dies are out of scope.
- Existing storage, key naming, retention and personal-data rules of Waypoint (counts and names only) apply unchanged to both new items.
- The monitor's data-store account is granted permission to write the Died verdict; where it only has read access, the run is still shown as Died for each view (FR-007d), but permanence across restarts is then not guaranteed and the monitor logs a warning.
