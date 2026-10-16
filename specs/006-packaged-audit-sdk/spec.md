# Feature Specification: Packaged Pipeline Monitoring Product

**Feature Branch**: `006-packaged-audit-sdk`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Package the product as three components: the monitoring dashboard app, Redis, and the step-audit integration library. Another pipeline that wants its graph visualised must adopt the step-audit library. The library gets one place to initialise the pipeline name and Redis settings, configured from the pipeline's main entry point. Make adopting it need as few changes to the pipeline's application code as possible (e.g. annotating step functions instead of wrapping each call), while step information still reaches Redis."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adopt the audit library in another pipeline with minimal edits (Priority: P1)

A developer of a different pipeline wants its steps and graph to appear in the monitoring dashboard. They install the step-audit library, declare the pipeline name and Redis settings once in the pipeline's entry point, and mark each step function as an audited step. The orchestration code that calls the steps stays as it is today: no call is rewritten or wrapped.

**Why this priority**: This is the product's core promise. If adoption is costly, nobody will use it.

**Independent Test**: Take a small sample pipeline with no audit code. Apply the adoption steps. Run it and confirm every step's record appears in Redis, with the diff to the pipeline's orchestration code being zero lines.

**Acceptance Scenarios**:

1. **Given** a pipeline whose steps are plain functions or methods, **When** the developer configures the library once in the entry point and marks each step as audited, **Then** a run reports start and finish, input counts and output count for every step without any change to the code that calls the steps.
2. **Given** a step marked as audited but no configuration has been made, **When** the pipeline runs, **Then** the step behaves exactly as if unmarked and nothing is written anywhere.
3. **Given** a configured pipeline, **When** the Redis server is unreachable, **Then** the pipeline completes with the same results and only a warning is logged.

---

### User Story 2 - One-place configuration of pipeline identity and Redis (Priority: P1)

The developer sets the pipeline's name, display label and Redis connection in a single initialisation call in the entry point. The step list, groups and layout hints (what the pipeline already declares today) are supplied there too or derived from the marked steps. The application code never mentions Redis or environment names.

**Why this priority**: Without a single configuration point, the "minimal changes to application code" goal cannot be met.

**Independent Test**: Change only the initialisation values in the entry point (name, Redis address) and confirm records land under the new name at the new address with no other file edited.

**Acceptance Scenarios**:

1. **Given** the initialisation call is given a valid pipeline name and Redis address, **When** a run happens, **Then** the dashboard lists that pipeline and shows its graph.
2. **Given** an invalid pipeline name or Redis address, **When** the initialisation call is made, **Then** the developer gets a clear message and the pipeline still runs unaudited.
3. **Given** the initialisation is never called twice in a run by mistake, **When** it is called a second time, **Then** the second call is ignored with a warning (or replaces the first, consistently), never producing mixed records.

---

### User Story 3 - Deploy all three components together (Priority: P2)

An operator can bring up the dashboard, Redis and a pipeline wired to the library from one packaged set, so a new environment shows a working dashboard with no hand assembly. The library is installable by other pipelines from the package, not by copying files.

**Why this priority**: Packaging is what makes the product shippable, but it is only valuable once adoption (P1) works.

**Independent Test**: On a clean machine, follow the packaging instructions only and confirm the dashboard shows records from a sample pipeline run.

**Acceptance Scenarios**:

1. **Given** a clean environment, **When** the operator starts the packaged set, **Then** the dashboard, Redis and the library are all available and the dashboard connects to Redis without manual editing of code.
2. **Given** a released version of the library, **When** a second pipeline declares it as a dependency, **Then** it can be used without access to this repository's source.
3. **Given** a new library version with a changed record format, **When** an older dashboard reads the records, **Then** it shows a clear "unsupported version" state instead of wrong data.

---

### User Story 4 - Existing CallRail pipeline keeps working (Priority: P2)

The CallRail pipeline switches to the packaged library and its dashboard graph is unchanged.

**Why this priority**: It is the reference adopter and proves the migration claim.

**Independent Test**: Run CallRail before and after; the records and the rendered graph are identical.

**Acceptance Scenarios**:

1. **Given** CallRail moved to the packaged library, **When** it runs, **Then** the records and graph match those from before the change.

---

### Edge Cases

- A step raises an error: the error propagates unchanged, the dashboard shows the step as started but not finished.
- A marked step is called more than once in a run, or from outside a run.
- A marked step is not in the declared step list: recorded and flagged as unplanned.
- Steps returning nothing, or returning large collections: only counts are recorded, never contents.
- Concurrent runs of the same pipeline: records stay separated by run.
- Asynchronous steps and steps defined as methods on classes.
- Two pipelines choosing the same name.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product MUST be deliverable as three components: the monitoring dashboard, the Redis store, and the step-audit library for pipelines.
- **FR-002**: The step-audit library MUST be installable by another pipeline as a versioned package, independent of this repository's other code.
- **FR-003**: The library MUST provide one initialisation point where the developer sets the pipeline name, optional display label and Redis connection settings.
- **FR-004**: The pipeline's entry point MUST be the only place that needs to know the pipeline name and Redis settings.
- **FR-005**: The library MUST let a developer mark a step as audited by annotating the step itself, so that the code which calls the steps needs no modification.
- **FR-006**: For each audited step the library MUST record start, finish, input counts and output count, matching what the dashboard already shows today.
- **FR-007**: Step input counts MUST be obtainable without the developer rewriting call sites (for example from the step's own arguments, with an optional way to name them).
- **FR-008**: The library MUST record only names and counts, never item contents.
- **FR-009**: If configuration is missing or invalid, or Redis fails at any moment, audited steps MUST behave exactly like unaudited ones and the failure MUST be logged without raising.
- **FR-010**: Audited steps MUST preserve the original function's name, arguments, return value and errors.
- **FR-011**: The library MUST support the pipeline's step declaration (names, hand-offs, groups, labels, layout hints) so the dashboard can draw the graph; the declaration MUST be validated at initialisation with clear messages.
- **FR-012**: The library MUST support synchronous and asynchronous steps and methods.
- **FR-013**: Records MUST carry a format version that the dashboard checks.
- **FR-014**: The packaged set MUST include documented instructions with a minimal sample pipeline showing adoption in a few lines.
- **FR-015**: The CallRail pipeline MUST be migrated to the packaged library with its dashboard output unchanged.

### Key Entities

- **Pipeline identity**: name, label and Redis connection settings, configured once.
- **Pipeline declaration**: ordered steps, hand-offs between steps, groups, labels, layout hints.
- **Audited step**: a unit of work marked for recording.
- **Run**: one execution of a pipeline, with a unique identifier.
- **Step record**: start marker and finish record with names and counts only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Adopting the library in a new pipeline needs zero edits to the code that calls its steps and no more than one line per step plus one initialisation block.
- **SC-002**: A developer who has not seen the library can get a sample pipeline showing in the dashboard in under 30 minutes using the documentation alone.
- **SC-003**: With the monitoring store down, 100% of audited pipeline runs finish with results identical to an unaudited run.
- **SC-004**: 100% of audited steps in a run appear in the dashboard with correct counts.
- **SC-005**: An operator can bring up the full set on a clean machine in under 15 minutes.
- **SC-006**: CallRail's graph and counts before and after migration are identical for the same input.

## Assumptions

- The three components stay in one repository for now; "packaging" means a versioned installable library plus a runnable deployment of dashboard and Redis, not a public release.
- The record format and Redis key layout from feature 005 are kept; this feature changes how pipelines produce them, not what is stored.
- Pipelines using the library are written in the same language as the library.
- The step declaration stays explicit (as today) because the dashboard needs hand-offs and groups; only the way steps are marked and run changes.
- Redis is provided by the operator or the packaged set; no new authentication scheme beyond the Redis address is introduced.
- Only counts and names are recorded, as required by the project's PII rule.
