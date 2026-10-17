import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domain.parsing import parse_run_id
from app.infrastructure.store import StoreUnavailable

PIPELINE = "callrail"

# The nine CallRail steps as a flow description: (name, label, group, inputs, returns_nothing)
CALLRAIL_STEPS: List[Tuple[str, str, str, List[Tuple[str, str]], bool]] = [
    ("read_callrail_account", "Accounts", "callrail", [], False),
    ("read_callrail_call", "Calls", "callrail", [("accounts", "read_callrail_account")], False),
    ("read_partners", "Partners", "gads", [], False),
    ("read_instances", "Instances", "gads", [("partners", "read_partners")], False),
    ("read_campaigns", "Campaigns", "gads", [("instances", "read_instances")], False),
    ("read_gads_clickview", "Click views", "gads", [("instances", "read_instances")], False),
    (
        "merge_calls_clickview",
        "Merged calls",
        "merge",
        [
            ("calls", "read_callrail_call"),
            ("campaigns", "read_campaigns"),
            ("clickview", "read_gads_clickview"),
        ],
        False,
    ),
    (
        "record_call_statistics",
        "Record stats",
        "persist",
        [("call_statistics", "merge_calls_clickview")],
        True,
    ),
    (
        "save_call_statistics",
        "Save stats",
        "persist",
        [("call_statistics", "merge_calls_clickview")],
        True,
    ),
]
STEP_NAMES = [s[0] for s in CALLRAIL_STEPS]
_INDEX = {name: i for i, name in enumerate(STEP_NAMES)}

# Sample outputs by step index; None = the step returns nothing.
SAMPLE_OUTPUT: List[Optional[int]] = [10, 1284, 6, 14, 92, 3410, 1284, None, None]

Raw = List[Tuple[str, str]]


def _prefix(pipeline: str, env: str) -> str:
    return f"waypoint:{pipeline}:{env}:"


class FakeStore:
    """Holds raw `(key, json)` pairs in the new layout; start markers are kept in `.markers`."""

    def __init__(self, records: Optional[Raw] = None) -> None:
        self.records: Raw = records or []
        self.markers: Raw = []
        self.alive: Raw = []
        self.died: Raw = []
        self.failures: Raw = []
        self.metrics: Raw = []
        self.maps: Raw = []
        self.items: Raw = []
        self.items_calls: List[Tuple[str, str, str, str]] = []  # list_items and read_item
        # run id -> level -> raw JSON elements, oldest first (the three event lists of a run)
        self.events: Dict[str, Dict[str, List[str]]] = {}
        self.events_denied = False  # the account may not read the event lists (NOPERM)
        self.read_events_calls = 0
        self.fail = False
        self.fail_write = False
        self.calls = 0
        self.write_calls: List[Tuple[str, str, str]] = []

    def _check(self) -> None:
        if self.fail:
            raise StoreUnavailable("down")

    def _all(self) -> Raw:
        return (
            self.records
            + self.markers
            + self.alive
            + self.died
            + self.failures
            + self.metrics
            + self.maps
            + self.items
        )

    def list_pipelines(self, env: str) -> List[str]:
        self._check()
        names = set()
        for key, _ in self._all():
            parts = key.split(":")
            if len(parts) > 3 and parts[0] == "waypoint" and parts[2] == env:
                names.add(parts[1])
        return sorted(names)

    def list_flows(self, env: str, pipeline: str) -> Raw:
        self.calls += 1
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.records if k.startswith(prefix) and k.endswith(":flow")]

    def list_records(self, env: str, pipeline: str) -> Raw:
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.records if k.startswith(prefix) and ":step:" in k]

    def list_markers(self, env: str, pipeline: str) -> Raw:
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.markers if k.startswith(prefix)]

    def list_alive(self, env: str, pipeline: str) -> Raw:
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.alive if k.startswith(prefix)]

    def list_died(self, env: str, pipeline: str) -> Raw:
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.died if k.startswith(prefix)]

    def list_failures(self, env: str, pipeline: str) -> Raw:
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.failures if k.startswith(prefix)]

    def list_metrics(self, env: str, pipeline: str) -> Raw:
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.metrics if k.startswith(prefix)]

    def list_maps(self, env: str, pipeline: str) -> Raw:
        self._check()
        prefix = _prefix(pipeline, env)
        return [(k, v) for k, v in self.maps if k.startswith(prefix)]

    def list_items(self, env: str, pipeline: str, run_id: str, map_name: str) -> Raw:
        self.items_calls.append((env, pipeline, run_id, map_name))
        self._check()
        prefix = f"{_prefix(pipeline, env)}{run_id}:item:{map_name}:"
        return [(k, v) for k, v in self.items if k.startswith(prefix)]

    def read_item(
        self, env: str, pipeline: str, run_id: str, map_name: str, key: str
    ) -> Optional[str]:
        self.items_calls.append((env, pipeline, run_id, map_name))
        self._check()
        wanted = f"{_prefix(pipeline, env)}{run_id}:item:{map_name}:{key}"
        return next((v for k, v in self.items if k == wanted), None)

    def list_event_counts(self, env: str, pipeline: str) -> Dict[str, Dict[str, int]]:
        self._check()
        if self.events_denied:
            return {}
        return {
            run_id: {
                "warning": len(levels.get("warning", [])),
                "error": len(levels.get("error", [])),
            }
            for run_id, levels in self.events.items()
        }

    def read_events(self, env: str, pipeline: str, run_id: str) -> List[Tuple[str, List[str]]]:
        self.read_events_calls += 1
        self._check()
        if self.events_denied:
            return []
        levels = self.events.get(run_id, {})
        return [
            (f"{_prefix(pipeline, env)}{run_id}:events:{level}", list(levels[level]))
            for level in ("info", "warning", "error")
            if levels.get(level)
        ]

    def add_event(
        self,
        run_id: str,
        level: str,
        n: int,
        ts: str,
        message: Optional[str] = "hello",
        step: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
        raw: Optional[str] = None,
        item: Optional[str] = None,
    ) -> None:
        """Append an author-sent event to the run's list of `level` (`raw` replaces the JSON)."""
        event: Dict[str, Any] = {"v": 1, "n": n, "ts": ts, "level": level}
        if message is not None:
            event["message"] = message
        if step is not None:
            event["step"] = step
        if fields is not None:
            event["fields"] = fields
        if item is not None:
            event["item"] = item
        self.events.setdefault(run_id, {}).setdefault(level, []).append(
            raw if raw is not None else json.dumps(event)
        )

    def record_died(self, key: str, value: str, alive_key: str) -> bool:
        self.write_calls.append((key, value, alive_key))
        if self.fail_write or any(k == key for k, _ in self.died):
            return False
        self.died.append((key, value))
        return True

    def ping(self) -> None:
        self._check()


def split(raw: Raw) -> Tuple[Raw, Raw, Raw]:
    """(flows, records, markers) of a raw list, for tests that call the parsers directly."""
    return (
        [p for p in raw if p[0].endswith(":flow")],
        [p for p in raw if ":step:" in p[0]],
        [p for p in raw if ":running:" in p[0]],
    )


def flow_value(
    pipeline: str,
    env: str,
    run_id: str,
    steps: Sequence[Dict[str, Any]],
    groups: Optional[List[Dict[str, str]]] = None,
    label: Optional[str] = None,
    v: int = 1,
) -> str:
    value: Dict[str, Any] = {
        "v": v,
        "pipeline": pipeline,
        "env": env,
        "run_id": run_id,
        "steps": list(steps),
    }
    if groups is not None:
        value["groups"] = groups
    if label is not None:
        value["label"] = label
    return json.dumps(value)


def callrail_flow_steps() -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for name, label, group, inputs, nothing in CALLRAIL_STEPS:
        step: Dict[str, Any] = {
            "name": name,
            "label": label,
            "group": group,
            "inputs": [{"name": n, "from": src} for n, src in inputs],
        }
        if nothing:
            step["returns_nothing"] = True
        steps.append(step)
    return steps


def make_flow(env: str, run_id: str, pipeline: str = PIPELINE) -> Tuple[str, str]:
    groups = [
        {"key": "callrail", "label": "CallRail"},
        {"key": "gads", "label": "Google Ads"},
        {"key": "merge", "label": "Merge"},
        {"key": "persist", "label": "Persist"},
    ]
    value = flow_value(pipeline, env, run_id, callrail_flow_steps(), groups, "CallRail")
    return f"{_prefix(pipeline, env)}{run_id}:flow", value


def make_run(
    env: str,
    run_id: str,
    missing_from: Optional[int] = None,
    overrides: Optional[Dict[int, int]] = None,
    corrupt: Sequence[int] = (),
    pipeline: str = PIPELINE,
    with_flow: bool = True,
    step_seconds: Optional[Sequence[float]] = None,
    exact: bool = True,
) -> Raw:
    """The flow plus the step records of one CallRail run. `missing_from` drops steps from that index.

    `step_seconds` gives each step's duration (the steps run back to back from the run's start); with
    `exact` the records carry `started_at` and `duration_ms` like library 0.4.0, without it they look
    like records of library 0.2.0/0.3.0.
    """
    outputs = list(SAMPLE_OUTPUT)
    for i, v in (overrides or {}).items():
        outputs[i] = v
    start = parse_run_id(run_id)
    out: Raw = [make_flow(env, run_id, pipeline)] if with_flow else []
    for i, (name, _label, _group, inputs, _nothing) in enumerate(CALLRAIL_STEPS):
        if missing_from is not None and i >= missing_from:
            continue
        counts = {n: int(outputs[_INDEX[src]] or 0) for n, src in inputs}
        if step_seconds is not None:
            began = start + timedelta(seconds=sum(step_seconds[:i]))
            finished = began + timedelta(seconds=step_seconds[i])
        else:
            began = None
            finished = (start + timedelta(seconds=(i + 1) * 8)).astimezone(timezone.utc)
        record: Dict[str, Any] = {
            "pipeline": pipeline,
            "run_id": run_id,
            "env": env,
            "step": name,
            "index": i + 1,
            "inputs": counts,
            "output": outputs[i],
            "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if began is not None and exact:
            record["started_at"] = began.strftime("%Y-%m-%dT%H:%M:%SZ")
            record["duration_ms"] = round(step_seconds[i] * 1000)  # type: ignore[index]
        value = "{not json" if i in corrupt else json.dumps(record)
        out.append((f"{_prefix(pipeline, env)}{run_id}:step:{i + 1:02d}-{name}", value))
    return out


def make_marker(
    env: str,
    run_id: str,
    step_index: int,
    started_at: datetime,
    pipeline: str = PIPELINE,
    step: Optional[str] = None,
) -> Tuple[str, str]:
    """One start-marker pair for the 0-based `step_index` of the run (or a named `step`)."""
    name = step or STEP_NAMES[step_index]
    record = {
        "pipeline": pipeline,
        "run_id": run_id,
        "env": env,
        "step": name,
        "index": step_index + 1,
        "started_at": started_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return f"{_prefix(pipeline, env)}{run_id}:running:{step_index + 1:02d}-{name}", json.dumps(
        record
    )


def run_id_at(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_alive(
    env: str, run_id: str, beat_at: datetime, pipeline: str = PIPELINE
) -> Tuple[str, str]:
    """One heartbeat item: the run's process was alive at `beat_at`."""
    value = {
        "v": 1,
        "pipeline": pipeline,
        "env": env,
        "run_id": run_id,
        "beat_at": _stamp(beat_at),
    }
    return f"{_prefix(pipeline, env)}{run_id}:alive", json.dumps(value)


def make_died(
    env: str, run_id: str, judged_at: datetime, last_seen_at: datetime, pipeline: str = PIPELINE
) -> Tuple[str, str]:
    """One stored died verdict."""
    value = {
        "v": 1,
        "pipeline": pipeline,
        "env": env,
        "run_id": run_id,
        "judged_at": _stamp(judged_at),
        "last_seen_at": _stamp(last_seen_at),
    }
    return f"{_prefix(pipeline, env)}{run_id}:died", json.dumps(value)


def make_failure(
    env: str,
    run_id: str,
    step_index: int,
    failed_at: datetime,
    pipeline: str = PIPELINE,
    step: Optional[str] = None,
    index: Optional[int] = None,
    started_at: Optional[datetime] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """One failure item for the 0-based `step_index` of the run (or a named `step`).

    `index` is the attempt index (default `step_index + 1`); use a higher one for a retry.
    """
    name = step or STEP_NAMES[step_index]
    attempt = index if index is not None else step_index + 1
    value = {
        "v": 1,
        "pipeline": pipeline,
        "env": env,
        "run_id": run_id,
        "step": name,
        "index": attempt,
        "started_at": _stamp(started_at or failed_at - timedelta(seconds=5)),
        "failed_at": _stamp(failed_at),
        "error": error
        or {
            "type": "ValueError",
            "message": "boom",
            "traceback": '  File "x.py", line 3, in run\n    raise ValueError("boom")\nValueError: boom\n',
        },
    }
    return f"{_prefix(pipeline, env)}{run_id}:failed:{attempt:02d}-{name}", json.dumps(value)


def make_metrics(
    env: str,
    run_id: str,
    step_index: int,
    values: Dict[str, Any],
    pipeline: str = PIPELINE,
    step: Optional[str] = None,
    index: Optional[int] = None,
    updated_at: Optional[datetime] = None,
) -> Tuple[str, str]:
    """One metrics record for the 0-based `step_index` of the run (or a named `step`).

    `index` is the attempt index (default `step_index + 1`); use a higher one for a retry.
    """
    name = step or STEP_NAMES[step_index]
    attempt = index if index is not None else step_index + 1
    value: Dict[str, Any] = {
        "v": 1,
        "pipeline": pipeline,
        "env": env,
        "run_id": run_id,
        "step": name,
        "index": attempt,
        "metrics": values,
    }
    if updated_at is not None:
        value["updated_at"] = _stamp(updated_at)
    return f"{_prefix(pipeline, env)}{run_id}:metrics:{attempt:02d}-{name}", json.dumps(value)


def declare_metrics(
    raw: List[Tuple[str, str]], step: str, declarations: List[Dict[str, Any]]
) -> List[Tuple[str, str]]:
    """The raw run with `declarations` added to `step` in its flow record."""
    out: List[Tuple[str, str]] = []
    for key, value in raw:
        if key.endswith(":flow"):
            flow = json.loads(value)
            for entry in flow["steps"]:
                if entry["name"] == step:
                    entry["metrics"] = declarations
            value = json.dumps(flow)
        out.append((key, value))
    return out


def bucket_of(ms: int) -> int:
    """The duration histogram bucket of the library: `floor(ln(ms) / ln(1.1))`, 0 below 1 ms."""
    return int(math.floor(math.log(ms) / math.log(1.1))) if ms >= 1 else 0


def make_aggregate(
    env: str,
    run_id: str,
    *,
    map_name: str = "accounts",
    index: int = 2,
    running: int = 0,
    done: int = 0,
    failed: int = 0,
    ended: bool = True,
    started_at: Optional[datetime] = None,
    pipeline: str = PIPELINE,
    durations_ms: Sequence[int] = (),
    slowest: Sequence[Tuple[str, int]] = (),
    inner: Optional[Dict[str, Dict[str, int]]] = None,
    failed_items: Sequence[Tuple[str, str, str]] = (),
    kept: Optional[int] = None,
    failed_without_record: int = 0,
    slow_kept: int = 0,
    lost_items: int = 0,
    in_total: int = 0,
    out_total: int = 0,
    raw: Optional[str] = None,
    **overrides: Any,
) -> Tuple[str, str]:
    """One map aggregate pair (contracts/redis-keys.md). `durations_ms` fills the histogram, count and sum."""
    start = started_at or parse_run_id(run_id) + timedelta(seconds=10)
    hist: Dict[str, int] = {}
    for ms in durations_ms:
        hist[str(bucket_of(ms))] = hist.get(str(bucket_of(ms)), 0) + 1
    started = running + done + failed
    value: Dict[str, Any] = {
        "v": 1,
        "pipeline": pipeline,
        "env": env,
        "run_id": run_id,
        "map": map_name,
        "index": index,
        "started_at": _stamp(start),
        "ended_at": _stamp(start + timedelta(seconds=41)) if ended else None,
        "updated_at": _stamp(start + timedelta(seconds=42)),
        "counts": {"started": started, "running": running, "done": done, "failed": failed},
        "in_total": in_total,
        "out_total": out_total,
        "lost_items": lost_items,
        "inner": inner or {},
        "duration": {
            "count": len(durations_ms),
            "sum_ms": sum(durations_ms),
            "hist": hist,
            "slowest": [{"key": k, "ms": ms} for k, ms in slowest],
        },
        "failed_items": [{"key": k, "step": st, "error_type": et} for k, st, et in failed_items],
        "detail": {
            "limit": 1000,
            "kept": started if kept is None else kept,
            "extra_failed_limit": 1000,
            "failed_without_record": failed_without_record,
            "slow_kept": slow_kept,
        },
    }
    value.update(overrides)
    return f"{_prefix(pipeline, env)}{run_id}:map:{map_name}", (
        raw if raw is not None else json.dumps(value)
    )


def item_steps(
    *, failed_at: Optional[str] = None, loss_at: Optional[str] = None, running: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Inner step results of fetch -> transform -> load for one item. A failed step stops the item;
    `running` is the step still open (later steps have not begun)."""
    results: List[Dict[str, Any]] = []
    rows = 48
    for name in ("fetch", "transform", "load"):
        result: Dict[str, Any] = {
            "step": name,
            "attempt": 1,
            "inputs": {"account": 1} if name == "fetch" else {"rows": rows},
            "started_at": "2026-10-15T02:04:21Z",
        }
        if name == running:
            result["state"] = "running"
            result["output"] = None
            results.append(result)
            break
        if name == failed_at:
            result.update(
                state="failed",
                output=None,
                duration_ms=6820,
                error={
                    "type": "ValueError",
                    "message": "bad date",
                    "traceback": '  File "t.py", line 3, in transform\n    raise ValueError("bad date")\n',
                },
            )
            results.append(result)
            break
        out = 0 if name == loss_at else rows
        result.update(state="done", output=out, duration_ms=2300)
        results.append(result)
        rows = out
    return results


def make_item(
    env: str,
    run_id: str,
    key: str,
    index: int,
    state: str = "done",
    *,
    map_name: str = "accounts",
    pipeline: str = PIPELINE,
    steps: Optional[List[Dict[str, Any]]] = None,
    duration_ms: Optional[int] = 3900,
    started_at: Optional[datetime] = None,
    compact: bool = False,
    metrics: Optional[Dict[str, Dict[str, Any]]] = None,
    error: Optional[Dict[str, Any]] = None,
    raw: Optional[str] = None,
    **overrides: Any,
) -> Tuple[str, str]:
    """One item record pair (contracts/redis-keys.md). A running item has no duration or end time."""
    start = started_at or parse_run_id(run_id) + timedelta(seconds=10 + index)
    if steps is None:
        steps = item_steps(failed_at="transform" if state == "failed" else None)
    value: Dict[str, Any] = {
        "v": 1,
        "pipeline": pipeline,
        "env": env,
        "run_id": run_id,
        "map": map_name,
        "key": key,
        "index": index,
        "state": state,
        "started_at": _stamp(start),
        "steps": steps,
    }
    if state != "running":
        value["finished_at"] = _stamp(start + timedelta(milliseconds=duration_ms or 0))
        value["duration_ms"] = duration_ms
    if metrics:
        value["metrics"] = metrics
    if error:
        value["error"] = error
    if compact:
        value["compact"] = True
    value.update(overrides)
    return (
        f"{_prefix(pipeline, env)}{run_id}:item:{map_name}:{key}",
        raw if raw is not None else json.dumps(value),
    )


def map_flow_steps(
    over: Optional[str] = "list_accounts",
    max_concurrency: Optional[int] = 5,
    metrics: bool = True,
) -> List[Dict[str, Any]]:
    """Flow steps `list_accounts` -> map `accounts` (fetch -> transform -> load) -> `publish`."""
    decl: Dict[str, Any] = {
        "name": "accounts",
        "label": "Accounts",
        "kind": "map",
        "inputs": [{"name": "accounts", "from": "list_accounts"}],
        "steps": [
            {"name": "fetch", "inputs": []},
            {
                "name": "transform",
                "inputs": [{"name": "rows", "from": "fetch"}],
                **(
                    {"metrics": [{"name": "rejected", "unit": "rows", "warn_above": 100}]}
                    if metrics
                    else {}
                ),
            },
            {"name": "load", "inputs": [{"name": "rows", "from": "transform"}]},
        ],
    }
    if over is not None:
        decl["over"] = over
    if max_concurrency is not None:
        decl["max_concurrency"] = max_concurrency
    return [
        {"name": "list_accounts", "inputs": []},
        decl,
        {"name": "publish", "inputs": [{"name": "done", "from": "accounts"}]},
    ]


def make_map_run(
    env: str,
    run_id: str,
    *,
    pipeline: str = PIPELINE,
    steps_done: int = 3,
    seconds: float = 8.0,
    map_decl: Optional[List[Dict[str, Any]]] = None,
) -> Raw:
    """The flow plus the step records of `list_accounts`, `accounts` and `publish` (the first
    `steps_done` of them), for a pipeline with a map step."""
    start = parse_run_id(run_id)
    flow = flow_value(pipeline, env, run_id, map_decl or map_flow_steps(), None, "Map demo")
    out: Raw = [(f"{_prefix(pipeline, env)}{run_id}:flow", flow)]
    names = ("list_accounts", "accounts", "publish")
    outputs: List[Optional[int]] = [10, 10, None]
    inputs: List[Dict[str, int]] = [{}, {"accounts": 10}, {"done": 10}]
    for i, name in enumerate(names[:steps_done]):
        began = start + timedelta(seconds=i * seconds)
        out.append(
            (
                f"{_prefix(pipeline, env)}{run_id}:step:{i + 1:02d}-{name}",
                json.dumps(
                    {
                        "pipeline": pipeline,
                        "run_id": run_id,
                        "env": env,
                        "step": name,
                        "index": i + 1,
                        "inputs": inputs[i],
                        "output": outputs[i],
                        "finished_at": _stamp(began + timedelta(seconds=seconds)),
                        "started_at": _stamp(began),
                        "duration_ms": round(seconds * 1000),
                    }
                ),
            )
        )
    return out
