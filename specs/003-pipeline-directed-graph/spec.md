# Feature Specification: Pipeline Directed Graph View

**Feature Branch**: `003-pipeline-directed-graph`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "the web app show the data pipeline is quite good, but I want it showing under directed graph, which indicate the relationship of each steps and output of this step is the input of another step."

## Clarifications

### Session 2026-10-15

- Q: Which visual design should the graph follow? → A: The approved prototype in `docs/design/pipeline-monitor-graph-update` (notes in `DESIGN_NOTES.md` §8, screenshots in `screenshots/graph/`); where this spec and the prototype differed, this spec has been aligned to the prototype.
- Q: Which view opens by default? → A: Graph. (The prototype opens in List; this is a deliberate deviation. The choice is remembered once the user changes it.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See how data flows between steps (Priority: P1)

An operator viewing a pipeline run sees the steps drawn as a directed graph instead of a flat ordered list. Each step is a node; an arrow from step A to step B means "A's output is B's input". Arrows are labelled with the data they carry and its item count (for example "accounts · 10"). Steps that start the pipeline (no input) appear as sources on one side and the final steps as sinks on the other, so the whole flow reads in one direction. A one-line header says how to read it ("Data flows left to right. An arrow A → B means A's output is B's input") and a summary line says how many of the 9 steps reported and names any stop or data-loss step. A legend explains step states, arrow styles and groups. Steps that need several inputs (for example the merge step taking calls, campaigns and click data) visibly receive several arrows.

**Why this priority**: This is the whole request: the operator can tell at a glance which step feeds which, rather than inferring it from step order.

**Independent Test**: Open any run that has stored step records and confirm every step is a node, every named input has an arrow from the step that produces it, and the counts on arrows equal the stored counts.

**Acceptance Scenarios**:

1. **Given** a complete run, **When** the operator opens the graph view, **Then** each of the pipeline's steps appears once as a node and arrows connect each producing step to every step that consumes its output.
2. **Given** a step with several named inputs, **When** displayed, **Then** it shows one incoming arrow per input, each labelled with the input name and count.
3. **Given** two independent branches (for example the CallRail branch and the Google Ads branch), **When** displayed, **Then** they appear as separate paths that join at the step that consumes both.
4. **Given** the graph, **When** the operator reads it left to right (or top to bottom on phones), **Then** every arrow points forward, with no loops and no crossing arrows.
5. **Given** arrows carrying different counts, **When** displayed, **Then** thicker arrows carry more items (log scale relative to the largest count in the run).

---

### User Story 2 - Spot where data was lost or a run stopped, on the graph (Priority: P1)

Node and arrow states carry the same health information the list already shows, with a little more detail: **Fine**; **Data loss** (inputs present but zero output); **Not reported** (the first step missing from the run, where it stopped); **Not reached** (later missing steps). A fine step downstream of a data-loss step also gets an "affected" badge. A problem is visible on the graph itself, and the operator can follow the arrows downstream to see what was affected.

**Why this priority**: Showing relationships is only useful for monitoring if problems stay visible; this is how operators find the first break and its downstream impact.

**Independent Test**: Display a run with one lost-data step and a run that stopped part-way; confirm the nodes are marked distinctly (not by colour alone), later missing steps show "Not reached", and steps downstream of the loss show "affected".

**Acceptance Scenarios**:

1. **Given** a step whose input count is above zero and output is zero, **When** displayed, **Then** its node is flagged "Data loss", its outgoing arrows show 0, and fine steps downstream of it carry an "affected" badge.
2. **Given** a run that stopped part-way, **When** displayed, **Then** the first missing step is drawn as "Not reported", later missing steps as "Not reached", and arrows into or out of missing steps are drawn inactive with "—" as their label.
3. **Given** a step that returns nothing, **When** displayed, **Then** it shows "n/a" and "returns nothing" rather than a zero, and has no outgoing data arrow.

---

### User Story 3 - Explore a step and its neighbours (Priority: P2)

The operator can select a node to open a "Selected step" panel (the same step card as the list: counts, finish time, trend) with Upstream and Downstream links that jump to neighbouring steps, while the direct neighbours are highlighted and the rest of the graph is dimmed. Hovering or focusing a node or arrow shows a tooltip with its inputs, source steps, output, time and state. The operator can switch between the graph and the existing list view, and the choice is remembered.

**Why this priority**: Makes the graph useful for investigation, but the static graph already delivers the main value.

**Independent Test**: Select a node and confirm its direct neighbours are highlighted and its details match the list view; switch to list and back.

**Acceptance Scenarios**:

1. **Given** the graph, **When** the operator selects (click, Enter or Space) a node, **Then** the Selected step panel opens and its direct upstream and downstream steps and connecting arrows are highlighted.
2. **Given** a selected node, **When** the operator clicks it again, presses Escape or clicks empty graph space, **Then** the selection clears; Escape returns focus to that node.
3. **Given** the History drawer is open with a selected node, **When** the operator presses Escape once, **Then** only the selection clears; a second Escape closes the drawer.
4. **Given** the operator switches to the list view and reloads, **When** the page opens, **Then** the last chosen view is shown.
5. **Given** a past run opened from History, **When** displayed, **Then** it can be shown as the same graph (compact layout) with that run's counts, using the same List | Graph choice.

### Edge Cases

- A step is missing from the run: its node still appears (as Not reported or Not reached) so the graph shape never changes between runs.
- A step's record is unreadable: treated as not reported and counted in the existing "could not be read" notice.
- A step with zero outgoing items: the arrow is drawn as "0" with short red dashes and flagged.
- A step that returns nothing but has no downstream consumer (final steps): shown as a sink with no outgoing arrow.
- Narrow screens (375 px): the graph flows top to bottom in two lanes, readable without any horizontal scrolling.
- Loading: a skeleton graph in the real layout. No runs: a ghost graph (names, no counts) with "No runs yet for <env>". Data store unreachable: the existing error card replaces the graph.
- Dark and light appearance: nodes, arrows and labels remain legible in both.
- Stored records carry no information about which step feeds which; relationships come from the pipeline's known structure, so a step unknown to that structure is still shown, unconnected, in a separate "Other steps" row under the graph rather than hidden.
- Dashboard stays read-only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST present a run's steps as a directed graph with one node per pipeline step and one arrow per producer→consumer data relationship (9 steps, 9 arrows).
- **FR-002**: Each arrow MUST be labelled with the name of the data it carries and its item count for the displayed run, matching the stored counts exactly. In the compact layout (see FR-009) the labels MAY appear only in the hover/focus tooltip.
- **FR-003**: The graph MUST be acyclic with no crossing arrows, laid out so all arrows point in one consistent direction, sources (no input) first and final steps last.
- **FR-004**: Every node MUST show a friendly name, step name, output count (or "n/a · returns nothing"), finish time and one health state: Fine, Data loss, Not reported (first missing step) or Not reached (later missing steps), using icon and text in addition to colour; missing nodes also use a dashed hatched style. A Fine node downstream of a Data-loss node MUST also carry an "affected" badge.
- **FR-005**: Arrow state MUST be: normal (solid, thickness growing with count on a log scale relative to the run's largest count), empty (count 0, short red dashes, label "0"), or inactive (producer or consumer missing, grey long dashes, label "—"). States differ by pattern as well as colour.
- **FR-006**: The graph MUST keep the same nodes and arrows for every run; only counts and states change.
- **FR-007**: The user MUST be able to select a node (click, Enter, Space) to highlight it and its direct upstream and downstream nodes and arrows (others dimmed) and open a "Selected step" panel that reuses the list's step card and links to upstream and downstream steps. Clicking the node again, Escape, or clicking empty graph space MUST clear the selection. In the History drawer the first Escape clears the selection and the second closes the drawer.
- **FR-008**: Hovering or focusing a node MUST show a tooltip with inputs and their source steps, output, finish time and state; hovering an arrow or its label MUST show `producer → consumer` and `input · count`.
- **FR-009**: The layout MUST depend on the graph panel's width: 880 px and wider, left-to-right full layout; 600–879 px (and the History drawer), left-to-right compact layout; under 600 px, top-to-bottom in two lanes. There MUST be no horizontal page scrolling from 375 px up, and the selection MUST survive resizing.
- **FR-010**: The user MUST be able to switch between Graph and List with a "List | Graph" control on the latest-run view and in the History drawer, sharing one remembered choice; Graph is the default.
- **FR-011**: The graph MUST be available for the latest run and for any run opened from History, and MUST keep the user's selection through the automatic refresh.
- **FR-012**: Which step feeds which step, and each step's group, MUST come from the pipeline definition the dashboard already receives, not be inferred from stored records. Node positions and friendly names are a single front-end table keyed by step name. A step not in that table MUST still be shown, unconnected, in an "Other steps" row.
- **FR-013**: The graph MUST show a header explaining the direction and the arrow meaning, a summary line (steps reported, stop point, loss point) and a legend of states, arrow styles and groups.
- **FR-014**: The graph MUST have a loading state (skeleton graph in the real layout) and an empty state (ghost graph with "No runs yet for <env>"); the existing unreachable-data error card MUST replace the graph as it does the list. Headline numbers, stale warning, unreadable-record notice and read-only access MUST be unchanged.
- **FR-015**: The graph MUST support light and dark appearance, be keyboard operable (Tab order column by column, top to bottom; visible focus; each node has a full accessible label), and disable the flow animation under reduced-motion preferences and while a node is selected.

### Key Entities

- **Step Node**: A pipeline step in a run, with friendly name, group, output count, health state (Fine, Data loss, Not reported, Not reached), "affected" flag and finish time.
- **Data Link**: A directed relationship from a producing step to a consuming step, carrying a data name, an item count and a state (normal, empty, inactive) for a given run.
- **Pipeline Structure**: The description of which steps exist, their groups, and which step's output feeds which step's inputs (from the dashboard's pipeline definition), plus the front-end table of positions and friendly names.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can name which step(s) feed any given step within 5 seconds of looking at the graph, without reading step order.
- **SC-002**: 100% of arrow and node counts shown match the stored records exactly.
- **SC-003**: An operator can identify the first broken step (Not reported or Data loss) and the steps downstream of it (Not reached or affected) within 10 seconds.
- **SC-004**: The graph view is fully displayed within 3 seconds, matching the existing list view's load time.
- **SC-005**: 100% of pipeline data relationships (every named input of every step) appear as an arrow in the graph, and the graph shows no crossing arrows in any layout.

## Assumptions

- The graph is an additional view of the existing dashboard (alongside the list), not a separate application.
- The set of steps and their relationships is fixed and known (9 recorded steps, as defined by the Pipeline Step Audit Trail feature); the graph is not discovered from stored data, and adding a step needs a new entry in the front-end position table as well.
- Stored records stay unchanged: they hold named input counts and one output count per step, so the count on an arrow is the consumer's recorded input count (the producer's output count is shown on the node).
- Visual style follows the approved graph design in `docs/design/pipeline-monitor-graph-update`, built on the existing design (colours, status icons, light/dark themes). New design tokens are `--grp-*` (+ `-bg`) and `--edge*`.
- No editing, panning or zooming of the graph; larger layouts are scaled to fit the panel.
- Real data drives all states; the prototype's preview switcher, mock data and `?state=`/`?select=` parameters are not carried over.
