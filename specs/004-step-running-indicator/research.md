# Research: Live Step Running Indicator

## 1. How does the monitor know a step is running?

- **Decision**: `StepAuditor.run` writes a start marker (separate Redis key family `callrail:running:...`) before calling the step function. The monitor treats a marker with no finish record for the same run and step as "running".
- **Rationale**: Today a record exists only after a step finishes (`step_audit.py`), so running cannot be inferred. A separate key prefix keeps the existing `callrail:audit:<env>:*` scan and parser untouched, so markers never count as "unreadable records" and old monitor versions ignore them.
- **Alternatives**: (a) write the marker under the finish key and overwrite on completion — breaks the strict record validator and makes `output` nullable semantics ambiguous; (b) a single "current run" key — loses history and overlaps badly when two runs overlap; (c) infer running from "first missing step of a fresh run" — cannot distinguish running from crashed.

## 2. Cleanup of markers

- **Decision**: markers are never deleted; they expire after 24 h (constant), and the monitor ignores a marker once the finish record exists. The monitor stays read-only.
- **Rationale**: the store protocol only has `write`; a delete would add a second failure path in the pipeline and the finish record already supersedes the marker.
- **Alternatives**: delete marker on finish (extra Redis call, fails silently leaving a stale marker anyway); long TTL equal to audit (30 d, pointless clutter).

## 3. Stalled and crashed steps

- **Decision**: `stalled` when `now - started_at > STALL_SECONDS` (default 900, monitor setting). A stalled step counts as the run's stop point (`first_missing_step`) and is not animated. A crash leaves the marker in place, so the step is shown Running until the limit and Stalled afterwards, until the 24 h marker TTL removes it (then plain "Not reported").
- **Rationale**: no extra "failed" write needed; matches User Story 3.
- **Alternatives**: write a "failed" marker in an `except` block (more precise, but extra pipeline change not requested; revisit later).

## 4. Which steps are "Waiting"

- **Decision**: when a run has a live (non-stalled) running step, steps with no record and no marker whose definition index is greater than the running step's index are `waiting`. Earlier missing steps stay `missing`. The pipeline executes steps in definition order, so this is exact.
- **Rationale**: avoids marking a skipped earlier step as merely waiting.
- **Alternatives**: all missing steps are waiting (hides a real gap before the running step).
- **Known gap**: between a step finishing and the next marker (microseconds) a run has no running step; at a 5 s poll this is very unlikely and self-heals on the next poll.

## 5. Run status and stale

- **Decision**: `status` gains `"running"` (at least one live running step); `stale` is `false` while running. `ended_at`/`duration_seconds` use the last finish record as today.
- **Rationale**: FR-010 — an in-progress run must not look stale or stopped.

## 6. Polling every 5 seconds without flicker

- **Decision**: default `REFRESH_SECONDS` becomes 5. The client computes a signature of the runs payload ignoring volatile counters (`age_seconds`, `elapsed_seconds`, `generated_at`) and skips `render()` when unchanged, only updating the "Updated" indicator. Elapsed time ticks locally every second from the server-provided `elapsed_seconds` plus time since fetch (clamped at 0), which avoids browser/server clock skew.
- **Rationale**: `render()` rewrites `innerHTML`, which would restart CSS spinner animations every 5 s and drop focus; the signature gate fixes both. Selection and view already survive refresh (spec 003 FR-011).
- **Alternatives**: DOM diffing library (overkill); Server-Sent Events/WebSocket (more infra; the user asked for an interval reload).

## 7. Server cache vs 5 s polling

- **Decision**: `CACHE_SECONDS` default 10 → 2. A 10 s cache would delay updates beyond 5 s (SC-002). A 2 s cache still coalesces several viewers into one Redis scan per 2 s.
- **Rationale**: ~270 keys per env; one SCAN+MGET per 2 s is negligible. Markers are read in the same cached window.

## 8. Visual treatment

- **Decision**: running step = spinner icon + text "Running · 42 s" + a slim indeterminate bar (list card) / pulsing outline (graph node); waiting = hollow dotted node + "Waiting"; stalled = static warning icon + "Stalled · 17m". Arrows into/out of a non-done step are drawn inactive (reuses the existing inactive edge style). Under `prefers-reduced-motion` the spinner and bar are static (partial ring, filled segment) and text carries the meaning (FR-009).
- **Rationale**: icon + motion + text, never colour alone; reuses spec 003 tokens, adds only `--running` colour pair if no existing accent fits.
