# Waypoint

Per-step tracking for ETL pipelines. A pipeline reports, for every step, how many items went in and
out. The records go to Redis, and **Waypoint Monitor** draws them as a dashboard and a graph, so you
can see whether last night's run worked and where data dropped off.

Only step names and counts are stored, never item contents.

```
 your pipeline ──(waypoint-etl)──▶  Redis  ◀──(read-only)──  Waypoint Monitor  ──▶ browser
```

| Part | Folder | What it is |
| --- | --- | --- |
| `waypoint-etl` | [`packages/waypoint_etl`](packages/waypoint_etl) | Python SDK you install in each pipeline. No required dependencies; `redis` is an extra. |
| Waypoint Monitor | [`waypoint_monitor`](waypoint_monitor) | Web dashboard (FastAPI backend, plain HTML/JS front end). Reads Redis. |
| Deploy | [`deploy`](deploy) | `docker-compose.yml` that starts Redis + Monitor (+ an optional demo pipeline). |

---

## 1. Run Waypoint Monitor

### Option A: Docker Compose (Redis + Monitor together)

```bash
git clone https://github.com/hoanglong1996/waypoint.git
cd waypoint
docker compose -f deploy/docker-compose.yml up --build
```

Open <http://localhost:8080>.

### Option B: Run it directly (you already have a Redis)

```bash
cd waypoint_monitor
pip install -r requirements.txt
cp .env.example .env               # edit REDIS_URL
python -m app.main                 # loads .env, serves http://localhost:8080
```

Or with Docker only:

```bash
docker build -t waypoint-monitor waypoint_monitor
docker run -p 8080:8080 -e REDIS_URL=redis://host:6379/0 waypoint-monitor
```

### Monitor settings

Set as environment variables or in the `.env.<name>` file selected with `-c <name>`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | none | Redis that pipelines write to. |
| `ENVIRONMENTS` | `prod,qa,test` | Environments the dashboard reads. |
| `STALE_HOURS` | `26` | A pipeline whose newest run is older than this is marked **Stale**. |
| `SLOW_RUN_MULTIPLE` | `2.0` | A run longer than this multiple of the median is flagged **Slower than usual**. |
| `DURATION_WINDOW_RUNS` | `30` | Newest completed runs used for the median and slow end. |
| `DURATION_MIN_RUNS` | `5` | Completed runs needed before any run is flagged. |
| `STALL_SECONDS` | `900` | A step running longer than this is **Stalled**. |
| `HEARTBEAT_DEAD_SECONDS` | `90` | Heartbeat older than this, with unfinished work, means **Died**. |
| `REFRESH_SECONDS` | `5` | How often an open page reloads. |
| `PORT` | `8080` | HTTP port. |

Full list and behaviour: [`waypoint_monitor/README.md`](waypoint_monitor/README.md).

### Security notes

- The dashboard has **no login**. Keep it on an internal network or behind a VPN / authenticating reverse proxy.
- Redis is not published to the host by the compose file. To let a pipeline elsewhere write to it, publish the port or use your own Redis, and protect it with a password.
- Redis permissions: pipelines write `waypoint:*`. The monitor only needs `SCAN`, `MGET`, `PING`, `PTTL`, `LLEN` and `LRANGE` (to read events), plus `SET` on `waypoint:*:died`.

---

## 2. Use the SDK in your pipeline

### Install

The SDK is installed straight from this repository by git tag. It is not on PyPI, so always use the full URL:

```bash
pip install "waypoint-etl[redis] @ git+https://github.com/hoanglong1996/waypoint.git@waypoint-etl-v0.5.0#subdirectory=packages/waypoint_etl"
```

(Step errors shown as **Failed**, with their stack trace, need `waypoint-etl` 0.3.0 or newer. Exact step durations and `waypoint_etl.log` events need 0.4.0 or newer; durations and the run timeline also work for older pipelines, with estimated step times. `waypoint_etl.metric` numbers per step, with optional units and warning limits, need 0.5.0 or newer. Loops tracked as a map step (`map_step`, `item`) need 0.6.0 or newer. The monitor works with any version.)

In `requirements.txt`, use the same line without `pip install`. Requires Python 3.10+.

### Let Claude Code set it up for you (recommended)

This repo ships a Claude Code skill, [`adopting-waypoint-etl`](.claude/skills/adopting-waypoint-etl/SKILL.md),
that installs the SDK, adds the Redis/env config, writes the `PipelineSpec`, decorates your steps and calls
`init` in your entry point. Copy it into your pipeline project once:

```bash
mkdir -p .claude/skills/adopting-waypoint-etl
curl -fsSL https://raw.githubusercontent.com/hoanglong1996/waypoint/main/.claude/skills/adopting-waypoint-etl/SKILL.md \
  -o .claude/skills/adopting-waypoint-etl/SKILL.md
```

(Private repo: clone it and copy the folder instead, or use `~/.claude/skills/` to enable it for all your projects.)
Then open Claude Code in your project and paste this prompt (fill in the three values):

```text
Use the adopting-waypoint-etl skill to add Waypoint tracking to this pipeline.

- SDK tag: waypoint-etl-v0.5.0
- Environment name: qa            (must match the monitor's ENVIRONMENTS)
- Redis URL: read from the REDIS_URL env var (do not hard-code or print it)

Inspect the project first and tell me the entry point, the steps you found and the files you plan to
change. Then: install the SDK from the git URL (dependency file and Dockerfile/CI), add REDIS_URL and the
env name to the existing config, write the PipelineSpec in its own module, decorate each step with
@audited_step, call waypoint_etl.init once in the entry point, and add an assert_spec_matches test.
Do not change business logic. Run the tests and import the entry point to verify, and finish with a
summary of changed files and the config values I must set.
```

It asks only for what it cannot find in the project. Review the diff, set `REDIS_URL` for real, and run the
pipeline once; the pipeline then appears in Waypoint Monitor under the chosen environment.

### Adopt it manually in 3 steps

**1. Declare the pipeline** (step names and how data flows between them):

```python
from waypoint_etl import PipelineSpec, StepSpec

SPEC = PipelineSpec(name="my-pipeline", steps=(
    StepSpec("extract"),
    StepSpec("clean", inputs=(("rows", "extract"),)),
    StepSpec("load", inputs=(("rows", "clean"),), returns_nothing=True),
))
```

`inputs=(("rows", "extract"),)` means: parameter `rows` comes from step `extract`.

**2. Configure once, in the entry point:**

```python
import os
import waypoint_etl

waypoint_etl.init(pipeline=SPEC, redis_url=os.getenv("REDIS_URL"), env="prod", ttl_days=30)
```

`env` must be one of the monitor's `ENVIRONMENTS`. `init` never raises: with a bad spec or no Redis URL it
prints a warning and the pipeline runs normally, unaudited.

**3. Mark each step function** (plain functions, methods and `async def` all work):

```python
@waypoint_etl.audited_step("clean")
def clean(rows): ...
```

Input counts come from the arguments, matched to the spec by **parameter name**. If a parameter is named
differently: `@audited_step("join", inputs={"a": "left", "b": "right"})`. Code that calls your steps does
not change.

Keep spec and code in sync with a test:

```python
from waypoint_etl.testing import assert_spec_matches
assert_spec_matches(SPEC, MyExtractUseCase, MyCleanUseCase)
```

### Try it without writing code

```bash
REDIS_URL=redis://localhost:6379/0 python packages/waypoint_etl/examples/sample_pipeline.py
```

Then open the monitor and choose the environment used in the example (`qa`).

### Behaviour to know

- A Redis failure is logged and swallowed. Your step results and exceptions are never changed.
- A heartbeat thread refreshes a small key every 15 s so the monitor can tell **Stalled** (alive, not progressing) from **Died** (process gone). Set `heartbeat_seconds=None` to turn it off.
- Counts: `None` is 0, list/tuple/set is its length, anything else is 1.

More detail: [`packages/waypoint_etl/README.md`](packages/waypoint_etl/README.md).

---

## 3. Releasing a new SDK version

1. Bump `version` in `packages/waypoint_etl/pyproject.toml` and `__version__` in `packages/waypoint_etl/src/waypoint_etl/__init__.py`.
2. Check: `cd packages/waypoint_etl && python -m unittest discover tests && black --check . && ruff check . && mypy .`
3. Tag and push:
   ```bash
   git tag waypoint-etl-vX.Y.Z && git push origin waypoint-etl-vX.Y.Z
   ```
4. Update the tag in the pipelines' `requirements.txt`.

If a release changes the stored record format, bump `FLOW_VERSION` too, so older dashboards show
"Unsupported record version" instead of wrong data.

## More docs

- [`deploy/README.md`](deploy/README.md): stack, Redis permissions, releasing
- [`waypoint_monitor/README.md`](waypoint_monitor/README.md): pages, statuses, Hung vs Died
- [`specs/`](specs): specs and contracts (Redis key format in `specs/007-rename-to-waypoint/contracts/redis-keys.md`)
