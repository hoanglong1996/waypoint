# Feature Specification: Rename the Product to Waypoint

**Feature Branch**: `007-rename-to-waypoint`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "I chose the name Waypoint. Create a spec for renaming everything consistently: the library, the dashboard, the deploy bundle, and so on. Change the Redis key prefix too; I will delete the existing Redis data, and every other place (package, README, ...) must be consistent."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A developer adopts the library under its new name (Priority: P1)

A developer of any pipeline installs the Waypoint library, imports it by its new name, and uses the same calls as before (initialise once, mark steps, declare the pipeline). Documentation, examples and warning messages all say Waypoint. Nothing about how it works changes.

**Why this priority**: the library is the part other teams touch in their own code; a half-renamed one (new name in the install command, old name in the import or messages) is the most confusing outcome.

**Independent Test**: in a clean environment, follow the library README from the first line to a running sample pipeline; no step mentions an old name and the sample runs.

**Acceptance Scenarios**:

1. **Given** a clean environment, **When** the developer installs the library by following the README, **Then** the install name, the import name and the README examples all use Waypoint and the sample pipeline runs.
2. **Given** a pipeline that was using the old library name, **When** the developer changes only the install name and the import lines, **Then** it works with no other edit.
3. **Given** the library prints a warning (invalid spec, missing Redis address, Redis unreachable), **When** the developer reads it, **Then** it names Waypoint, not the old name.

---

### User Story 2 - An operator runs Waypoint and sees data under the new key prefix (Priority: P1)

An operator brings up the packaged set (store, dashboard, optional sample pipeline). Every visible name, from the page title to the container, volume and image names, says Waypoint. Pipelines write their records under the new Waypoint key prefix and the dashboard reads only that prefix. Existing data under the old prefix is deleted by the operator and is not migrated.

**Why this priority**: the key prefix is the one change that breaks data compatibility, so it must be right and documented with the cutover order.

**Independent Test**: start the packaged set with the sample pipeline on an empty store; the dashboard shows the sample's graph, and listing keys shows only the new prefix.

**Acceptance Scenarios**:

1. **Given** an empty store, **When** a pipeline runs, **Then** every key it writes starts with the new Waypoint prefix and none with the old prefix.
2. **Given** keys under the old prefix still exist in the store, **When** the dashboard loads, **Then** it ignores them and does not error.
3. **Given** the dashboard is open, **When** the operator looks at the page title, header, footer and empty-state texts, **Then** they say Waypoint.
4. **Given** the operator follows the cutover instructions, **When** they finish, **Then** old keys are gone and new pipelines and the new dashboard work together.

---

### User Story 3 - The rename is complete and verifiable (Priority: P2)

A maintainer searches the repository for the old names and finds none in live code, configuration, tests, documentation, container definitions or comments. Historical records (earlier feature specs and design notes) are the only place the old names may remain, and that is stated.

**Why this priority**: consistency is the whole point of the user's request, and "complete" needs to be checkable.

**Independent Test**: run a search for each old name; the only hits are in the explicitly excluded historical material.

**Acceptance Scenarios**:

1. **Given** the rename is done, **When** the maintainer searches for each old product, library, dashboard and key-prefix name, **Then** no live file contains it.
2. **Given** folders were renamed, **When** the maintainer opens any README, container file or test config, **Then** every path in it points at an existing location.

---

### User Story 4 - CallRail keeps working unchanged (Priority: P2)

The CallRail pipeline, the first adopter, keeps producing the same results and the same dashboard graph; only names change.

**Why this priority**: it proves the rename did not change behaviour.

**Independent Test**: run CallRail's tests and compare its recorded steps and counts with the baseline from before the rename.

**Acceptance Scenarios**:

1. **Given** the rename is done, **When** CallRail's tests run, **Then** they pass and fail exactly as before (the same pre-existing failures, no new ones).
2. **Given** a CallRail run, **When** the dashboard shows it, **Then** step names, counts and graph are identical to before; only the key prefix differs.

---

### Edge Cases

- **Mixed versions during rollout**: an old pipeline still writing the old prefix is invisible to the new dashboard, and a renamed pipeline is invisible to an old dashboard. The cutover order must be documented so the gap is short.
- **Leftover old keys**: they remain until the operator deletes them or they expire; they must never be read or break anything.
- **Browser-stored preferences** (view mode, selected pipeline) saved under old names are lost once; the dashboard falls back to defaults.
- **Other pipelines already adopting the old library name** keep working only until they update the install name and import; the old distribution is no longer published or referenced.
- **Outside references**: deployment definitions outside this repository (job manifests, CI pipelines) may reference old folder, image or variable names and must be updated by their owners; the rename note lists what changed.
- **Name already taken** by another public product or package: the rename must not be released publicly until availability is checked.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product MUST be named **Waypoint** everywhere a name is shown to a person: library, dashboard, deploy bundle, documentation, messages and page text.
- **FR-002**: The library MUST be installable as `waypoint-etl` and imported as `waypoint_etl`; its public behaviour (initialise once, mark steps, declare the pipeline, wrap, test helper) MUST NOT change.
- **FR-003**: The dashboard MUST be called **Waypoint Monitor** (page title, header, documentation, container image name), and its folder MUST be renamed to match.
- **FR-004**: The deploy bundle MUST be called **Waypoint Stack**: the compose project, service, volume and image names MUST use Waypoint naming.
- **FR-005**: Pipelines MUST write, and the dashboard MUST read, records under the key prefix `waypoint:` instead of `etl-audit:`; the key structure after the prefix and the record contents MUST NOT change.
- **FR-006**: The dashboard MUST ignore keys under any other prefix without error, and no data migration MUST be provided (the operator deletes old data).
- **FR-007**: Audit-specific configuration names (currently the record-lifetime setting) MUST use Waypoint naming; generic names such as the Redis address setting MUST stay as they are. All env files and documentation MUST be updated together.
- **FR-008**: Values the dashboard stores in the browser MUST use Waypoint naming; losing the old values once is accepted.
- **FR-009**: Warnings, log lines, comments and error messages MUST use Waypoint naming.
- **FR-010**: No live file (code, tests, configuration, container definitions, documentation, comments) MAY contain the old product, library, dashboard or key-prefix names. Earlier feature specs and design notes are historical and excluded, and so is the rename note itself (it must name the old identifiers so operators can find and delete old data); the rename note MUST say so.
- **FR-011**: All existing tests MUST be renamed and moved with their code and MUST pass and fail exactly as before the rename (no new failures, no silently dropped tests).
- **FR-012**: The library's release tag format and install instructions MUST use Waypoint naming.
- **FR-013**: Availability of the library's install and import names on the public package index MUST be checked before the first tagged release, and the outcome recorded; a name already used there by another project MUST NOT be used (a pipeline that installs by name could otherwise pull the wrong project).
- **FR-014**: A short rename note MUST list every old name and its new name, the operator cutover order (stop old pipelines and dashboard, delete old keys, deploy new), and what owners of outside references must change.
- **FR-015**: The CallRail pipeline MUST be updated to the new library and key prefix with identical step names, counts and graph.

### Key Entities

- **Product name**: Waypoint, the one name used in all user-visible text.
- **Component names**: library `waypoint-etl` (import `waypoint_etl`), dashboard Waypoint Monitor, deploy bundle Waypoint Stack.
- **Key prefix**: the leading segment of every stored key, `waypoint:` after the rename.
- **Rename map**: the table of every old name and its replacement, kept in the rename note.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A search of the repository for each old name returns zero hits outside the explicitly excluded historical material.
- **SC-002**: All test suites report the same passing and failing tests as before the rename (the same pre-existing failures only).
- **SC-003**: Starting the packaged set with the sample pipeline on an empty store shows the sample's graph on the dashboard, and 100% of keys in the store use the new prefix.
- **SC-004**: A developer who already uses the old library name migrates a pipeline by changing only the install name and import lines, in under 10 minutes.
- **SC-005**: 100% of user-visible text (page title, headers, empty states, README titles, warnings) says Waypoint.
- **SC-006**: After the operator completes the cutover instructions, zero keys under the old prefix remain and none are read.
- **SC-007**: CallRail's recorded steps and counts for the same input are identical before and after the rename.

## Assumptions

- Component names follow the earlier suggestion, except the library's install and import names, which were changed after checking the public package index (`waypoint-sdk` is already taken there by an unrelated project, and `waypoint` by another): library `waypoint-etl` imported as `waypoint_etl`, dashboard "Waypoint Monitor", deploy bundle "Waypoint Stack".
- The record format version is unchanged; only the key prefix changes, and the dashboard reads only the new prefix.
- The user deletes the existing Redis data and other stale artefacts themselves, so there is no migration, no dual-prefix support and no backward-compatible alias for the old library name.
- Generic settings (such as the Redis address) keep their names; only audit-specific names change, and the repository's env files are updated in the same change.
- Folders are renamed to match: the library folder and the dashboard folder take Waypoint names.
- Earlier feature specs (001–006) and the design notes under `docs/` stay as history and may still mention old names.
- The library version stays at 0.1.0 because no release has been tagged yet; the first tag uses the new tag format.
- Deployment definitions outside this repository are owned by others and are updated by them using the rename note.
