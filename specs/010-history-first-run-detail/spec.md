# Feature Specification: History-First Pipelines with Run Detail Pages

**Feature Branch**: `010-history-first-run-detail`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "when click a pipeline, the default page is history, and latest page convert to detailed page, when click a run, it show its detailed page not showing the right pannel"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A pipeline opens on its history (Priority: P1)

An operator selects a pipeline, either from a card on the home page or from a direct address, and lands on that pipeline's history page: the list of past runs (and step trends) with the environment filter. The history is the first thing they see, so they can scan recent runs and spot problems before choosing one to look into.

**Why this priority**: This is the entry point the operator asked to change. Every pipeline visit now starts here, and the other stories build on it.

**Independent Test**: With recorded runs for a pipeline, select its card on the home page and confirm the history page opens, listing that pipeline's runs newest first.

**Acceptance Scenarios**:

1. **Given** the home page, **When** the operator selects a pipeline card, **Then** that pipeline's history page opens, not a latest-run page.
2. **Given** an address that points at a pipeline without naming a page (for example an older bookmark), **When** it is opened, **Then** the pipeline's history page is shown.
3. **Given** a pipeline's history page, **When** the operator reloads the browser or opens its address directly, **Then** the same history page is shown, with the same environment filter applied.
4. **Given** a pipeline's history page, **When** it is shown, **Then** the page offers no separate "Latest" page to switch to; the most recent run is simply the first row of the list.
5. **Given** a pipeline with no recorded runs in the applied environment, **When** its history opens, **Then** the existing "no runs in this environment" message appears and the filter stays usable.

---

### User Story 2 - A run opens as its own detail page (Priority: P1)

When the operator selects a run in the history list, the monitor navigates to a full detail page for that run instead of sliding a panel in on the right. The detail page shows what the former latest-run page showed (run status, summary counts, the flow of steps and the per-step timeline) but for the chosen run, and the history list is no longer visible behind it.

**Why this priority**: This is the second half of the request: the "latest" content becomes the run detail page, and the right-hand panel goes away. Without it, the history page has no way to open a run.

**Independent Test**: From a pipeline's history, select an older run and confirm a full page opens showing that run's status, counts and steps, with no side panel, and that the back control returns to the history.

**Acceptance Scenarios**:

1. **Given** a pipeline's history page, **When** the operator selects a run, **Then** a full detail page for that run opens and no right-hand panel appears.
2. **Given** a run's detail page, **When** it is shown, **Then** it presents the same information the latest-run page showed (status, headline counts, step flow and step timeline) for that specific run, including the List | Graph choice for the steps.
3. **Given** a run's detail page, **When** the operator uses the back control, **Then** they return to the pipeline's history with the same environment filter that was applied.
4. **Given** a run's detail page, **When** the operator reloads the browser or opens its address directly, **Then** the same run's detail page is shown, not the history.
5. **Given** a run's detail page, **When** the page is shown, **Then** the pipeline name and the run's environment are visible so the operator knows which run they are looking at.
6. **Given** a run that is still in progress, **When** its detail page is open, **Then** it keeps updating on the same periodic refresh the former latest page used.
7. **Given** an address for a run that does not exist (deleted, expired or mistyped), **When** it is opened, **Then** a "run not found" page appears with a link back to that pipeline's history.

---

### User Story 3 - The latest run is one selection away (Priority: P2)

Operators who only care about the newest run can still reach its detail page quickly: it is the top row of the history list, and selecting it opens its detail page like any other run. Pipeline cards on the home page keep showing the latest run's status, time and counts.

**Why this priority**: Removing the Latest page must not make the most common question ("how did the last run go?") harder than one click from the history.

**Independent Test**: Open a pipeline's history and confirm that selecting the first row opens the detail page of the most recent run in the applied environment.

**Acceptance Scenarios**:

1. **Given** a pipeline's history, **When** the operator selects the first (newest) run, **Then** that run's detail page opens and matches what the home-page card summarised.
2. **Given** a new run is recorded while the history page is open, **When** the periodic refresh runs, **Then** the new run appears at the top of the list without losing the operator's place or environment filter.

---

### Edge Cases

- The run being viewed is removed from the data store while its detail page is open: the page shows "run not found" with a link back to the history, rather than staying blank or showing stale data.
- A run's environment differs from the history filter that was applied when the operator reached it (for example via a shared address): the detail page still opens, and the back control returns to the history of that run's pipeline.
- Some stored data for a run cannot be read: the detail page shows what is readable with the same unreadable-data notice used elsewhere.
- Browser back and forward move between home, history and run detail pages in the order the operator visited them.
- Older bookmarks to the former latest page (a pipeline address with no page named) keep working and land on history.
- Narrow screens: the detail page uses the full width; there is no side panel to squeeze content.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Selecting a pipeline (from a home-page card or an address that names only the pipeline) MUST open that pipeline's history page.
- **FR-002**: The pipeline page MUST NOT offer a separate "Latest" page; the history page is the pipeline's only list view.
- **FR-003**: Selecting a run in the history list MUST navigate to a full detail page for that run; no side panel or overlay may be used to show run details.
- **FR-004**: The run detail page MUST show the content previously shown on the latest-run page (run status, headline counts, step flow, step timeline and the List | Graph choice) for the selected run.
- **FR-005**: Every run detail page MUST have its own address, so that reloading it, opening it directly or sharing it shows the same run.
- **FR-006**: The run detail page MUST provide a back control that returns to the pipeline's history with the environment filter that was applied when the run was opened.
- **FR-007**: The run detail page MUST identify the pipeline and the run's environment and start time.
- **FR-008**: A run detail page for a run still in progress MUST keep refreshing periodically and show when it last updated, as the latest-run page did.
- **FR-009**: An address for a run that cannot be found MUST show a "run not found" page with a link back to the pipeline's history.
- **FR-010**: The environment filter on the history page MUST keep working as before and MUST stay in the address.
- **FR-011**: Home-page cards MUST keep showing the latest run's status, time, counts and environment, unchanged by this feature.
- **FR-012**: Existing addresses for a pipeline (with or without the history page named) MUST keep resolving, both landing on the history page.
- **FR-013**: Browser back and forward MUST move between home, history and run detail pages in visit order.
- **FR-014**: The page title MUST follow the current page (home, history or run detail) as it does today.

### Key Entities

- **Pipeline**: A monitored ETL job (for example CallRail). Opens on its history.
- **Run**: One recorded execution of a pipeline in one environment, with a status, counts, steps and a start time. Identified so that it can be addressed individually.
- **Run detail page**: The full-page view of one run, replacing both the former latest-run page and the right-hand run-details panel.
- **History**: The list of a pipeline's runs for the applied environment, newest first, with step trends.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From the home page, an operator reaches a pipeline's history in one selection, and reaches any listed run's detail page in two selections in total.
- **SC-002**: In 100% of pipeline visits, the first page shown is the history; no visit lands on a latest-run page.
- **SC-003**: Opening a run shows no side panel on any screen size; the run's content uses the full page width.
- **SC-004**: Reloading or sharing the address of any history page or run detail page shows the same page for 100% of runs that still exist.
- **SC-005**: Operators can get from a pipeline's history back to the same history (same environment filter) after viewing a run in one selection.
- **SC-006**: The newest run's detail page is reachable from a pipeline's history in one selection.

## Assumptions

- The "latest" page and the "run detail" content are the same layout; the existing latest-run presentation is generalised to any run rather than redesigned.
- The history page keeps its current content (step trend, runs list, environment filter); only how a run is opened changes.
- The home page and its cards are unchanged, except that selecting a card now opens history instead of the latest page.
- A run is addressable by the identifier it already has in the data store; no new run identifiers are introduced.
- Run detail pages update on the same refresh interval the monitor already uses; no new live-update mechanism is added.
- Older addresses that named the pipeline only continue to work and land on history; no redirect notice is shown.
- No new environments, authentication or data are involved; this is a navigation and page-structure change within the existing monitor.
