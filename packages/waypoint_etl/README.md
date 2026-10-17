# Waypoint library (`waypoint-etl`)

Part of Waypoint. Records every step of an ETL pipeline (start, finish, how many items went in and
out) in Redis so Waypoint Monitor can draw the pipeline as a graph. Only step names and counts are
stored, never item contents.

## Install

```bash
pip install -e "packages/waypoint_etl[redis]"        # inside this repo
pip install "waypoint-etl[redis] @ git+https://github.com/hoanglong1996/waypoint.git@waypoint-etl-v0.3.0#subdirectory=packages/waypoint_etl"
```

## Adopt it in a pipeline

1. **Declare the pipeline once** (names, hand-offs, optional groups/labels/layout hints):

   ```python
   from waypoint_etl import PipelineSpec, StepSpec

   SPEC = PipelineSpec(name="my-pipeline", steps=(
       StepSpec("extract"),
       StepSpec("clean", inputs=(("rows", "extract"),)),
       StepSpec("load", inputs=(("rows", "clean"),), returns_nothing=True),
   ))
   ```

   `inputs=(("rows", "extract"),)` reads "input `rows` comes from step `extract`".

2. **Configure once, in the entry point:**

   ```python
   import waypoint_etl
   waypoint_etl.init(pipeline=SPEC, redis_url=os.getenv("REDIS_URL"), env="prod", ttl_days=30)
   ```

   `init` returns `True` when auditing is on. With a bad spec or missing/invalid Redis URL it prints
   a warning, returns `False` and the pipeline runs unaudited. It never raises.

   Optional: `heartbeat_seconds=15` (default) sets how often the run's heartbeat is refreshed (see
   "Behaviour to know"); `None` or `0` turns it off.

3. **Mark each step function** (functions, methods and `async def` all work):

   ```python
   @waypoint_etl.audited_step("clean")
   def execute(self, rows): ...
   ```

   Input counts are taken from the call's arguments, matched to the step's spec inputs by
   **parameter name**. If a parameter is named differently, rename it:
   `@audited_step("join", inputs={"a": "left", "b": "right"})`.

   The code that calls your steps does not change. Before `init` (or after a failed `init`) a marked
   step behaves exactly like an unmarked one.

4. **Keep spec and steps in sync** with a test:

   ```python
   from waypoint_etl.testing import assert_spec_matches
   assert_spec_matches(SPEC, MyExtractUseCase, MyCleanUseCase, ...)
   ```

If you cannot edit a function, `waypoint_etl.wrap(obj, "execute", step="clean")` marks it from the
outside.

## Behaviour to know

- Records are written to `waypoint:{pipeline}:{env}:{run_id}:...` (contract:
  `specs/007-rename-to-waypoint/contracts/redis-keys.md`).
- A Redis failure at any moment is logged and swallowed; results and exceptions of your steps are
  never altered.
- **Step errors** (0.3.0): if a step raises an `Exception` (sync or `async`), one failure item
  `waypoint:{pipeline}:{env}:{run_id}:failed:{NN}-{step}` is written and **the same exception is re-raised
  untouched**; no finish record is written and the start marker stays (the monitor lets the failure win). The item holds
  the error type, a message shortened to 500 characters, a stack trace shortened to 8 KB (last frames kept) and
  `started_at` / `failed_at`. The trace has file, line, function and source line of each frame, never variable
  values. `KeyboardInterrupt`, `SystemExit` and `asyncio.CancelledError` are not recorded (they look like a process that
  stopped, which the heartbeat turns into Died). Error messages can contain data, so you decide what is kept:

  ```python
  waypoint_etl.init(
      pipeline=SPEC, redis_url=url, env="prod",
      capture_error_message=True,     # default; False stores only the type and the trace
      redact=lambda text: scrub(text),  # optional str -> str, applied to every message first
  )
  ```

  A `redact` that raises drops the message instead of storing it raw. Older monitors ignore the item
  (the step then looks Stalled or Died as before); the monitor shows it as **Failed** from this release on.
- **Step durations** (0.4.0): each finish record also carries `started_at` and `duration_ms` (measured with a
  monotonic clock, so a clock change cannot distort it). Older records still work: the monitor then estimates a step's
  duration from the previous step's end and marks it with `≈`.
- **Events** (0.4.0): send a short message to the run's timeline from anywhere in your code:

  ```python
  waypoint_etl.log("Loaded batch 3", rows=1200)             # info, attached to the running step
  waypoint_etl.warn("12 rows had no phone number", rows=12)
  waypoint_etl.error("one batch skipped", step="load", batch=7)
  ```

  An event has a message (300 characters at most), a level (`info`, `warning`, `error`), an optional step (the step
  you are inside, per thread or async task, unless you pass `step=`) and up to 10 named values: numbers or strings of
  at most 100 characters, names of letters, digits, `_`, `.`, `-` (anything else is dropped silently). The call goes
  onto an in-memory queue and a background thread writes it in batches, so it **never waits on Redis and never
  raises**: before `init`, after a failed `init` or with Redis down it does nothing. Redis keeps at most 500 `info`,
  200 `warning` and 200 `error` events per run (the oldest of a level go first, so errors survive a flood of info);
  they expire with the run. Events are delivered within about a second; at exit (and on
  `waypoint_etl.registry.clear()`) the queue is flushed, waiting at most 2 seconds, so only a killed process
  (`SIGKILL`) loses the last second. The monitor builds the rest of the timeline itself (run and step start, finish,
  failure, died, stalled) from the records above, so you only send what is worth saying.
  **Keep data values out of event text**: what you write is stored as written. `capture_error_message=False`
  and `redact=` (above) also cover events: with capture off the message and text values are dropped (numbers stay),
  with `redact` every message and text value is cleaned first. Store back ends other than Redis need a
  `push_events(items, ttl_seconds)` method (`items` are `(key, values, cap)` triples) to receive events.
- **Heartbeat** (0.2.0): after `init`, a daemon thread refreshes `waypoint:{pipeline}:{env}:{run_id}:alive`
  (`{"v":1, "pipeline", "env", "run_id", "beat_at"}`, same TTL as the run) right away and then every
  `heartbeat_seconds` (15). It keeps beating while a step is blocked and stops when the process dies, so the
  monitor can tell a hung run (alive, not progressing: "Stalled") from a dead one ("Died", shown within about 90 s).
  It holds ids and a time only, never raises, never blocks a step, never keeps the process alive, and stops on
  `waypoint_etl.registry.clear()` or when `init` is called again. Only the process that called `init` beats.
  Older monitors ignore the item; runs without it are never shown as Died.
- Steps are assumed to run one after another within a run. Calling `init` again replaces the
  previous configuration (with a warning).
- Counts: `None` → none, list/tuple/set → its length, anything else → 1. Never the contents.

## Try it

```bash
REDIS_URL=redis://localhost:6379/0 python examples/sample_pipeline.py
```

## Develop

```bash
python -m unittest discover tests
black . && ruff check . && mypy .
```
