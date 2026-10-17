# Research: Step Failure Errors

Decisions that the spec left open, taken against the code as it stands on 2026-10-17.

## R1. What counts as a step failure on the library side

**Decision**: Record `Exception` subclasses raised by the step function (sync and `async`). Do not record
`BaseException` that is not an `Exception` (`KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError`).

**Rationale**: Those three mean "stopped from outside / asked to exit", not "the code raised an error". They leave
the step looking unfinished, which the heartbeat of spec 009 already turns into Died when the process goes away.
**Alternatives**: catch `BaseException` (would label Ctrl-C and task cancellation as failures; noisy). Easy to widen
later if a pipeline uses `sys.exit(1)` inside steps.

## R2. How the original exception is preserved

**Decision**: `except Exception:` then call the recorder inside its own `try/except Exception`, then a bare `raise`.
The recorder returns nothing and never raises.

**Rationale**: A bare `raise` re-raises the same exception object with its original traceback (the wrapper frame
is already part of normal propagation), so type, message, `__cause__` and `__traceback__` are identical to an
unmonitored run (FR-002, SC-003). An exception raised while recording is swallowed inside the recorder and
cannot replace it. **Alternatives**: `raise exc` (adds a frame, can change context); a context manager (same result,
more code across the sync and async wrappers).

## R3. Building the traceback without leaking values

**Decision**: Build the text from frames only: for the exception and each chained cause/context, use
`traceback.extract_tb` / `format_list` (file, line number, function, source line). Never use `capture_locals`.
The exception's own text appears only on a header line `Type: message` when message capture is on (after `redact`);
with capture off the header is the type alone. Frames that belong to `waypoint_etl` itself are dropped.

**Rationale**: `traceback.format_exception` always appends `Type: message`, which would reintroduce the message
when capture is off (FR-006a, SC-004). Source lines are code, not data. **Alternatives**: `format_exception` plus
string surgery (fragile); `StackSummary.extract(..., capture_locals=True)` (forbidden by FR-006).

## R4. Message capture and redaction

**Decision**: `init(capture_error_message=True, redact=None)`. Message on by default (spec clarification). Order:
`str(exc)` (guarded) -> `redact(text)` if given -> cut to 500 characters. If `redact` raises or returns a non-string,
the message is dropped (fail safe), not stored raw. When capture is off the `message` field is omitted entirely.
The cleaning function also applies to chained-exception header lines.

**Rationale**: Matches FR-005/006a and keeps the worst case (a bad cleaning function) private. The cap is applied
after cleaning so a cleaner that expands text cannot exceed the limit.

## R5. Size caps

**Decision**: `message` ≤ 500 characters. `traceback` ≤ 8192 UTF-8 bytes, keeping the **last** frames: drop whole
leading frames (and chained blocks) until it fits, prefix `... (earlier frames omitted)`; if one frame alone is larger,
cut from its start. `type` ≤ 200 characters. The monitor applies the same caps when parsing, so an item written by
anything else cannot inflate the API.

**Rationale**: The innermost frames explain the failure; a deep recursion error would otherwise fill the cap
with identical outer frames.

## R6. How a failed step stops looking like Running

**Decision**: The library does **not** delete or rewrite the start marker (the store protocol only has `write`,
and custom stores implement just that). Instead the monitor gives the failure precedence: a step whose latest
attempt is a failure is Failed, never Running/Stalled/Died, whatever the marker says.

**Rationale**: Keeps the store protocol unchanged and makes the result independent of write ordering. Spec
FR-004 ("no longer treated as running") is satisfied in the only place that decides display.
**Alternatives**: delete the marker (needs a `delete` on every store, extra Redis call at the worst moment); overwrite
it with a "failed" marker (a new marker format, and old monitors would show the step as Running).

## R7. Which attempt is current: compare by attempt index, not by time

**Decision**: Each attempt of a step has a unique 1-based `index` (the auditor increments it on every `begin`). For a
step, take the highest index among its finish record, start marker and failure item: if it is the failure, the step
is Failed; a later marker (retry in progress) makes it Running/Stalled as usual; a later finish makes it Done.

**Rationale**: Timestamps have one-second resolution, so an immediate retry can share a second with the failure.
Indexes are exact and already in every record. Resolves the "retry succeeds" and "same step fails twice" edge cases.

## R8. When the run itself is Failed (clarified: only if the failure stopped the pipeline)

**Decision**: The run is Failed when its current failure has the highest index of everything recorded for the run
(no later step has started, finished or failed). Then the run is not Died even if its heartbeat stops, the
monitor never writes a died verdict for it, and later planned steps are `missing` (shown "Not reached").
If the pipeline continued past a failure, the step shows Failed but the run keeps its ordinary status; a failed
planned step has no finish record, so it counts as missing and the run is Incomplete (never Completed).

**Rationale**: Directly implements the spec's clarifications. "Highest index" is computable from the same
records the monitor already reads. **Alternative**: any failed step fails the run (rejected by the user in clarification Q2).

## R9. Error text is untrusted input in the browser

**Decision**: Render type, message and traceback only through the existing `esc()` helper (or `textContent`);
the Copy button copies from the in-memory model value, not by reading HTML back from the DOM; the trace sits in a
scrollable `<pre>` with a maximum height.

**Rationale**: The text comes from Redis and may contain markup, so escaping is a security requirement. Capping
at parse time also bounds DOM size.

## R10. History "Failed" filter

**Decision**: History has an environment filter but no status filter and no outcome trend today. Label Failed
runs in the run rows (the status pill) and add one small client-side control, "All runs / Failed only", next to the
environment filter. No trend change (the trend shows counts, not outcomes).

**Rationale**: Spec US4 scenario 2 asks to filter by Failed; this is the smallest thing that satisfies it. A
general multi-state filter is out of scope. **Alternative**: drop the filter and relax the spec (would need a spec edit).

## R11. Where the Failed card sorts

**Decision**: Within the "needs attention" group put Failed cards first, then keep the existing order by label
(`groupCards` in the front end and `build_overview` on the server). Only Failed moves; a full state ranking would change
the ordering rule of specs 008/009 for no requirement (FR-011 asks only that Failed ranks above the others).

## R12. Time of a failed run

**Decision**: For age and `ended_at`, a current failure counts like a finish: `ended_at` = latest of finish times
and failure times. A stopped-failure run is therefore "stopped Xh ago" measured from the failure, and cannot be Stale
before `STALE_HOURS` passes after the failure.

## R13. Library version

**Decision**: `waypoint-etl` 0.3.0 (the roadmap pairs this with the duration work, which this feature does not
build; `failed` items already carry `started_at` so duration can use them later). The monitor needs no version
coordination: it works with 0.2.x pipelines (FR-015) and a 0.3.0 pipeline works with an older monitor (it ignores
the `:failed:` key and keeps showing Stalled/Died as today).
