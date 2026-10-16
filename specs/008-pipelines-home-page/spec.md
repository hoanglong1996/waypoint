# Feature Specification: Pipelines Home Page

**Feature Branch**: `008-pipelines-home-page`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "design a home page, which allow me to manage many pipelines, I can have callrail pipeline, FB pipeline, Google Ads pipeline. when select a pipeline the UI move to the lastest page. In the history page, design a filter which allow me to select a env."

## Clarifications

### Session 2026-10-16

- Q: Should this feature also make the Facebook and Google Ads pipelines report their runs, or only build the home page for pipelines that already report? → A: Home page only. It lists any pipeline that already reports; instrumenting Facebook and Google Ads is a separate feature per pipeline.
- Q: When a pipeline has both prod and qa runs, which run should its home-page card show? → A: The most recent run across all environments, with an environment label on the card.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pick a pipeline from a home page (Priority: P1)

An operator opens Waypoint Monitor and lands on a home page that lists every pipeline being monitored (for example CallRail, Facebook, Google Ads). Each pipeline appears as a card showing its name, the status of its latest run, when that run happened, and its headline counts. Selecting a card opens that pipeline's latest-run page.

**Why this priority**: Without a pipeline list the monitor can only follow one pipeline at a time. This is the entry point for everything else.

**Independent Test**: With recorded runs for three pipelines, open the home page, confirm three cards appear with the correct latest-run status and time, select one and confirm the latest-run page for that pipeline opens.

**Acceptance Scenarios**:

1. **Given** runs exist for CallRail, Facebook and Google Ads, **When** the operator opens the home page, **Then** one card per pipeline is shown with its name, latest-run status, time since the latest run, headline counts and the environment that run belongs to.
2. **Given** the home page, **When** the operator selects a pipeline card, **Then** the latest-run page for that pipeline opens, showing only that pipeline's data.
3. **Given** a pipeline's latest-run page, **When** the operator uses the back control or the product name, **Then** they return to the home page.
4. **Given** a pipeline's latest-run page, **When** the operator reloads the browser or opens its address directly, **Then** the same pipeline's page is shown, not the home page.
5. **Given** a pipeline's latest run is incomplete or lost data, **When** its card is shown, **Then** the card is visibly flagged so problems stand out without opening the pipeline.
6. **Given** the home page, **When** it is shown, **Then** pipelines with problems are listed first, followed by the rest by name.

---

### User Story 2 - Filter a pipeline's history by environment (Priority: P2)

On a pipeline's history page, the operator can choose an environment (for example prod or qa) from a filter. The list of past runs and any step trends then show only that environment's runs for the selected pipeline.

**Why this priority**: Prod and qa runs of the same pipeline are different questions. Mixing them in one history makes trends misleading, but the latest-run page already works without this.

**Independent Test**: With prod and qa runs recorded for one pipeline, open its history, choose "prod" and confirm only prod runs are listed; switch to "qa" and confirm only qa runs are listed.

**Acceptance Scenarios**:

1. **Given** a pipeline's history page, **When** it opens, **Then** an environment filter is visible and shows which environment is applied.
2. **Given** runs exist in several environments, **When** the operator selects one environment, **Then** the history lists only that environment's runs, newest first.
3. **Given** a selected environment, **When** the operator opens a run or a step trend, **Then** it is limited to that environment.
4. **Given** the operator changes the filter, **When** they reload the page or share its address, **Then** the same environment is still applied.
5. **Given** the selected environment has no runs for this pipeline, **When** the history is shown, **Then** a clear "no runs in this environment" message appears and the filter stays usable.
6. **Given** the address asks for an environment with no runs for this pipeline, **When** the history opens, **Then** that environment is still shown as applied, with a "no runs" hint, and the page says "No runs in this environment".

---

### User Story 3 - See new and quiet pipelines without configuration (Priority: P3)

When a pipeline records its first run it appears on the home page without anyone editing a list. A pipeline that has stopped reporting is shown as stale instead of disappearing.

**Why this priority**: It keeps the home page trustworthy as pipelines are added, but a fixed list would still deliver stories 1 and 2.

**Independent Test**: Record a first run for a new pipeline and confirm its card appears on the next refresh; leave a pipeline without runs past its expected interval and confirm its card is marked stale.

**Acceptance Scenarios**:

1. **Given** a pipeline records its first run, **When** the home page refreshes, **Then** a card for it appears.
2. **Given** a pipeline's latest run is older than expected, **When** its card is shown, **Then** it is marked as stale with the time since the run.
3. **Given** the home page stays open, **When** the periodic refresh runs, **Then** cards update and the time of the last update is shown.

---

### Edge Cases

- No pipeline has recorded a run: the home page shows a friendly empty state explaining that pipelines appear after their first run.
- The data store is unreachable: the home page shows a clear error with a retry option rather than a blank or broken page.
- Some stored records cannot be read: readable pipelines are still shown, with a notice that some data was skipped.
- A pipeline address that matches no known pipeline: a "pipeline not found" page links back to the home page.
- A pipeline exists in only one environment: the history filter lists only environments that have runs for that pipeline.
- Pipeline names are long or numerous (for example twenty or more): cards stay readable and the page stays scrollable, with no overlap.
- Only one environment exists overall: the filter is still shown so the applied environment is clear.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a home page that is the default landing page of the monitor.
- **FR-002**: The home page MUST list every pipeline that has recorded at least one run, one card per pipeline.
- **FR-003**: Each card MUST show the pipeline name, the status of its latest run (completed, incomplete, lost data, or stale), the time since that run, its headline counts and a label naming the run's environment. The latest run is the most recent run across all environments.
- **FR-004**: Selecting a card MUST open that pipeline's latest-run page, scoped to that pipeline only.
- **FR-005**: Every pipeline page MUST have a visible way back to the home page.
- **FR-006**: Each page, including each pipeline's latest-run and history pages, MUST have its own address, so reloading, bookmarking and sharing return to the same view.
- **FR-007**: Pipelines with a problem (Stale, Incomplete or Lost data) MUST be listed before the others in their own titled group, and each group MUST be ordered by name.
- **FR-008**: The pipeline history page MUST provide an environment filter listing the environments that have runs for that pipeline.
- **FR-009**: Applying the environment filter MUST restrict the run list, run details and step trends to that environment.
- **FR-010**: The selected environment MUST be kept in the page address and MUST survive reloads.
- **FR-011**: The history page MUST open with a sensible default environment (see Assumptions) and always show which one is applied, with a note saying how many runs of it are shown.
- **FR-012**: New pipelines MUST appear on the home page automatically, with no manual registration.
- **FR-013**: The home page MUST refresh periodically and show when it was last updated.
- **FR-014**: The home page MUST show clear empty, error and partial-data states instead of a blank or broken page.
- **FR-015**: The home page and the filter MUST be usable with a keyboard only and on phone-width screens.

### Key Entities

- **Pipeline**: A named ETL job whose runs are monitored (for example CallRail, Facebook, Google Ads). Has a name, one or more environments and a set of runs.
- **Run**: One execution of a pipeline in one environment. Has a time, a status and per-step counts.
- **Environment**: The deployment a run belongs to (for example prod or qa).
- **Pipeline Summary**: What a home-page card shows: the pipeline name, the latest run's status, environment, time and headline counts, and whether it is stale.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From opening the monitor, an operator can reach any pipeline's latest-run page in two selections or fewer.
- **SC-002**: An operator can tell which pipelines need attention from the home page alone, without opening any pipeline, in under 10 seconds for up to 20 pipelines.
- **SC-003**: Filtering a history by environment takes one selection and shows the result in under 1 second for 30 runs.
- **SC-004**: 100% of runs shown after applying an environment filter belong to the chosen environment.
- **SC-005**: A newly reporting pipeline appears on the home page within one refresh interval, with no manual step.
- **SC-006**: In a first-use check, at least 90% of operators find the history page and apply an environment filter without guidance.

## Assumptions

- The monitor already identifies runs by pipeline name and environment (features 005 and 007), so the home page groups existing records and needs no new recording format.
- The existing global prod/qa selector is replaced by the history page's environment filter. The latest-run page opens on the run the card showed, so it matches the card's environment.
- The history filter defaults to prod when that pipeline has prod runs, otherwise to the most recent environment.
- "Stale" means the latest run is older than the expected interval already used by the monitor's stale-run warning.
- A card shows three numbers from the run's own steps: the first step, the largest step between the first and the last, and the last step (a step that has not reported shows "—"). They are named by the step, so no pipeline-specific wording is built in.
- A card's status, first match wins: Running, Stale (older than the stale-run limit), Incomplete (stopped or stalled), Lost data, Completed. Stale, Incomplete and Lost data are the "problems" that need attention.
- The environment filter lists environments with runs, prod first then A to Z. If the address asks for an environment with no runs, it is still shown (with a "no runs" hint) and the history shows "No runs in this environment". Changing the filter adds a browser history entry.
- The visual design is `docs/design/waypoint-monitor/` (home page, pipeline header, environment tag, filter). Where it and this spec differ, the design is followed and this spec is updated to match.
- Only pipelines that already record runs appear on the home page. Making Facebook and Google Ads report their runs is out of scope here and is done as separate features; until then they are absent, and review of their cards uses demo data.
- Operators can only view; creating, renaming, hiding or deleting pipelines from the page is out of scope.
- Access control, sign-in and user-specific saved views are out of scope for this feature.
- The existing look of Waypoint Monitor is reused for the new pages.
