# Waypoint library (`waypoint-etl`)

Part of Waypoint. Records every step of an ETL pipeline (start, finish, how many items went in and
out) in Redis so Waypoint Monitor can draw the pipeline as a graph. Only step names and counts are
stored, never item contents.

## Install

```bash
pip install -e "packages/waypoint_etl[redis]"        # inside this repo
pip install "waypoint-etl[redis] @ git+https://github.com/hoanglong1996/waypoint.git@waypoint-etl-v0.2.0#subdirectory=packages/waypoint_etl"
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
  never altered. If a step raises, its start marker stays and no finish record is written.
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
