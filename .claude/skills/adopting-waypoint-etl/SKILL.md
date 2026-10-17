---
name: adopting-waypoint-etl
description: Use when adding Waypoint pipeline tracking (waypoint-etl SDK, Waypoint Monitor) to a Python ETL project - installing the SDK, configuring Redis/env, writing the PipelineSpec, decorating steps with audited_step, calling waypoint_etl.init in the entry point, or tracking a loop over items (accounts, files, partners, batches; sequential, thread pool or asyncio) with a map step
---

# Adopting waypoint-etl in a client project

## Overview

`waypoint_etl` records each pipeline step (start, finish, input/output counts) in Redis; Waypoint Monitor reads it and draws the pipeline. Your job is to set up the user's project so they do not have to write this themselves. Three code pieces: a **PipelineSpec** (declared once), **`init`** (once, in the entry point), **`@audited_step`** on each step function. Callers of the steps do not change. A step that repeats the same small flow for many items (a loop) adds two more pieces, a **`MapStepSpec`** and two `with` lines, described in "Loops: map step" below. Without a successful `init`, decorated functions behave as plain ones, and `init` never raises.

Only names and counts are stored, never item contents. Never put data in step names or labels.

SDK repo: `https://github.com/hoanglong1996/waypoint` (SDK in `packages/waypoint_etl/`, its README has the full API).

## Step 0: Inspect before changing anything

Find out, and state back to the user in one short list:

- Entry point (`main.py`, `__main__`, DAG file, CLI) and where the pipeline is run (`run_pipeline`, a chain of calls, an Airflow/Prefect task, ...).
- How dependencies are declared (`requirements.txt`, `pyproject.toml`, `poetry`, `Pipfile`, Dockerfile) and the Python version (SDK needs **3.10+**).
- How config is read (env vars, `.env`, a `Config` class, secrets manager). Never print secret values; config files may hold live credentials.
- How the project is deployed (Docker image, CI) so the install line works there.
- **Loops**: any place where one step repeats the same sequence of calls for many items (`for account in accounts`, `pool.map`, `asyncio.gather`, a per-partner or per-file loop). Note each loop, how it runs (plain `for`, `ThreadPoolExecutor`/`pool.map`, asyncio, `multiprocessing`), what identifies one pass (an id or an index) and which functions it calls in order. These become map steps (see "Loops: map step"); do not give them one `StepSpec` that hides the loop, and do not call `init` per item.

Ask the user only for what you cannot find: the **Redis URL** the Waypoint Monitor reads, the **environment name(s)** (must match the monitor's `ENVIRONMENTS`, e.g. `qa`, `prod`), and the **SDK version/tag** to pin (default: latest `waypoint-etl-v*` tag, see `git ls-remote --tags https://github.com/hoanglong1996/waypoint.git`). Map steps need **0.6.0 or newer**.

## Step 1: Install the SDK and configure the environment

Not on PyPI. Always install from git with a pinned tag and the full URL:

```
waypoint-etl[redis] @ git+https://github.com/hoanglong1996/waypoint.git@waypoint-etl-vX.Y.Z#subdirectory=packages/waypoint_etl
```

- Add that line to the project's dependency file (`requirements.txt`; or `pyproject.toml` dependencies; or `poetry add "git+https://github.com/hoanglong1996/waypoint.git@waypoint-etl-vX.Y.Z#subdirectory=packages/waypoint_etl" -E redis`). The `[redis]` extra installs `redis`; without it nothing is written.
- Dockerfile: `git` must exist in the image at build time (`apt-get install -y git` on slim images), or install a prebuilt wheel instead. For a private repo, CI needs a token (`git+https://x-access-token:${GH_TOKEN}@github.com/...`) or a deploy key (`git+ssh://git@github.com/...`); pass it as a build secret, never commit it.
- Config: add `REDIS_URL` (and optionally `WAYPOINT_TTL_DAYS`, default 30, and an env name such as `ENV_NAME`) using the project's existing config mechanism. Add placeholders to `.env.example` / config templates, not real values. If the project has no config mechanism, read `os.getenv`.
- Redis account for the pipeline must be able to write `waypoint:*` keys. Tell the user if they need to arrange that.

## Step 2: Write the spec

1. **List the steps** from the pipeline: one step per unit of work, in call order. Name = `[a-z0-9_]{1,64}` (e.g. `read_partners`).
2. **Put the spec in its own module** (e.g. `pipeline_spec.py`, constant `<NAME>_PIPELINE`), not inside `main()`:
   ```python
   from waypoint_etl import PipelineSpec, StepSpec

   MY_PIPELINE = PipelineSpec(name="my-pipeline", steps=(
       StepSpec("extract"),
       StepSpec("clean", inputs=(("rows", "extract"),)),
       StepSpec("load", inputs=(("rows", "clean"),), returns_nothing=True),
   ))
   ```
   - `inputs=(("param_name", "producer_step"),)` means "input `param_name` comes from `producer_step`". The producer must be declared **earlier** in `steps`.
   - `param_name` must equal the **parameter name** of the decorated function (excluding `self`). If it differs, rename on the decorator: `@audited_step("x", inputs={"my_param": "spec_input"})`.
   - Last or side-effect steps: `returns_nothing=True`.
   - Optional: `label` (<=40 chars), `group` (must exist in `groups`), pipeline `name` `[a-z0-9][a-z0-9_-]{0,39}`.
   - Groups: declare `groups=(GroupSpec("extract", "Extract"), ...)` on the `PipelineSpec`, then set `group="extract"` on a `StepSpec` or `MapStepSpec`. A `MapStepSpec` takes its own `group`; its inner `StepSpec`s must **not** set `group` (rejected from 0.6.2).
   - If a validation error is unclear, read `spec.py` in the SDK source (`pip show -f waypoint-etl` for its location).

## Step 3: Decorate the steps

```python
import waypoint_etl

@waypoint_etl.audited_step("clean")
def clean(rows): ...

class ReadUseCase:
    @waypoint_etl.audited_step("read")
    def execute(self, accounts): ...
```

Functions, methods and `async def` all work. Put the import in the third-party block, in the project's import style. If a function cannot be edited (third-party, generated), use `waypoint_etl.wrap(obj, "execute", step="name")` instead.

## Step 4: Init in the entry point

Once, after config is loaded and before the pipeline runs:

```python
import os
import waypoint_etl
from pipeline_spec import MY_PIPELINE

waypoint_etl.init(
    pipeline=MY_PIPELINE,
    redis_url=os.getenv("REDIS_URL"),   # None/invalid -> warning, unaudited, no raise
    env=os.getenv("ENV_NAME", "qa"),    # must be a str; must match the monitor's ENVIRONMENTS
    ttl_days=30,
)
```

`init` returns `True` when auditing is on. Optional `heartbeat_seconds=15` (default) lets the monitor tell Stalled from Died; `None` turns it off.

## Loops: map step (0.6.0 or newer; nesting rule enforced from 0.6.1)

Use a map step when a step loops over items and the user wants to see which item and which inner step failed or was slow. If the loop only needs totals, a normal step with `waypoint_etl.metric("items_failed", n, mode="add")` is enough; say so and let the user choose. Skip this section when the project has no loops.

**1. Declare it in the spec**, in the place of the step that contains the loop (inner steps are the functions one pass calls, in order):

```python
from waypoint_etl import MapStepSpec, PipelineSpec, StepSpec

MY_PIPELINE = PipelineSpec(name="my-pipeline", steps=(
    StepSpec("list_accounts"),
    MapStepSpec(
        "accounts",                    # name of the map step, [a-z0-9_]{1,64}
        over="list_accounts",          # optional: earlier top-level step that supplies the items
        max_concurrency=5,             # optional, display only; the library never runs the loop
        steps=(
            StepSpec("fetch"),
            StepSpec("transform", inputs=(("rows", "fetch"),)),
            StepSpec("load", inputs=(("rows", "transform"),), returns_nothing=True),
        ),
    ),
    StepSpec("publish", inputs=(("done", "accounts"),)),   # a later step may take the map step as producer
))
```

Rules (a violation turns tracking off with a warning naming the problem):
- Inner step names are unique across the **whole** pipeline, including top-level steps and other map steps.
- Inner steps never set `group` (rejected from 0.6.2); put the `group` on the `MapStepSpec`.
- 1 to 20 inner steps, in a **straight line**: no branches, no map step inside a map step (see "Nested loops" below).
- An inner step's `inputs` may name only an earlier inner step of the same map or an earlier top-level step.
- `max_concurrency`, when given, is an int >= 1. `over` must name an earlier top-level step.

**Nested loops: only the outermost loop is a map step.** When the code has loops inside loops, make the first (outermost) one the `MapStepSpec` and treat every loop inside it as ordinary code: wrap the **whole inner loop** in one normal `StepSpec` (decorated function) of the map step's `steps`. Never write `map_step()` or `item()` inside an item, and never put a `MapStepSpec` in another's `steps`. From 0.6.1 the SDK ignores a nested `map_step()` (and its `item()` calls) with one warning, so the inner loop is not tracked per item.

**2. Decorate the inner steps** exactly like any step (`@waypoint_etl.audited_step("fetch")`, Step 3); the same parameter-name rule applies to their `inputs`.

**3. Wrap the loop and one pass** (the loop itself stays the user's):

```python
with waypoint_etl.map_step("accounts"):              # the whole loop
    for account in accounts:
        process(account)

def process(account):
    with waypoint_etl.item(account.id):              # one pass: an id or an index
        rows = fetch(account)
        rows = transform(rows)
        load(rows)
```

- **Thread pool**: put `item()` **inside the function the worker runs** (`pool.map(process, accounts)`). Worker threads do not inherit the caller's context, so `item()` finds its map from the one open `map_step` block.
- **Asyncio**: `with item(id):` or `async with item(id):` inside each coroutine, then `asyncio.gather(...)`.
- If several map steps can be open at once, pass `item(key, map="accounts")`.
- If the loop catches item errors (collects exceptions, `try/except` around `process`), keep that; `item()` never swallows an exception, and a failed inner step is recorded even when the loop continues. The monitor then shows the map step as **Failed** once the loop ends.
- `waypoint_etl.log(...)` and `waypoint_etl.metric(...)` inside `item()` belong to that item and inner step automatically. A metric sent inside `item()` but outside every inner step is dropped with a warning.

**4. Choose the item key carefully.** It is shown on screen and stored: use a database id, an index or a file sequence number, **never a name, email, phone or other personal data**. Characters outside `[A-Za-z0-9_.-]` become `_`, it is cut to 64, an empty key becomes `item_N`, and a key that starts twice in one map step is ignored with a warning. If the only natural key is personal, use the loop index.

**5. Know the limits** and tell the user: items run in a child process (`multiprocessing`) are not recorded unless the child calls `init` and opens its own scopes; per map step and run, 1,000 items keep a full record, then up to 1,000 more failed items (compact) and the 50 slowest; counts always cover every item and the monitor says when detail is partial; nothing in these calls raises or waits on the network.

**What the user will see**: one node with `6 done · 4 running · 1 failed` (never a total), a panel under the graph with the item list (search, status filters, sort, paging), and a page per item with its inner steps, error and stack trace, metrics and events.

## Step 5: Sync test and verification

1. Add a test: `from waypoint_etl.testing import assert_spec_matches; assert_spec_matches(SPEC, UseCase1, UseCase2, ...)`, passing every decorated **class** (or module/function holder). It fails on decorated-but-unspecced or specced-but-undecorated steps. Inner steps of a map step count as specced steps, so pass the classes that hold them too.
2. Run the project's tests, then import the entry point (`python -c "import main"`) to catch import errors.
3. Run the pipeline once against a QA Redis, then check keys exist: `redis-cli --scan --pattern 'waypoint:<pipeline>:<env>:*'`. Open the Monitor, pick that environment, and confirm the pipeline card and step counts appear. For a map step also check: `redis-cli --scan --pattern 'waypoint:<pipeline>:<env>:*:map:*'` and `'*:item:*'` return keys, the map node shows done and failed counts, and opening an item shows its inner steps. Run it once with a deliberately failing item to see the failed item, its inner step and the "not run" step after it.
4. Report to the user: files changed, new config variables they must set, any Dockerfile/CI changes, and for each map step the item key used (and why it is not personal data) and how the loop runs.

## Common mistakes

| Mistake | Effect |
|---|---|
| Installing `waypoint-etl` by bare name | Pulls a different package or fails; use the full git URL |
| Forgetting the `[redis]` extra | `init` warns and the pipeline runs unaudited |
| `git` missing in the Docker image | Build fails on the git URL |
| Spec defined inside `main()` and also imported from a module | Shadowed/duplicate definition |
| Param name differs from spec input name | Input count silently missing (no error) |
| Step name typo between spec and decorator | Step never shown / `assert_spec_matches` fails |
| `init` called per partner/loop | Replaces config, new run each time (prints warning) |
| Non-str or unlisted `env` | Breaks the key, or the monitor never shows it |
| Putting data values in `waypoint_etl.log(...)` text | Event messages and text values are stored as written (300 and 100 characters at most). Send names and counts (`waypoint_etl.log("Loaded batch", rows=n)`). `capture_error_message=False` or `redact=` in `init` cover events as well as errors. From 0.4.0; the call does nothing before `init` or with Redis down, so it is safe anywhere |
| Sending text or booleans through `waypoint_etl.metric(...)` | A metric is a finite number only (`int` or `float`, not `bool`); the name is `[a-z0-9_]{1,64}`, at most 20 per step. Anything else is dropped with a warning. Use `mode="add"` to accumulate in a loop and `mode="max"` to keep the largest. Optional: declare it on the step with `Metric(name, label=, unit=, warn_above=, warn_below=)` for a unit and a warning flag. From 0.5.0; the call does nothing before `init` or with Redis down. Metrics are merged in the process that called `init` |
| Expecting exceptions to stay invisible | From 0.3.0 a raising step writes a failure item (type, shortened message, frames-only trace) and the exception is re-raised untouched; shown as Failed. Messages can hold data: pass `capture_error_message=False` or `redact=` to `init` when they might |
| A loop over accounts/files/partners inside one step, or `init` per item | Do not call `init` per item and do not hide the loop in one `StepSpec`. Use a map step (see "Loops: map step") |
| `item()` outside the worker function of a thread pool, or no `map_step` around the loop | Nothing is recorded for that pass (one warning). Open `map_step` around the whole loop and call `item()` inside the function each worker runs |
| Inner step name equal to a top-level step, or a branch / nested map step in the item flow | The spec is invalid: tracking is off and a warning names the step. Give inner steps unique names and keep the item flow a straight line |
| Putting the whole pipeline inside `item()` or opening `map_step` per item | `map_step` wraps the **whole loop once**; `item()` wraps one pass. Opening `map_step` per item: while one is open a second one of the same name is ignored with a warning (thread pool), and reopening it one after another restarts the map step each time, so the item list and counts only cover the last item |
| Using a name, email or phone as the `item(...)` key | The key is shown on screen and stored. Use an id or an index. Other characters become `_`, it is cut to 64, and a key used twice in one map step is ignored with a warning |
| Top-level steps that run in parallel | SDK assumes top-level steps run one after another per run; parallelism belongs inside a map step |

Counts: `None` is 0, list/tuple/set is its length, anything else is 1.
