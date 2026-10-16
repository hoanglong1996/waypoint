# Research: Run Liveness Heartbeat

Facts marked "read" come from the code on 2026-10-16. Nothing in the plan was left as NEEDS CLARIFICATION.

## R1. How the library sends the signal without affecting the pipeline

- **Decision**: One daemon `threading.Thread` per active auditor, waiting on a `threading.Event` with the beat interval as timeout. It writes immediately at start, then every interval, using the auditor's existing store `write`. Any exception is caught and printed as a warning (first failure, then at most once a minute). `stop()` sets the event and joins briefly (<= 1 s).
- **Rationale**: The thread keeps beating while the main thread is blocked inside a step (hung case) and stops when the process dies (dead case). Daemon status means it never delays exit (FR-005). Store writes already have 2 s timeouts (read: `RedisStepAuditStore`), so a stuck write only ever delays the heartbeat thread, not the pipeline (SC-004). The `redis` client is thread-safe.
- **Alternatives**: beat only at step start/finish (cannot separate a long step from a dead process); `asyncio` task (breaks for sync pipelines, dies with a blocked event loop); a separate sidecar process (new deployable).

## R2. What the alive item holds and how long it lives

- **Decision**: One JSON item per run, overwritten each beat: `{"v":1,"pipeline","env","run_id","beat_at"}`. TTL equals the run's normal `ttl_days`, refreshed on every beat.
- **Rationale**: Spec FR-003: "never sent" (legacy run, key absent) must differ from "stopped sending" (key present, old `beat_at`). A short-TTL key would make both look absent. A persistent timestamp allows the monitor to compare against its own clock.
- **Alternatives**: short-TTL key (loses the distinction); store only in the flow item (written once, cannot be refreshed); list of beats (unbounded growth).

## R3. When the monitor judges a run Died

- **Decision**: In `build_runs` (pure, no I/O): a run is Died if (a) a stored verdict exists, or (b) it has an alive item, work is unfinished, and `now - beat_at > HEARTBEAT_DEAD_SECONDS` (default 90). "Unfinished" means any planned step has no record, or a start marker has no record. A run with all planned steps recorded is never newly judged Died (FR-013). No alive item means legacy behaviour (FR-010).
- **Rationale**: 90 s equals six missed 15 s beats, which covers short store outages and small clock differences. Keeping the rule inside the pure function keeps it easy to test.
- **Effect on other states**: for a Died run the open step is `died` (not `running`/`stalled`), later planned steps are `missing` (not `waiting`), the "just started" state is off, `status` is `incomplete`, `running` is false.
- **Known limit**: a run that exits cleanly after skipping planned steps on purpose is also judged Died once its beat ages out, because the library records no "finished" marker. A run-level finished record is a separate feature (spec Assumptions). Before this feature such a run was shown as "Incomplete"; after it, "Died" (which also means incomplete). Accepted.
- **Alternatives**: a stall-threshold-only rule (today); judging from marker age (cannot tell hung from dead).

## R4. Persisting the verdict (clarification 2, option A)

- **Decision**: When `build_runs` reports a Died run with no stored verdict, the route calls `store.record_died(key, value)`. Redis side: `PTTL` of the run's alive item, then `SET key value NX PX <that ttl>` (fallback 30 days if the TTL is unavailable). `NX` makes concurrent writers produce one verdict (FR-007e); a run is stored once and never overwritten or deleted by the monitor (FR-007c).
- **Rationale**: Same data store, no new component, shared by all monitor instances, and expires with the run's records (about `ttl_days` from the last beat).
- **Failure handling** (FR-007d): `record_died` returns False on any Redis error, including `NOPERM` for a read-only account. The route still returns the Died view, evicts nothing, logs a warning (throttled), and retries on the next view. Without write permission, Died is recomputed per view and permanence across restarts is not guaranteed (documented).
- **Cache**: after a successful write the cache entry for that pipeline and environment is dropped so the next read includes the verdict.
- **Alternatives**: in memory (rejected by user); Lua script (not needed: a single `SET NX PX` is atomic).

## R5. Backward compatibility (FR-014, SC-007)

- **Decision**: Keep every existing key and field as is, add only `...:alive` and `...:died`. Both are outside the three scan patterns an old monitor uses (`*:flow`, `*:step:*`, `*:running:*`), so old monitors never see them, never count them unreadable, and keep working. The new monitor treats a missing alive item as legacy. Record format version stays 1.
- **Rationale**: Either side can be deployed first. Read: `RedisRecordStore` scans by exact suffix patterns.
- **Alternatives**: bump `FLOW_VERSION` (would make old monitors show "Unsupported record version").

## R6. Front end

- **Decision**: Add the state `died` wherever `stalled` is handled: `model.js` (step state, card kind), `api.js` (mapping `died`, `last_seen_at`), `graph-model.js` (a stop point like `stalled`), `views/graph.js` (label, icon, pill), `views/home.js` ("Died at step X, last seen N ago"), `views/step.js` and `views/latest.js`, `styles.css` (`gpill--died`, `step--died`, using the existing error colours, not the warning ones). Card status `died` sorts with the problem cards.
- **Rationale**: Reuses the established pattern; Died must look distinct from Stalled (SC-005).
- **Alternatives**: reuse the Stalled visuals with different text (fails "distinct" in FR-012).

## R7. Release and rollout

- **Decision**: Library version 0.2.0 (minor, additive). Roll out in any order. Monitor Redis account needs write permission for `waypoint:*:died` (or the whole `waypoint:*` prefix); without it the feature degrades as described in R4. Update `deploy/README.md` pinned URL when a tag is cut.
- **Not in scope**: failure-reason records, resilient/buffered writes, run-finished record, push alerts (spec Assumptions).
