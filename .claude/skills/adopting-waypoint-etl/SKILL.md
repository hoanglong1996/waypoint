---
name: adopting-waypoint-etl
description: Use when adding Waypoint pipeline tracking (waypoint-etl SDK, Waypoint Monitor) to a Python ETL project - installing the SDK, configuring Redis/env, writing the PipelineSpec, decorating steps with audited_step, or calling waypoint_etl.init in the entry point
---

# Adopting waypoint-etl in a client project

## Overview

`waypoint_etl` records each pipeline step (start, finish, input/output counts) in Redis; Waypoint Monitor reads it and draws the pipeline. Your job is to set up the user's project so they do not have to write this themselves. Three code pieces: a **PipelineSpec** (declared once), **`init`** (once, in the entry point), **`@audited_step`** on each step function. Callers of the steps do not change. Without a successful `init`, decorated functions behave as plain ones, and `init` never raises.

Only names and counts are stored, never item contents. Never put data in step names or labels.

SDK repo: `https://github.com/hoanglong1996/waypoint` (SDK in `packages/waypoint_etl/`, its README has the full API).

## Step 0: Inspect before changing anything

Find out, and state back to the user in one short list:

- Entry point (`main.py`, `__main__`, DAG file, CLI) and where the pipeline is run (`run_pipeline`, a chain of calls, an Airflow/Prefect task, ...).
- How dependencies are declared (`requirements.txt`, `pyproject.toml`, `poetry`, `Pipfile`, Dockerfile) and the Python version (SDK needs **3.10+**).
- How config is read (env vars, `.env`, a `Config` class, secrets manager). Never print secret values; config files may hold live credentials.
- How the project is deployed (Docker image, CI) so the install line works there.

Ask the user only for what you cannot find: the **Redis URL** the Waypoint Monitor reads, the **environment name(s)** (must match the monitor's `ENVIRONMENTS`, e.g. `qa`, `prod`), and the **SDK version/tag** to pin (default: latest `waypoint-etl-v*` tag, see `git ls-remote --tags https://github.com/hoanglong1996/waypoint.git`).

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

## Step 5: Sync test and verification

1. Add a test: `from waypoint_etl.testing import assert_spec_matches; assert_spec_matches(SPEC, UseCase1, UseCase2, ...)`, passing every decorated **class** (or module/function holder). It fails on decorated-but-unspecced or specced-but-undecorated steps.
2. Run the project's tests, then import the entry point (`python -c "import main"`) to catch import errors.
3. Run the pipeline once against a QA Redis, then check keys exist: `redis-cli --scan --pattern 'waypoint:<pipeline>:<env>:*'`. Open the Monitor, pick that environment, and confirm the pipeline card and step counts appear.
4. Report to the user: files changed, new config variables they must set, and any Dockerfile/CI changes.

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
| Parallel steps | SDK assumes steps run one after another per run |

Counts: `None` is 0, list/tuple/set is its length, anything else is 1.
