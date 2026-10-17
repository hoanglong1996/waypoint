"""Write three-step demo pipelines (flow, records, optional running marker) into a Redis.

Not a test: it is the helper for specs/005-self-describing-pipeline-graph/quickstart.md step 2 and
specs/008-pipelines-home-page/quickstart.md. It uses only the key layout in contracts/redis-keys.md,
never code from the pipeline.

    REDIS_URL=redis://localhost:6380/0 python -m tests.seed_demo [env [pipeline ...]]

Without pipeline names it writes `demo` (one step running), `facebook` (complete), `google_ads`
(a step that lost data) and `crashed` (a step was open and its last heartbeat is 3 minutes old, so
the monitor shows it as Died: specs/009-run-liveness-heartbeat). `events` writes one finished run
with author events (500 info events of which 100 were dropped, warnings and errors on two steps).
`history` writes
ten finished runs hours apart (specs/012-duration-and-run-events): seven of about 10 minutes with exact
step durations, one that took 35 minutes (flagged Slower than usual), one from an older library
(no step start times) and one whose last step failed. A name you give is written as a complete run
with that name as its label. `metrics` writes twelve finished runs (specs/013-step-metrics): the
`clean` step declares `rejected` (rows, warn above 100) and `coverage` (%, warn below 90) and also sends an
undeclared `retries`; `rejected` rises from 40 to 150 so the newest runs are over the limit, one run did not
report it, and the newest run is still running with a metric growing in its open step.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List

import redis

STEPS = [
    {"name": "extract", "label": "Extract", "group": "etl", "inputs": []},
    {
        "name": "clean",
        "label": "Clean",
        "group": "etl",
        "inputs": [{"name": "rows", "from": "extract"}],
    },
    {
        "name": "load",
        "label": "Load",
        "group": "out",
        "inputs": [{"name": "rows", "from": "clean"}],
    },
]
GROUPS = [{"key": "etl", "label": "ETL"}, {"key": "out", "label": "Output"}]
COUNTS = {"extract": (None, 120), "clean": (120, 118), "load": (118, 118)}


# name -> (label, outcome); outcome is running, complete, loss or died
DEFAULTS = {
    "demo": ("Demo pipeline", "running"),
    "facebook": ("Facebook Ads", "complete"),
    "google_ads": ("Google Ads", "loss"),
    "crashed": ("Crashed pipeline", "died"),
    "history": ("History demo", "history"),
    "events": ("Events demo", "events"),
    "metrics": ("Metrics demo", "metrics"),
}


def seed(client: redis.Redis, env: str, name: str, label: str, outcome: str) -> List[str]:
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = f"waypoint:{name}:{env}:{run_id}"
    ttl = 3600
    written: List[str] = []

    def put(key: str, value: dict) -> None:  # type: ignore[type-arg]
        client.setex(key, ttl, json.dumps(value))
        written.append(key)

    put(
        f"{root}:flow",
        {
            "v": 1,
            "pipeline": name,
            "env": env,
            "run_id": run_id,
            "label": label,
            "groups": GROUPS,
            "steps": STEPS,
        },
    )
    counts = dict(COUNTS)
    if outcome == "loss":
        counts["clean"] = (120, 0)
        counts["load"] = (0, 0)
    open_step = outcome in ("running", "died")
    reported = ["extract", "clean"] if open_step else ["extract", "clean", "load"]
    for index, step in enumerate(reported, start=1):
        inputs, output = counts[step]
        put(
            f"{root}:step:{index:02d}-{step}",
            {
                "pipeline": name,
                "run_id": run_id,
                "env": env,
                "step": step,
                "index": index,
                "inputs": {} if inputs is None else {"rows": inputs},
                "output": output,
                "finished_at": (now + timedelta(seconds=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    if outcome == "died":
        beat = now - timedelta(minutes=3)
        put(
            f"{root}:alive",
            {
                "v": 1,
                "pipeline": name,
                "env": env,
                "run_id": run_id,
                "beat_at": beat.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    if open_step:
        put(
            f"{root}:running:03-load",
            {
                "pipeline": name,
                "run_id": run_id,
                "env": env,
                "step": "load",
                "index": 3,
                "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    return written


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_history(client: redis.Redis, env: str, name: str, label: str) -> List[str]:
    """Ten finished runs, newest first one hour back: see the module docstring."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ttl = 86400
    written: List[str] = []
    # (hours back, seconds per step extract/clean/load, kind)
    plan = [(1, (60, 330, 210), "ok"), (2, (210, 1500, 390), "slow"), (3, (65, 300, 240), "old")]
    plan += [(4, (70, 320, 230), "failed")]
    plan += [(h, (55 + h, 310 + h * 5, 225), "ok") for h in range(5, 11)]
    for hours, seconds, kind in plan:
        start = (now - timedelta(hours=hours)).replace(minute=0, second=0)
        run_id = start.strftime("%Y%m%dT%H%M%SZ")
        root = f"waypoint:{name}:{env}:{run_id}"

        def put(key: str, value: dict) -> None:  # type: ignore[type-arg]
            client.setex(key, ttl, json.dumps(value))
            written.append(key)

        put(
            f"{root}:flow",
            {
                "v": 1,
                "pipeline": name,
                "env": env,
                "run_id": run_id,
                "label": label,
                "groups": GROUPS,
                "steps": STEPS,
            },
        )
        clock = start
        steps = STEPS[:2] if kind == "failed" else STEPS
        for index, step in enumerate(steps, start=1):
            began, clock = clock, clock + timedelta(seconds=seconds[index - 1])
            inputs, output = COUNTS[step["name"]]  # type: ignore[index]
            record = {
                "pipeline": name,
                "run_id": run_id,
                "env": env,
                "step": step["name"],
                "index": index,
                "inputs": {} if inputs is None else {"rows": inputs},
                "output": output,
                "finished_at": _stamp(clock),
            }
            if kind != "old":
                record["started_at"] = _stamp(began)
                record["duration_ms"] = seconds[index - 1] * 1000
            if kind == "failed" and index == 2:
                put(
                    f"{root}:failed:{index:02d}-{step['name']}",
                    {
                        "v": 1,
                        "pipeline": name,
                        "env": env,
                        "run_id": run_id,
                        "step": step["name"],
                        "index": index,
                        "started_at": _stamp(began),
                        "failed_at": _stamp(clock),
                        "error": {
                            "type": "ValueError",
                            "message": "bad row",
                            "traceback": '  File "clean.py", line 9, in run\n    raise ValueError()\n',
                        },
                    },
                )
                continue
            put(f"{root}:step:{index:02d}-{step['name']}", record)
    return written


def seed_metrics(client: redis.Redis, env: str, name: str, label: str) -> List[str]:
    """Twelve runs, newest first one hour back, with step metrics: see the module docstring."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ttl = 86400
    written: List[str] = []
    declared = [
        {"name": "rejected", "label": "Rejected rows", "unit": "rows", "warn_above": 100},
        {"name": "coverage", "unit": "%", "warn_below": 90},
    ]
    steps = [dict(s, **({"metrics": declared} if s["name"] == "clean" else {})) for s in STEPS]
    for hours in range(1, 13):
        start = (now - timedelta(hours=hours)).replace(minute=0, second=0)
        run_id = start.strftime("%Y%m%dT%H%M%SZ")
        root = f"waypoint:{name}:{env}:{run_id}"
        rejected = 40 + (12 - hours) * 10  # 150 for the newest finished run, 40 for the oldest
        running = hours == 1

        def put(key: str, value: dict) -> None:  # type: ignore[type-arg]
            client.setex(key, ttl, json.dumps(value))
            written.append(key)

        put(
            f"{root}:flow",
            {
                "v": 1, "pipeline": name, "env": env, "run_id": run_id, "label": label,
                "groups": GROUPS, "steps": steps,
            },
        )  # fmt: skip
        clock = start
        for index, step in enumerate(STEPS, start=1):
            began, clock = clock, clock + timedelta(seconds=60 * index)
            inputs, output = COUNTS[step["name"]]  # type: ignore[index]
            if running and step["name"] == "clean":
                put(
                    f"{root}:running:{index:02d}-clean",
                    {"pipeline": name, "run_id": run_id, "env": env, "step": "clean",
                     "index": index, "started_at": _stamp(now - timedelta(seconds=40))},
                )  # fmt: skip
                break
            put(
                f"{root}:step:{index:02d}-{step['name']}",
                {
                    "pipeline": name, "run_id": run_id, "env": env, "step": step["name"],
                    "index": index, "inputs": {} if inputs is None else {"rows": inputs},
                    "output": output, "finished_at": _stamp(clock),
                    "started_at": _stamp(began), "duration_ms": 60_000 * index,
                },
            )  # fmt: skip
        values = {"rejected": rejected, "coverage": 96 - hours % 3, "retries": hours % 4}
        if hours == 5:
            values.pop("rejected")  # one run did not report it: a gap in the trend
        if running:
            values = {"rejected": 130, "retries": 2}  # still growing in the open step
        put(
            f"{root}:metrics:02-clean",
            {
                "v": 1, "pipeline": name, "env": env, "run_id": run_id, "step": "clean",
                "index": 2, "updated_at": _stamp(now), "metrics": values,
            },
        )  # fmt: skip
    return written


def seed_events(client: redis.Redis, env: str, name: str, label: str) -> List[str]:
    """One finished run (seed() with outcome complete) plus author events in the three event lists."""
    written = seed(client, env, name, label, "complete")
    run_id = next(k for k in written if k.endswith(":flow")).split(":")[3]
    start = datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    ttl = 3600

    def stamp(offset_ms: int) -> str:
        return (start + timedelta(milliseconds=offset_ms)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ] + "Z"

    def element(n: int, level: str, offset_ms: int, message: str, step: str, fields: dict) -> str:  # type: ignore[type-arg]
        value = {
            "v": 1,
            "n": n,
            "ts": stamp(offset_ms),
            "level": level,
            "step": step,
            "message": message,
        }
        if fields:
            value["fields"] = fields
        return json.dumps(value)

    info = [
        element(100 + i, "info", 100 + i * 4, f"Loaded batch {i}", "clean", {"rows": 100 + i})
        for i in range(1, 501)
    ]
    warning = [
        element(601, "warning", 1100, "slow source, retrying", "extract", {"retries": 2}),
        element(602, "warning", 1400, "12 rows had no phone number", "clean", {"rows": 12}),
        element(603, "warning", 1900, "<b>markup</b> in a message is shown as text", "load", {}),
    ]
    error = [
        element(604, "error", 1500, "one batch skipped", "clean", {"batch": 7}),
        element(605, "error", 2000, "could not reach the audit endpoint", "load", {}),
    ]
    for level, items in (("info", info), ("warning", warning), ("error", error)):
        key = f"waypoint:{name}:{env}:{run_id}:events:{level}"
        client.delete(key)
        client.rpush(key, *items)
        client.expire(key, ttl)
        written.append(key)
    return written


def main() -> None:
    env = sys.argv[1] if len(sys.argv) > 1 else "qa"
    names = sys.argv[2:]
    client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    plan = [(n, n, "complete") for n in names] if names else [(n, *DEFAULTS[n]) for n in DEFAULTS]
    written: List[str] = []
    for name, label, outcome in plan:
        if outcome == "history":
            written += seed_history(client, env, name, label)
        elif outcome == "events":
            written += seed_events(client, env, name, label)
        elif outcome == "metrics":
            written += seed_metrics(client, env, name, label)
        else:
            written += seed(client, env, name, label, outcome)
    print("\n".join(written))


if __name__ == "__main__":
    main()
