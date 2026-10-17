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
`maps` writes one run per map step state (specs/014-map-step-fan-out) into the pipeline `maps`: running with
no failure, running with one failed item (a slow running item and an item that lost data), failed, done,
done with an item that lost data, zero items started, zero items, stalled, died, a 10,000-item loop with
partial detail, and one from a library without map steps. Each run has a clock-based id, newest first.
"""

import json
import math
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
    "maps": ("Map step demo", "maps"),
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


# ---- map step demo (specs/014-map-step-fan-out) ------------------------------------------------------

MAP_STEPS = [
    {"name": "list_accounts", "label": "Accounts", "inputs": []},
    {
        "name": "accounts",
        "label": "Accounts",
        "kind": "map",
        "inputs": [{"name": "accounts", "from": "list_accounts"}],
        "over": "list_accounts",
        "max_concurrency": 5,
        "steps": [
            {"name": "fetch", "inputs": []},
            {
                "name": "transform",
                "inputs": [{"name": "rows", "from": "fetch"}],
                "metrics": [{"name": "rejected", "unit": "rows", "warn_above": 100}],
            },
            {"name": "load", "inputs": [{"name": "rows", "from": "transform"}]},
        ],
    },
    {"name": "publish", "label": "Publish", "inputs": [{"name": "done", "from": "accounts"}]},
]
PLAIN_STEPS = [
    {k: v for k, v in step.items() if k not in ("kind", "over", "max_concurrency", "steps")}
    for step in MAP_STEPS
]
TRACE = (
    '  File "transform.py", line 31, in transform\n    parse(row["date"])\nValueError: bad date\n'
)


def _bucket(ms: int) -> int:
    return int(math.floor(math.log(ms) / math.log(1.1))) if ms >= 1 else 0


def _inner(
    state: str = "done",
    *,
    failed_at: str = "",
    loss_at: str = "",
    running: str = "",
    started: str = "",
    transform_ms: int = 1500,
) -> List[dict]:  # type: ignore[type-arg]
    """Inner step results of one item (fetch -> transform -> load), see contracts/redis-keys.md."""
    out: List[dict] = []  # type: ignore[type-arg]
    rows = 48
    for name in ("fetch", "transform", "load"):
        result = {
            "step": name,
            "attempt": 1,
            "inputs": {"account": 1} if name == "fetch" else {"rows": rows},
            "started_at": started,
        }
        ms = transform_ms if name == "transform" else 700
        if name == running:
            out.append(dict(result, state="running", output=None))
            break
        if name == failed_at:
            error = {"type": "ValueError", "message": "bad date", "traceback": TRACE}
            out.append(dict(result, state="failed", output=None, duration_ms=ms, error=error))
            break
        rows = 0 if name == loss_at else rows
        out.append(dict(result, state="done", output=rows, duration_ms=ms))
    return out


def seed_maps(client: redis.Redis, env: str, name: str, label: str) -> List[str]:
    """One run per map step state, newest first: see the module docstring."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ttl = 86400
    written: List[str] = []

    def put(key: str, value: dict) -> None:  # type: ignore[type-arg]
        client.setex(key, ttl, json.dumps(value))
        written.append(key)

    def run(minutes_back: float, case: str) -> None:
        start = now - timedelta(minutes=minutes_back)
        run_id = start.strftime("%Y%m%dT%H%M%SZ")
        root = f"waypoint:{name}:{env}:{run_id}"
        plain = case == "premap"
        put(
            f"{root}:flow",
            {
                "v": 1, "pipeline": name, "env": env, "run_id": run_id, "label": label,
                "steps": PLAIN_STEPS if plain else MAP_STEPS,
            },
        )  # fmt: skip

        def step_record(
            index: int, step: str, began: datetime, seconds: int, **counts: object
        ) -> None:
            put(
                f"{root}:step:{index:02d}-{step}",
                {
                    "pipeline": name, "run_id": run_id, "env": env, "step": step, "index": index,
                    "inputs": counts.get("inputs", {}), "output": counts.get("output"),
                    "started_at": _stamp(began), "duration_ms": seconds * 1000,
                    "finished_at": _stamp(began + timedelta(seconds=seconds)),
                },
            )  # fmt: skip

        step_record(1, "list_accounts", start, 2, output=10)
        map_start = start + timedelta(seconds=2)
        open_block = case in ("running_ok", "running_fail", "zero_started", "stalled", "died")
        if plain:
            step_record(2, "accounts", map_start, 38, inputs={"accounts": 10}, output=10)
            step_record(3, "publish", map_start + timedelta(seconds=38), 3, inputs={"done": 10})
            return
        if open_block:
            put(
                f"{root}:running:02-accounts",
                {"pipeline": name, "run_id": run_id, "env": env, "step": "accounts",
                 "index": 2, "started_at": _stamp(map_start)},
            )  # fmt: skip
        if case in ("running_ok", "running_fail"):
            put(
                f"{root}:alive",
                {"v": 1, "pipeline": name, "env": env, "run_id": run_id, "beat_at": _stamp(now)},
            )
        if case == "died":
            put(
                f"{root}:alive",
                {"v": 1, "pipeline": name, "env": env, "run_id": run_id,
                 "beat_at": _stamp(now - timedelta(minutes=20))},
            )  # fmt: skip
        # item rows: (key, state, duration ms, inner results, metrics)
        items: List[tuple] = []  # type: ignore[type-arg]
        durations: List[int] = []
        failed_items: List[dict] = []  # type: ignore[type-arg]
        counts = {"running": 0, "done": 0, "failed": 0}
        kept = 0
        failed_without_record = 0
        if case in ("running_ok", "stalled", "died"):
            ndone = 6 if case == "running_ok" else 3
            for i in range(1, 11 if case == "running_ok" else 6):
                began = _stamp(map_start + timedelta(seconds=i))
                if i <= ndone:
                    ms = 3000 + i * 150
                    items.append((i, "done", ms, _inner(started=began, transform_ms=ms - 1400), {}))
                    counts["done"] += 1
                    durations.append(ms)
                else:
                    step = "load" if i % 2 else "transform"
                    items.append((i, "running", None, _inner(running=step, started=began), {}))
                    counts["running"] += 1
        elif case == "running_fail":
            for i in range(1, 11):
                began = _stamp(map_start + timedelta(seconds=i))
                if i == 4:
                    ms = 6400
                    items.append(
                        (i, "failed", ms, _inner(failed_at="transform", started=began), {})
                    )
                    counts["failed"] += 1
                    failed_items.append(
                        {"key": "acct-4", "step": "transform", "error_type": "ValueError"}
                    )
                    durations.append(ms)
                elif i == 3:
                    ms = 3400
                    metrics = {"transform": {"rejected": 150}}
                    items.append(
                        (i, "done", ms, _inner(loss_at="transform", started=began), metrics)
                    )
                    counts["done"] += 1
                    durations.append(ms)
                elif i <= 6:
                    ms = 3000 + i * 130
                    items.append((i, "done", ms, _inner(started=began), {}))
                    counts["done"] += 1
                    durations.append(ms)
                else:
                    # acct-9 has run for far longer than twice the median: a slow running item
                    began = _stamp(now - timedelta(seconds=45)) if i == 9 else began
                    items.append(
                        (i, "running", None, _inner(running="transform", started=began), {})
                    )
                    counts["running"] += 1
        elif case in ("failed", "done", "done_lost"):
            for i in range(1, 11):
                began = _stamp(map_start + timedelta(seconds=i))
                if case == "failed" and i == 7:
                    ms = 9120
                    metrics = {"transform": {"rejected": 4}}
                    items.append(
                        (i, "failed", ms, _inner(failed_at="transform", started=began), metrics)
                    )
                    counts["failed"] += 1
                    failed_items.append(
                        {"key": "acct-7", "step": "transform", "error_type": "ValueError"}
                    )
                elif case == "done_lost" and i == 3:
                    ms = 3300
                    items.append((i, "done", ms, _inner(loss_at="transform", started=began), {}))
                    counts["done"] += 1
                else:
                    ms = 3000 + i * 100
                    items.append((i, "done", ms, _inner(started=began), {}))
                    counts["done"] += 1
                durations.append(ms)
        elif case == "large":
            durations = [2500 + (i * 37) % 2400 for i in range(1, 10_001)]
            # records: the first 1,000 items (151 of them failed) and the 50 slowest later ones
            first_failed = 0
            for i in range(1, 1001):
                began = _stamp(map_start + timedelta(seconds=i // 40))
                ms = 2500 + (i * 37) % 2400
                if first_failed < 151 and i % 6 == 0:
                    first_failed += 1
                    items.append(
                        (i, "failed", ms, _inner(failed_at="transform", started=began), {})
                    )
                    failed_items.append(
                        {"key": f"acct-{i}", "step": "transform", "error_type": "ValueError"}
                    )
                else:
                    items.append((i, "done", ms, _inner(started=began), {}))
            for n in range(50):
                i = 2000 + n * 100
                began = _stamp(map_start + timedelta(seconds=i // 40))
                items.append(
                    (i, "done", 20000 + n * 150, _inner(started=began, transform_ms=18000), {})
                )
            counts = {"running": 0, "done": 10_000 - 188, "failed": 188}
            failed_items = failed_items[:20]
            kept = len(items)
            failed_without_record = 188 - first_failed
        elif case == "zero_started":
            pass
        # the aggregate
        started = counts["running"] + counts["done"] + counts["failed"]
        hist: dict = {}  # type: ignore[type-arg]
        for ms in durations:
            hist[str(_bucket(ms))] = hist.get(str(_bucket(ms)), 0) + 1
        slowest = sorted(
            ((f"acct-{i}", ms) for i, st, ms, _s, _m in items if ms), key=lambda t: -t[1]
        )[:5]
        lost = sum(
            1
            for _i, _st, _ms, steps, _m in items
            if any(r["state"] == "done" and r["output"] == 0 and r["inputs"] for r in steps)
        )
        ended = None if open_block else _stamp(map_start + timedelta(seconds=40))
        inner_counts: dict = {}  # type: ignore[type-arg]
        for _i, _st, _ms, steps, _m in items:
            for r in steps:
                entry = inner_counts.setdefault(
                    r["step"], {"running": 0, "done": 0, "failed": 0, "in": 0, "out": 0}
                )
                entry[r["state"]] += 1
                entry["in"] += sum(r["inputs"].values())
                entry["out"] += r["output"] or 0
        put(
            f"{root}:map:accounts",
            {
                "v": 1, "pipeline": name, "env": env, "run_id": run_id, "map": "accounts", "index": 2,
                "started_at": _stamp(map_start), "ended_at": ended, "updated_at": _stamp(now),
                "counts": {"started": started, **counts},
                "in_total": 48 * started, "out_total": 48 * (counts["done"]), "lost_items": lost,
                "inner": inner_counts,
                "duration": {
                    "count": len(durations), "sum_ms": sum(durations), "hist": hist,
                    "slowest": [{"key": k, "ms": ms} for k, ms in slowest],
                },
                "failed_items": failed_items,
                "detail": {
                    "limit": 1000, "kept": kept or started, "extra_failed_limit": 1000,
                    "failed_without_record": failed_without_record, "slow_kept": 50 if case == "large" else 0,
                },
            },
        )  # fmt: skip
        for i, state, ms, steps, metrics in items:
            began = steps[0]["started_at"] if steps else _stamp(map_start)
            record = {
                "v": 1, "pipeline": name, "env": env, "run_id": run_id, "map": "accounts",
                "key": f"acct-{i}", "index": i, "state": state, "started_at": began, "steps": steps,
            }  # fmt: skip
            if state != "running":
                begun = datetime.strptime(began, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                record["finished_at"] = _stamp(begun + timedelta(milliseconds=ms or 0))
                record["duration_ms"] = ms
            if metrics:
                record["metrics"] = metrics
            put(f"{root}:item:accounts:acct-{i}", record)
        if ended is not None:
            seconds = 40
            step_record(2, "accounts", map_start, seconds, inputs={"accounts": 10}, output=started)
            step_record(
                3, "publish", map_start + timedelta(seconds=seconds), 3, inputs={"done": 10}
            )
        # events recorded inside items
        if case in ("failed", "running_fail"):
            key = "acct-7" if case == "failed" else "acct-9"
            events = [
                (1, "info", "Fetched rows", "fetch", {"rows": 48}),
                (2, "warning", "slow response from the source", "transform", {"retries": 2}),
            ]
            if case == "failed":
                events.append((3, "error", "bad date in row 17", "transform", {"row": 17}))
            for n, level, message, step, fields in events:
                stamp = (map_start + timedelta(seconds=n + 3)).strftime("%Y-%m-%dT%H:%M:%S.250Z")
                body = {"v": 1, "n": n, "ts": stamp, "level": level, "step": step,
                        "message": message, "fields": fields, "item": key}  # fmt: skip
                events_key = f"{root}:events:{level}"
                client.rpush(events_key, json.dumps(body))
                client.expire(events_key, ttl)
                written.append(events_key)

    for minutes, case in (
        (3, "running_ok"),
        (6, "running_fail"),
        (10, "failed"),
        (20, "done"),
        (25, "done_lost"),
        (1.5, "zero_started"),
        (30, "zero_items"),
        (180, "stalled"),
        (40, "died"),
        (120, "large"),
        (45, "premap"),
    ):
        run(minutes, case)
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
        elif outcome == "maps":
            written += seed_maps(client, env, name, label)
        else:
            written += seed(client, env, name, label, outcome)
    print("\n".join(written))


if __name__ == "__main__":
    main()
