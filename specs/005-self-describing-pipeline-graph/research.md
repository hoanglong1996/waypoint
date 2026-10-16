# Research: Self-Describing Pipeline Graph

Date: 2026-10-16. Read from the current source (`step_audit.py`, `redis_step_audit.py`, monitor `app/` and `static/js/graph-model.js`).

## R1. Key layout and pipeline discovery
- **Decision**: `etl-audit:{pipeline}:{env}:{run_id}:flow`, `...:step:{NN}-{step}`, `...:running:{NN}-{step}`. Pipeline names match `[a-z0-9][a-z0-9_-]{0,39}` (no colon). Discovery = `SCAN etl-audit:*:{env}:*:flow` and read the pipeline segment; step and marker scans reuse the same pattern per pipeline.
- **Rationale**: one common root makes discovery automatic (clarification 2) and cannot collide with the old `callrail:*` keys, which are then ignored for free (clarification 3). Putting the pipeline before env keeps per-pipeline scans cheap.
- **Alternatives**: a Redis set of pipeline names (extra write, can go stale, TTL handling); a `pipelines` config in the monitor (rejected in clarification); keeping `callrail:audit` and adding a field (cannot tell pipelines apart without reading every value).

## R2. Where the flow description lives
- **Decision**: one JSON value per run under `...:flow`, written once at run start by the auditor with the same TTL as step records. Declared once in code as a `PipelineSpec` (clarification 5).
- **Rationale**: a run that fails before any step still has a known flow (FR-002); each run carries its own description so no cross-run logic (clarification 4); one key keeps the monitor read to one `MGET`.
- **Alternatives**: per-step self-announcement (rejected, clarification 5); one global description per pipeline (cannot show changed steps for older runs).

## R3. Format versioning
- **Decision**: `"v": 1` in the flow value. The monitor accepts only known versions, treats an unknown one as an invalid description (simplified graph + visible problem, FR-009). Unknown extra fields are ignored.
- **Rationale**: lets the contract grow without breaking viewers.

## R4. Validation and bad input
- **Decision**: validate in two places with the same rules: the pipeline rejects an invalid `PipelineSpec` at construction (duplicate step names, input from unknown step, bad name chars) and logs, then runs without a flow (audit stays non-fatal); the monitor re-validates stored data and keeps the valid part (dangling input kept as a flagged edge, cycle flagged, oversize text truncated).
- **Rationale**: spec FR-009 and edge cases; the monitor can never trust stored data.

## R5. Automatic layout
- **Decision**: client-side layered layout: layer = longest path from sources over the hand-off edges (cycle edges dropped and flagged); rows within a layer ordered by average row of producers (barycenter), ties by declared order. Optional hints `col`/`row` per step override. Groups render as node colour and tag; the LR bands are drawn only for groups whose steps sit in contiguous layers.
- **Rationale**: replaces `POSITIONS`/`GROUP_NAME` and the special-cased skip edge and chip staggering in `layoutLR`/`layoutTB` (which name `read_instances` etc. directly). Generic rule: an edge spanning more than one layer runs straight through its source row and bends only in the last gap (today's LR behaviour); the TB layout is the same model transposed with a single-lane-per-row fallback.
- **Alternatives**: a graph library (new dependency, no CDN rule in docs, bigger than needed for ≤50 nodes); server-side layout (monitor must stay thin and layout depends on viewport).
- **Risk**: crowded graphs above ~30 steps; mitigated by horizontal scroll in the panel and the List view remaining available (SC-006 reviewed with a 30-step sample).

## R6. Simplified graph for runs without a description
- **Decision**: steps from the records and markers in `index` order, no hand-off edges, a "No flow description" note. The monitor holds no step list (clarification 1, FR-008).

## R7. Monitor API shape
- **Decision**: `/api/pipelines?env=` lists discovered pipelines (name, last run id); `/api/runs?env=&pipeline=` returns runs, each with its own `flow` (label, groups, steps, hints, `flow_status`: `ok|missing|invalid`) and per-step state as today. `/api/config` loses `expected_steps`. Cache stays per `(env, pipeline)`.
- **Rationale**: a run response is self-contained, so the front end needs no config lookup for steps.

## R8. Reference pipeline
- **Decision**: CallRail declares its nine steps in `src/application/pipeline_spec.py`; `application.py` keeps its `audit(...)` calls, but names now must match the spec (the auditor rejects an unknown step name by logging a warning, since it cannot place the record).
- **Rationale**: single source of truth in the pipeline; the duplicate in the monitor goes away.

## Measured layout (2026-10-16, from `node --test`)

30-step generated flow, 33 edges: 0 node overlaps and 0 edges through a non-endpoint node in left-to-right, compact and top-to-bottom layouts, laid out in 0.3-0.5 ms. 50 steps (59 edges): 0.5 ms, 0 overlaps, 0 crossings. 100 steps lay out without overlaps (SC-006 evidence).
