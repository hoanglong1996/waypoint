# Research: Pipelines Home Page

Findings marked "read" come from the code on 2026-10-16.

## 1. How pages get their own addresses

- **Decision**: Hash routes (`#/`, `#/p/<pipeline>`, `#/p/<pipeline>/history?env=prod`).
- **Rationale**: The monitor is a static page served by one FastAPI app. Hash routes work for reload, bookmark
  and sharing (FR-006) with no server fallback rule and no change to the container. Matches the no-build-step
  front end.
- **Alternatives considered**: History API paths (`/p/callrail`): cleaner, but needs the server to return the
  page for every path and care with asset paths. Query-only routing (`?pipeline=`): works, but mixes page and
  filter state.

## 2. Where the home-page data comes from

- **Decision**: New read-only `GET /api/overview` returning one summary per pipeline.
- **Rationale**: Read: today the browser calls `/api/pipelines` per environment and `/api/runs` per pipeline
  and environment. For 20 pipelines and 2 environments that is 40+ requests every 5 s. The server already
  builds runs for each (env, pipeline) with a 2 s cache, so one endpoint is cheaper and keeps the
  "newest across environments" rule in one tested place.
- **Alternatives considered**: Browser fan-out (simple, but request count grows with pipelines). Extending
  `/api/pipelines` (its shape is used per environment today; changing it risks the existing picker tests).

## 3. "Newest run across environments" for a card

- **Decision**: For each pipeline, build runs per configured environment and take the run with the greatest run
  id (`YYYYMMDDTHHMMSSZ`, sorts by time). Ties go to the environment listed first in `ENVIRONMENTS`.
- **Rationale**: Read: the front end already merges and sorts by run id, so cards and the Latest page agree.
  Spec clarification: the card shows the newest run in any environment with an environment label.

## 4. Environment filter on History

- **Decision**: The filter offers environments that have runs for that pipeline, prod first then A to Z (from
  the overview). The History page fetches `/api/runs?env=<chosen>`; no "all" option. Default: `prod` if present,
  else the environment of the newest run. The choice lives in the address (`?env=`). An address asking for an
  environment with no runs is kept and shown with a "no runs" hint (design, section 15). Changing the filter
  adds a history entry.
- **Rationale**: Spec FR-008 to FR-011 and the approved design. Read: `/api/runs` already takes one
  environment, so no server change for filtering. Latest keeps the merged view so it matches the card.
- **Alternatives considered**: Client-side filtering of merged runs (loses runs when one environment fills the
  30-run window). Correcting a bad `?env=` silently (hides what the address asked for).

## 5. Card status, ordering and headline

- **Decision**: Status, first match wins: Running, Stale, Incomplete (stopped or stalled), Lost data, Completed.
  Attention group = Stale, Incomplete, Lost data, listed first; each group A to Z. Headline = first step, largest
  step between first and last, last step of the run's own flow. All computed on the server from existing run
  fields.
- **Rationale**: The approved design (`docs/design/waypoint-monitor/DESIGN_NOTES.md` sections 13 and 17). This
  replaces the earlier plan to rank problems by severity and to reuse the Latest hero's first/peak/last rule.
- **Consequence**: the card's "largest step" can differ from the Latest hero's "Largest step" (which looks at all
  reported steps). The design chose this on purpose; the card names the step so it stays readable.

## 6. Stale threshold (open item from clarify)

- **Decision**: Reuse `STALE_HOURS` (default 26 h), already exposed as `stale` on each run.
- **Rationale**: Read: `analysis.py` sets `stale` when a non-running run is older than `stale_hours`.
  One threshold for the banner and the card avoids two answers to the same question.

## 7. Card headline counts

- **Decision (superseded by section 5)**: Reuse the front end's `headline(run)` (first step, largest step, last step) and send the three
  values through the overview, so cards need no step names.
- **Rationale**: Read: `model.js` already derives the same three numbers for any pipeline from its own flow.
  This satisfies the spec assumption for pipelines that are not CallRail.

## 8. Facebook and Google Ads

- **Decision**: Not instrumented here (clarification 2026-10-16). The home page lists whatever reports; review
  of their cards uses `python -m tests.seed_demo` data.
- **Rationale**: Out of scope per spec. The seed script gets extra demo pipelines so the design can be seen.
