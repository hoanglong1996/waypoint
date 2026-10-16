# Feature Specification: Pipeline Step Audit Trail

**Feature Branch**: `001-pipeline-step-audit`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "in run_pipeline function, I use redis to store input and output of function inside with ttl 1 month, after running I can check input and output of each function via redis, e.g: self.read_callrail_account.execute() with no input, output is 10 accounts, for list or object, I don't need to know too detailed, I only want the number of items"

## Clarifications

### Session 2026-10-15

- Q: When the pipeline runs again, are previous runs' records kept or replaced? → A: Kept; every run's records are stored separately, each expiring 30 days after it was written.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inspect what each pipeline step received and produced (Priority: P1)

After a pipeline run, an operator wants to see, for every step in the run (read accounts, read calls, read partners, read instances, read campaigns, read click-view records, merge call statistics, transform, save), what went in and what came out, summarised as item counts. For example: "read accounts: input none, output 10 items".

**Why this priority**: This is the whole feature. It lets the operator find where data drops off (e.g. 10 accounts but 0 calls) without re-running the job or reading console logs.

**Independent Test**: Run the pipeline once, then look up the stored record for the "read accounts" step and confirm it shows no input and an output count equal to the number of accounts read.

**Acceptance Scenarios**:

1. **Given** a completed pipeline run, **When** the operator looks up a step's record, **Then** it shows the step name, an input summary and an output summary.
2. **Given** a step that takes no input (e.g. reading accounts), **When** the record is viewed, **Then** the input is shown as "none" and the output is the number of accounts returned.
3. **Given** a step whose input or output is a list, **When** the record is viewed, **Then** only the number of items is shown, not the items themselves.
4. **Given** a step whose input is several collections (e.g. merging calls, campaigns and click-view records), **When** the record is viewed, **Then** each input shows its own item count.

---

### User Story 2 - Records expire automatically (Priority: P2)

The operator expects step records to disappear on their own after one month so history does not grow without limit.

**Why this priority**: Retention is a stated requirement but does not affect the core value of seeing counts.

**Independent Test**: Inspect a freshly written record and confirm its remaining lifetime is about one month.

**Acceptance Scenarios**:

1. **Given** a record just written, **When** its remaining lifetime is checked, **Then** it is about 30 days.

---

### User Story 3 - Audit problems never break the pipeline (Priority: P2)

If the audit store is unreachable or recording fails, the pipeline must still run and save call statistics as it does today.

**Why this priority**: The audit trail is diagnostic; it must not become a new way for the job to fail.

**Independent Test**: Run the pipeline with the audit store unavailable and confirm it completes and saves data, with a warning noted.

**Acceptance Scenarios**:

1. **Given** the audit store is unavailable, **When** the pipeline runs, **Then** all steps still execute and results are saved.
2. **Given** a step fails mid-run, **When** the operator checks records, **Then** records for the steps that completed are present.

### Edge Cases

- A step returns an empty list: output count is 0 (distinct from "no data recorded").
- A step returns a single object rather than a list: count is 1.
- A step returns nothing (e.g. the transform and save steps): output shown as "none".
- Two runs happen on the same day (prod and qa, or a re-run): records must not overwrite each other across runs or environments.
- Counts only: no caller names, phone numbers, transcripts or other record contents may be stored (see constitution principle II).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For every step executed in a pipeline run, the system MUST store a record containing the step name, an input summary and an output summary.
- **FR-002**: A list input or output MUST be summarised as its item count only; a single object as a count of 1; no value as "none".
- **FR-003**: When a step has multiple inputs, each input MUST have its own named count.
- **FR-004**: Records MUST NOT contain any item contents, only counts and identifying metadata.
- **FR-005**: Each record MUST expire automatically 30 days after it is written.
- **FR-006**: Records MUST be identifiable by run and environment. A new run MUST NOT overwrite or remove any earlier run's records (nor prod/qa records), and an operator MUST be able to tell which run is the latest from the record's run time.
- **FR-007**: Each record MUST include the time the step finished.
- **FR-008**: A failure to store a record MUST NOT stop or fail the pipeline; it MUST be reported as a warning.
- **FR-009**: Records for steps completed before a pipeline failure MUST remain available.
- **FR-010**: The existing console messages and pipeline results MUST be unchanged.

### Key Entities

- **Pipeline Run**: One execution of the pipeline, identified by environment and start time.
- **Step Record**: Summary of one step in a run: step name, input counts (by name), output count, finish time, 30-day lifetime.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After any run, an operator can see the input and output counts for 100% of executed steps without re-running the job.
- **SC-002**: An operator can locate where data was lost between steps (e.g. a step with non-zero input and zero output) in under 2 minutes.
- **SC-003**: Records are no longer retrievable after 30 days and remain retrievable before then.
- **SC-004**: With the audit store unavailable, the pipeline completes and saves call statistics in 100% of runs.
- **SC-005**: Zero caller PII appears in stored records.

## Assumptions

- The operator inspects records through the Redis store already used by the project's environment, as described in the request; no new viewing tool is in scope.
- "Step" means each use-case call inside `run_pipeline`, as listed in User Story 1.
- Input counts are recorded for collection inputs; the single-object or scalar case counts as 1.
- The Redis connection settings follow the project's existing environment configuration, and a new setting for it will be documented in the README.
