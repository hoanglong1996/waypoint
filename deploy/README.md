# Waypoint Stack

Waypoint has three parts: **Redis** (stores step records), **Waypoint Monitor** (the dashboard,
`../waypoint_monitor`, read-only) and the **Waypoint library** (`waypoint-etl`,
`../packages/waypoint_etl`, used inside each pipeline). This folder brings the first two up together.

## Bring up Redis + Waypoint Monitor

```bash
docker compose -f deploy/docker-compose.yml up --build   # http://localhost:8080
```

Redis is not published to the host. To let a pipeline running elsewhere write to it, publish the port
(or use your own Redis) and point the pipeline's `REDIS_URL` at it. The dashboard has no login, so
keep it on an internal network or behind your usual access control.

## Redis permissions

The pipeline account writes `waypoint:*`. The monitor's account reads (`SCAN`, `MGET`, `PING`, and `LLEN`, `LRANGE` for
the event lists) and has exactly one
write: `SET` (with `PTTL`) on keys matching `waypoint:*:died`, the verdict it stores when a run's process is
gone (`specs/009-run-liveness-heartbeat/contracts/redis-keys.md`). With read-only access the monitor still works, but
a Died verdict is then not kept across monitor restarts; without `LLEN`/`LRANGE` pipeline events are not shown.

## Point a pipeline at it

Set `REDIS_URL` for the pipeline (CallRail reads it through `src/utils/config.py`) and call
`waypoint_etl.init(...)` once in its entry point. Full adoption guide:
`packages/waypoint_etl/README.md`. All keys are written under the `waypoint:` prefix
(`specs/007-rename-to-waypoint/contracts/redis-keys.md`).

## Install the library from another repository

```bash
pip install "waypoint-etl[redis] @ git+https://github.com/hoanglong1996/waypoint.git@waypoint-etl-v0.5.0#subdirectory=packages/waypoint_etl"
```

For a private repository use `git+ssh://git@github.com/hoanglong1996/waypoint.git@...` (deploy key) or
`git+https://x-access-token:${GH_TOKEN}@github.com/hoanglong1996/waypoint.git@...` (token) in CI. Always install with the
full URL above: do not `pip install waypoint-etl` by bare name, and do not publish the library to the
public package index without reserving the name first.

## Release a new library version

1. Bump `version` in `packages/waypoint_etl/pyproject.toml` and `__version__` in
   `packages/waypoint_etl/src/waypoint_etl/__init__.py`.
2. Run the package tests and checks (`cd packages/waypoint_etl && python -m unittest discover tests && black --check . && ruff check . && mypy .`).
3. Tag and push: `git tag waypoint-etl-vX.Y.Z && git push origin waypoint-etl-vX.Y.Z`.

If a release changes the stored record format, bump `FLOW_VERSION` too. Dashboards that do not know
the new version show "Unsupported record version" for those runs instead of wrong data.

## Renaming from the previous names

Moving an existing installation to Waypoint (new key prefix, new names) needs a cutover; the order
and the list of what changed are in [RENAME.md](RENAME.md).
