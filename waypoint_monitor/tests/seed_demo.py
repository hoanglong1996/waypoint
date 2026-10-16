"""Write three-step demo pipelines (flow, records, optional running marker) into a Redis.

Not a test: it is the helper for specs/005-self-describing-pipeline-graph/quickstart.md step 2 and
specs/008-pipelines-home-page/quickstart.md. It uses only the key layout in contracts/redis-keys.md,
never code from the pipeline.

    REDIS_URL=redis://localhost:6380/0 python -m tests.seed_demo [env [pipeline ...]]

Without pipeline names it writes `demo` (one step running), `facebook` (complete), `google_ads`
(a step that lost data) and `crashed` (a step was open and its last heartbeat is 3 minutes old, so
the monitor shows it as Died: specs/009-run-liveness-heartbeat). A name you give is written as a
complete run with that name as its label.
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


def main() -> None:
    env = sys.argv[1] if len(sys.argv) > 1 else "qa"
    names = sys.argv[2:]
    client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    plan = [(n, n, "complete") for n in names] if names else [(n, *DEFAULTS[n]) for n in DEFAULTS]
    written: List[str] = []
    for name, label, outcome in plan:
        written += seed(client, env, name, label, outcome)
    print("\n".join(written))


if __name__ == "__main__":
    main()
