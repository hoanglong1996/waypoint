# Research: Run Duration and Run Events

Decisions that the spec left open (including roadmap decisions 3, 4, 5), taken against the code as it stands on 2026-10-17.

## R1. Where a step's duration comes from

**Decision**: Use the first source that exists, in this order, and mark the result approximate only for the last:
1. `duration_ms` in the finish record (new, measured with a monotonic clock, immune to clock changes);
2. `started_at` and `finished_at` in the finish record (new in 0.4.0);
3. the start marker's `started_at` (exists only for 24 h) with `finished_at`;
4. **approximate**: `finished_at` minus the end of the previous step (the latest finish or failure time among steps with
   a lower attempt index), or minus the run's start (the run id) for the first step.
A failed step uses its failure item (`failed_at - started_at`, always present). A result that is negative or
missing is `null`, shown as unavailable.

**Rationale**: The finish record today has no start time and markers expire after 24 h, so for most completed runs
(and every run older than a day from library 0.2.0/0.3.0) the exact value does not exist. Steps are sequential, so the
previous step's end is a sound estimate (it also includes any gap between steps, hence "approximate"). Resolves the
spec's FR-001 and SC-001 wording.
**Alternatives**: library change only (leaves every existing run without step durations); derive only from markers
(fails after 24 h).

## R2. How author-sent events are stored (roadmap decision 3)

**Decision**: Three Redis **Lists** per run, one per level: `...:{run_id}:events:info`, `...:events:warning`,
`...:events:error`. A write is one transaction per flush: `RPUSH` the batch, `LTRIM` to the cap (`-500`/`-200`/`-200`),
`EXPIRE` to the run's TTL. Each element is a JSON object (see contracts/redis-keys.md).

**Rationale**:
- `RPUSH` is atomic, so several threads or processes (a step that forks workers) can append to the same run without
  overwriting each other. A single JSON document per run would be overwritten by whichever writer flushed last.
- `LTRIM` keeps the **newest** N, so "oldest info dropped first" (Q2) is enforced by Redis itself, with no script
  (no `EVAL` permission) and no read-modify-write.
- One list per level keeps warnings and errors safe from info floods and makes the counts for Home and History a
  plain `LLEN`, with no event bodies read on every refresh.
**Alternatives**: Redis Stream (`XADD MAXLEN`, `XRANGE` paging): natural paging, but `MAXLEN` trims by age across all
levels, so info events would push out errors; needs `XADD`/`XRANGE` permissions and a different cap rule. One key per
event: `SCAN` of the whole keyspace would grow by up to 900 keys per run on every dashboard refresh. One JSON document:
overwritten by concurrent writers.

## R3. Automatic events are derived, not stored

**Decision**: The monitor builds run started, step started, step finished, step failed, run ended, run died and step
stalled from the run it already assembled (`build_runs` output). The library writes none of them.

**Rationale**: The records already carry everything (flow, markers, finish, failure, alive, verdict). Deriving them
means identical timelines for every library version (FR-031, SC-008), no extra writes, and automatic events cannot be
lost to the cap (Q2). This changes FR-014 from "the library records" to "the timeline includes"; the spec is amended.
**Alternatives**: the library writes them too (duplicates data the monitor must then reconcile; older runs would still
need the derived path).

## R4. Timestamps, ordering, and stable order for equal times

**Decision**: Recorded events carry millisecond UTC timestamps and a per-process sequence `n`. Derived events use the
records' one-second timestamps, placed so that events sent *inside* a step sort between its start and its end:
`started`-type events at the start of their second (`.000`), `finished`/`failed`/`ended` events at the **end** of their
second (`.999`). Sort key: `(timestamp, source_rank, sequence)` where derived events rank before recorded ones at the
same instant, derived events keep their derivation order, and recorded events keep `n`.

**Refinement found in the manual pass**: derived events are produced in the order the steps ran, and a step that starts in the same whole second the previous step finished is placed at the end of that second too (after the previous step's finish). Without it, two quick back-to-back steps listed the second step's start before the first step's finish. The cost is a sub-second ambiguity for events a step sends in that first fraction of a second.

**Rationale**: Without the `.999` rule an event sent 0.6 s into the last second of a step would sort after the step's
"finished" event. Sequence `n` makes ordering stable for events in the same millisecond (FR-023, edge case).

## R5. Never blocking the pipeline (FR-018, SC-006)

**Decision**: `log()` builds the event (validation and limits), puts it on a `queue.Queue(maxsize=2000)` with
`put_nowait`, and returns. A daemon thread `waypoint-events` drains up to 100 events at a time (waits at most 1 s for
the first), groups them by level and writes one transaction. If the queue is full the event is dropped (warning and
error events displace an info event if the queue is full) and counted as dropped. `clear()` and an `atexit` hook stop
the thread after one last flush that waits at most 2 s. Writer errors are caught, logged at most once a minute, and the
batch is discarded (no retry storm).

**Rationale**: The same shape as the heartbeat (spec 009): a daemon thread and a swallow-and-warn policy. A `SIGKILL`
loses at most the last second of events; documented.
**Alternatives**: inline write (round trip on every call; stalls up to the 2 s socket timeout when Redis is down);
thread per call (cost, ordering).

## R6. Caps and the "dropped" note (FR-020, Q2)

**Decision**: Info list keeps the newest **500**, warning and error lists the newest **200** each (the oldest of that
level is dropped first). Each event carries `n`, a per-process counter over all levels. The events endpoint reports
`dropped = max(0, max(n) - stored)` where `stored` is the number of recorded events read for the run. Limits are
constants in this release.

**Rationale**: Dropped events leave no tombstone in Redis (a list trimmed with `LTRIM` has no record of what it lost), and
a counter key would cost another write. The gap between the highest `n` and what remains is exact for a single-process
run and a safe underestimate when workers restart `n`. Queue-full drops also leave gaps, so they are included.

## R7. Privacy of event text (Q1, FR-022)

**Decision**: The `capture_error_message` and `redact` arguments of `init` apply to **all free text** the library stores:
an event's `message` and the text values in `fields`. With capture off the `message` is omitted and text field values
are dropped (numbers are kept). `redact` runs on the message and on each text value, before the length cap; if it raises
or returns a non-string, that text is dropped. No new argument. Docs say "free text" and keep the warning that author
text is the author's responsibility.

**Rationale**: One switch is easier to reason about and to test (SC-010) than two. The parameter names stay for
backward compatibility with 0.3.0 callers.

## R8. Which step an event belongs to (FR-016)

**Decision**: A `contextvars.ContextVar` holds the current step name, set by the decorator around the call (sync and
async, so it is correct per thread and per asyncio task). `log(step=...)` overrides it. If the variable is empty (for
example in a worker thread, which does not inherit it) the auditor's most recently begun, still open step is used if
there is exactly one; otherwise the event has no step.

**Rationale**: Steps are sequential (spec assumption), so the single-open-step fallback is right for pool threads.

## R9. Typical duration, slow flag, window (roadmap decision 5)

**Decision**: Global settings, no per-pipeline override: `DURATION_WINDOW_RUNS=30`, `DURATION_MIN_RUNS=5`,
`SLOW_RUN_MULTIPLE=2.0`. Per pipeline and environment, take the newest `DURATION_WINDOW_RUNS` runs whose status is
`complete` (Lost data counts, because the run finished; Failed, Died, Stalled, Incomplete and running do not). Median
is the middle value (average of the two middle values for an even count); p95 uses nearest-rank
(`ceil(0.95 * n)`-th smallest). A run is `slow` when its duration is greater than `SLOW_RUN_MULTIPLE * median`,
there are at least `DURATION_MIN_RUNS` such runs, and (for a running run) its elapsed time to now already exceeds that.
The flag never changes status or ordering (FR-013). The statistics are computed over every run the monitor read, not
only the `limit` slice returned.

**Rationale**: Nearest-rank is simple, deterministic, and testable. Including the run itself in its own baseline is
harmless for a median with a minimum of 5. Computing in `build()` keeps `/api/runs` and `/api/overview` consistent.

## R10. Bottleneck (FR-005)

**Decision**: Among steps of the run with a known duration, the one with the largest duration, shown only when at least
two steps have a duration and it is the strict maximum (ties: none highlighted). The API returns its name in
`bottleneck`. Approximate durations count.

## R11. Limits on an event

**Decision**: `message` ≤ 300 characters; ≤ 10 named `fields`; field names match the step-name pattern (letters,
digits, `_`, `-`, `.`; ≤ 40 characters); a field value is an `int`/`float` (finite) or a string ≤ 100 characters;
anything else (booleans, lists, objects, NaN) is dropped. Level must be `info`, `warning` or `error` (otherwise
`info`). The monitor applies the same limits when parsing, so an element written by anything else cannot inflate the API.

## R12. Reading cost (SC-004, SC-009)

**Decision**: `/api/runs` and `/api/overview` read only **counts**: `SCAN` for `...:events:*` key names and one pipelined
`LLEN` batch (read only), cached in the same 2 s window. Event bodies are read only by the events endpoint, for one run,
with three `LRANGE 0 -1` calls (at most 900 elements). Paging, filtering and merging happen in the monitor in memory.

**Degraded mode**: a `NOPERM` (or other `ResponseError`) answer to `SCAN`-for-events, `LLEN` or `LRANGE` is not "store unavailable": counts become zero and the events endpoint returns an empty recorded list with the derived timeline, so a monitor account without the new permission keeps every existing page working. A connection error is still `503`.

**Rationale**: Refreshes happen every 5 s for every open dashboard; event bodies must not be part of that path.

## R13. Events endpoint and paging

**Decision**: `GET /api/runs/{pipeline}/{env}/{run_id}/events?level=&step=&offset=0&limit=200` (limit 1 to 500).
Offset paging over the merged, filtered list (the list only grows at the end, apart from the rare late arrival of an
earlier-timestamped event, which is acceptable for a diagnostic view). The response carries `total`, `matched`,
`recorded` (author events read), `dropped`, `has_more`. While a run is open the front end refetches the pages it has
already loaded on each refresh; filters and scroll are client state and are not reset.

**Alternatives**: a cursor by event id (more state for little benefit at ≤ 900 events).

## R14. Config and compatibility

**Decision**: Library `0.4.0` (events + finish record fields); duration works with 0.2.0 and 0.3.0 (roadmap decision 4:
`0.3.0` shipped with #1; #2 and #3 ship together as `0.4.0`). Finish records gain optional `started_at` and
`duration_ms` without a `v` bump; the monitor parser ignores unknown fields (verified for failure items in spec 011,
re-verified for step records in the first task). Event elements carry `"v": 1`. An older monitor never reads the event
lists. An older library never writes them: the timeline is then purely derived and says so (FR-030).

## R15. History chart and flags

**Decision**: Reuse `chart.js` for a second chart "Run duration" (one point per run, a dashed line at the median and a
band to p95). Runs flagged Slower than usual get a text label with an icon, and a marker in the chart (not colour
alone). The runs list gains a Duration column; below `DURATION_MIN_RUNS` the card says "Not enough history yet".
