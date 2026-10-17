# Waypoint Monitor

The dashboard of Waypoint: a small web page for ETL pipelines such as CallRail. It only reads, with one exception: it stores a small "died" verdict when it first sees that a run's process is gone (see "Hung or dead?"). It reads
the per-step records a pipeline writes to Redis with the Waypoint library (`../packages/waypoint_etl`) and shows, for each run,
how many items went in and out of every step, so you can see at a glance whether last night's run
worked and where data dropped off. Only counts are stored and shown, never caller data.

- History (earlier specs, kept under their original names). Spec, plan and API contract: `../specs/002-pipeline-monitor-dashboard/`
- Spec and plan for the graph view: `../specs/003-pipeline-directed-graph/`
- Visual design (source of the front end): `../docs/design/pipeline-monitor-degisn/` and, for the graph view, `../docs/design/pipeline-monitor-graph-update/`

## Run

```bash
cd waypoint_monitor
pip install -r requirements.txt
cp .env.example .env.qa        # then edit REDIS_URL etc.
python -m app.main -c qa       # loads .env.qa, serves http://localhost:8080
```

Like the pipeline, `-c <name>` loads `.env.<name>` from the current folder (`-c prod` → `.env.prod`).
Without `-c` it loads `.env` if present. Variables already set in the real environment win over the
file, so `PORT=9000 python -m app.main -c qa` still works. `.env*` files are git-ignored (only
`.env.example` is tracked) because a Redis URL can contain a password.

```bash
docker build -t waypoint-monitor .
docker run -p 8080:8080 -e REDIS_URL=redis://host:6379/0 waypoint-monitor
# or mount an env file:  -v $PWD/.env.qa:/app/.env.qa waypoint-monitor -c qa
```

## Steps view: List | Graph

Under "Steps" on a run's page, a **List | Graph** switch chooses how a
run's steps are shown. The graph draws each step as a node and each hand-off as an arrow
(`A → B` means A's output is B's input), with the count on the arrow, data-loss and not-reported
states, and a click-to-trace selection. **Nothing about the pipeline is built into the monitor**:
steps, hand-offs, groups, friendly names and optional layout hints all come from the *flow
description* each run stores in Redis (see "Add a pipeline" below), and positions are computed from
the hand-offs. A run with no usable flow description is drawn as a plain row of the steps that
reported, with a note saying so; a run written in a newer record format than this dashboard knows
says "Unsupported record version" instead. The choice is remembered in `localStorage['wp-steps-view']` and
defaults to Graph.

## Pages and addresses

Every page has its own address (in the URL hash), so reload, Back/Forward and shared links open the same view.

| Address | Page |
| --- | --- |
| `#/` | **Home**: one card per pipeline that has a run, showing its newest run in any environment (environment tag, status, time since, three numbers). Pipelines that need attention (Stale, Incomplete, Lost data) come first. |
| `#/p/<pipeline>` (same as `#/p/<pipeline>/history`) | **History** of that pipeline: the opening page of a pipeline. The newest run is the first row, tagged "Newest". |
| `#/p/<pipeline>/history?env=<env>` | History limited to one environment by the *Environment* filter (default: prod if the pipeline has prod runs, else the environment of its newest run). The trend and the runs list follow the filter. A home card links here with the environment of the run it shows. |
| `#/p/<pipeline>/runs/<env>/<run id>` | **Run page**: one run in full (status, headline counts, step flow, steps as List or Graph). Selecting a run in History opens it; the pipeline name in the breadcrumb returns to that History. A run that is not found shows "Run not found". |
| anything else | "Pipeline not found" with a link home. |

Pipelines are discovered from Redis in every configured environment (`ENVIRONMENTS`, default `prod,qa`); there is no
list to maintain and no remembered pipeline setting. The home page reads one endpoint, `GET /api/overview`
(`../specs/008-pipelines-home-page/contracts/api.md`). Card status, first match wins: Running, **Died** (the run's
process is gone), Stale (older than `STALE_HOURS`), Incomplete (stopped or stalled), Lost data, Completed.

## Add a pipeline

No monitor change and no new monitor setting. In the pipeline (full guide:
`../packages/waypoint_etl/README.md`):

1. Install the library: `pip install "waypoint-etl[redis]"` (see `../deploy/README.md` for the git URL).
2. Declare the pipeline once: a `PipelineSpec(name, steps=(StepSpec(...), ...))` with each step's
   inputs and producers and, optionally, labels, groups and `col`/`row` layout hints. The CallRail
   job's `src/application/pipeline_spec.py` is the worked example.
3. Call `waypoint_etl.init(pipeline=SPEC, redis_url=..., env=...)` once in the entry point and mark
   each step function with `@waypoint_etl.audited_step("step_name")`. The code that calls the steps
   does not change.

It then writes the keys in `../specs/007-rename-to-waypoint/contracts/redis-keys.md`
and the pipeline gets a card on the home page. Only names and counts are stored, never item contents.
`python -m tests.seed_demo qa` writes three demo pipelines (`demo` with a running step, `facebook`, and `google_ads` with a lost-data step) for a quick look; `python -m tests.seed_demo qa my_job` adds one complete run for a pipeline of your own name.

## Configuration (env file or environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | *(none)* | Redis holding the pipeline's step records. |
| `ENVIRONMENTS` | `prod,qa` | Environments read for the home cards and offered in the History filter. |
| `STALE_HOURS` | `26` | Warn when the newest run finished longer ago than this; also marks a card **Stale**. |
| `REFRESH_SECONDS` | `5` | How often an open page reloads its data (whether or not a run is in progress). |
| `RETRY_SECONDS` | `30` | Retry interval while the data store is unreachable. |
| `CACHE_SECONDS` | `2` | Server-side cache so many viewers don't hammer Redis. Keep it below `REFRESH_SECONDS`, or updates appear late. |
| `STALL_SECONDS` | `900` | A step that has been running longer than this is shown as **Stalled** (no longer animated) and counts as where the run stopped. |
| `HEARTBEAT_DEAD_SECONDS` | `90` | A run whose latest heartbeat is older than this, with unfinished work, is shown as **Died**. Six missed 15 s beats by default. See "Hung or dead?". |
| `PORT` | `8080` | HTTP port. |

## What it reads

Per pipeline, run and environment (`waypoint:{pipeline}:{env}:{run_id}:...`, full contract in
`../specs/007-rename-to-waypoint/contracts/redis-keys.md`):

- `...:flow`: the run's flow description (steps, hand-offs, groups, labels, hints);
- `...:step:{NN}-{step}`: one JSON step record per finished step (counts and finish time);
- `...:running:{NN}-{step}`: the start marker written just before each step;
- `...:alive`: the run's heartbeat, refreshed every 15 s while its process lives (`{"v":1, ... , "beat_at"}`);
- `...:died`: the monitor's own verdict that a run died (written by the monitor, see below);
- `...:failed:{NN}-{step}`: written by the pipeline when a step raised (error type, shortened message, shortened
  stack trace; `waypoint-etl` 0.3.0 or newer). The monitor only reads it.

A marker with no finish record for the same step means the step is **running** (or **stalled** past
`STALL_SECONDS`); later planned steps of that run show **Waiting**. A planned step with no record is
**not reached**; a record for a step that is not in the run's flow shows under "Other steps".
Keys under any other prefix, including those written before the rename to Waypoint, are ignored. The page reloads
itself every `REFRESH_SECONDS` and only redraws when something changed, so spinners and your selection
are not disturbed. It runs `SCAN`, `MGET` and `PING`, plus one write: `PTTL` of a run's heartbeat and `SET ... NX PX` of its `...:died` verdict (see "Hung or dead?"). It never deletes and never changes anything a pipeline wrote. Malformed
records are skipped, counted, and shown as "unreadable"; a malformed flow description draws the part
that is valid and lists what was dropped. Endpoints: `/api/health`, `/api/config`,
`/api/pipelines?env=`, `/api/runs?env=&pipeline=&limit=` (see
`../specs/005-self-describing-pipeline-graph/contracts/api.md`).

## Failed steps

A step that raised an error is **Failed** at once (no waiting for a stall or death threshold), with its error type,
message and stack trace in the step details (scrollable, with a Copy button). A step is Failed when its latest
attempt failed; a retry that is running or has finished replaces it. The **run** is Failed only when the failure
stopped the pipeline, meaning no later step was started; the steps after it show **Not reached**. If the pipeline
caught the error and carried on, only that step is marked Failed and the run keeps its own state (a failed planned
step does not count as finished, so such a run is Incomplete, never Completed). A Failed run is never judged Died,
even though its heartbeat stops, and the monitor writes no died verdict for it. Priority for the card and the run:
Running, **Failed**, Died, Stale, Incomplete, Lost data, Completed; Failed cards lead the "Needs attention" group.
History marks Failed runs and has an "All runs / Failed only" filter.

Error text is data from your pipeline, shown as plain text only. It is capped (message 500 characters, trace 8 KB)
on both sides. Pipelines choose in `waypoint_etl.init` whether messages are stored and may pass a cleaning function
(see the library README). No new Redis permission is needed. Older pipelines send no failure items and look as before.

## Hung or dead?

A step that has started but not finished is **Running**, then **Stalled** after `STALL_SECONDS`. What tells a
hung run from a dead one is the heartbeat (`waypoint-etl` 0.2.0 or newer, `../specs/009-run-liveness-heartbeat/`):

| Heartbeat | Unfinished step | Shown as |
| --- | --- | --- |
| newer than `HEARTBEAT_DEAD_SECONDS` | within `STALL_SECONDS` | **Running** |
| newer than `HEARTBEAT_DEAD_SECONDS` | longer than `STALL_SECONDS` | **Stalled**: the process is alive but not progressing |
| older than `HEARTBEAT_DEAD_SECONDS` | any | **Died**: the process is gone, shown right away |
| none ever sent (older pipeline version) | any | as before: Running, then Stalled; never Died |

Died is permanent. The first time the monitor judges a run Died it stores one small item,
`waypoint:{pipeline}:{env}:{run_id}:died` (ids and two times, no business data), with `SET ... NX` and the
remaining life of the run's heartbeat item as expiry. Every later view, restart or second monitor instance reads it
and shows the run as Died even if heartbeats resume. If the write fails (Redis down, or an account without write
permission) the run is still shown as Died on each view and the write is retried; a warning is logged at most once
a minute, but the verdict is then not kept across restarts. A run whose steps are all recorded is never newly
judged Died. A run that exits cleanly after skipping planned steps is also shown as Died once its heartbeat ages out.

Limits: the pipeline host's clock and the monitor's clock must agree within `HEARTBEAT_DEAD_SECONDS`, and only the
pipeline's main process beats (the death of a child process alone is not seen).

## Security

There is no login in v1: it is meant for an internal network and only exposes counts. Its Redis account needs
`SCAN`, `MGET`, `PING` and `PTTL`, plus `SET` on keys matching `waypoint:*:died` (nothing else may be written);
without `SET` the monitor still works, but a Died verdict is not kept across restarts. Put it
behind your usual access control (VPN, reverse proxy with auth) before exposing it more widely.

## Development

```bash
python -m unittest discover tests      # backend, no Redis needed
node --test static/tests               # front-end rules (Node 18+, tests only)
black . && ruff check . && mypy .
```

The front end is plain HTML, CSS and ES modules under `static/` (no build step, no JS
libraries). The only external request is the optional Geist font; without it the system font is used.
