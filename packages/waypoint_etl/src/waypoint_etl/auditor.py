"""Writes the flow description once per run and a start marker plus a record for every step.

Only names and counts are recorded: pipeline items may carry personal data, so item contents must
never be serialised here. A storage failure is logged and swallowed - the audit is diagnostic and
must not change what the pipeline does.
"""

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, TypeVar

from waypoint_etl.heartbeat import Heartbeat
from waypoint_etl.keys import (
    FLOW_VERSION,
    START_MARKER_TTL_SECONDS,
    alive_key,
    flow_key,
    marker_key,
    step_key,
)
from waypoint_etl.spec import PipelineSpec, validate_spec
from waypoint_etl.stores import StepAuditStore

T = TypeVar("T")


def count_items(value: object) -> Optional[int]:
    """None -> None, list/tuple/set -> its length, any other object -> 1."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value)
    return 1


def _utc_stamp(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ")


def _flow_value(spec: PipelineSpec, env: str, run_id: str) -> Dict[str, object]:
    steps: List[Dict[str, object]] = []
    for s in spec.steps:
        entry: Dict[str, object] = {
            "name": s.name,
            "inputs": [{"name": n, "from": src} for n, src in s.inputs],
        }
        for field, optional in (
            ("label", s.label),
            ("group", s.group),
            ("col", s.col),
            ("row", s.row),
        ):
            if optional is not None:
                entry[field] = optional
        if s.returns_nothing:
            entry["returns_nothing"] = True
        steps.append(entry)
    value: Dict[str, object] = {
        "v": FLOW_VERSION,
        "pipeline": spec.name,
        "env": env,
        "run_id": run_id,
        "steps": steps,
    }
    if spec.label is not None:
        value["label"] = spec.label
    if spec.groups:
        value["groups"] = [{"key": g.key, "label": g.label} for g in spec.groups]
    return value


class StepAuditor:
    def __init__(
        self,
        store: StepAuditStore,
        spec: PipelineSpec,
        env: str,
        ttl_seconds: int,
        run_id: Optional[str] = None,
    ) -> None:
        self.store = store
        self.spec = spec
        self.env = env
        self.ttl_seconds = ttl_seconds
        self.run_id = run_id or _utc_stamp(datetime.now(timezone.utc))
        self._index = 0
        self._heartbeat: Optional[Heartbeat] = None
        self._started = False
        self._spec_ok = True
        try:
            validate_spec(spec)
        except ValueError as exc:
            self._spec_ok = False
            print(f"Warning: pipeline spec invalid, flow not recorded: {exc}")

    def start(self) -> None:
        """Store the flow description once per run, before any step. Never raises."""
        if self._started:
            return
        self._started = True
        if not self._spec_ok:
            return
        try:
            self.store.write(
                flow_key(self.spec.name, self.env, self.run_id),
                _flow_value(self.spec, self.env, self.run_id),
                self.ttl_seconds,
            )
        except Exception as exc:
            print(f"Warning: Waypoint flow write failed: {exc}")

    def start_heartbeat(self, interval_seconds: Optional[float]) -> None:
        """Start refreshing this run's alive item every ``interval_seconds``; None or <= 0 means off.

        The monitor reads the item to tell a run whose process is gone from one that is only slow.
        """
        if self._heartbeat is not None or not interval_seconds or interval_seconds <= 0:
            return
        self._heartbeat = Heartbeat(self._beat, interval_seconds)
        self._heartbeat.start()

    def stop(self) -> None:
        """Stop the heartbeat. Safe to call more than once."""
        if self._heartbeat is not None:
            self._heartbeat.stop()

    def _beat(self) -> None:
        pipeline = self.spec.name
        record: Dict[str, object] = {
            "v": FLOW_VERSION,
            "pipeline": pipeline,
            "env": self.env,
            "run_id": self.run_id,
            "beat_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.store.write(alive_key(pipeline, self.env, self.run_id), record, self.ttl_seconds)

    def begin(self, name: str) -> int:
        """Write the start marker for step ``name`` and return its 1-based index. Never raises."""
        self.start()
        self._index += 1
        index = self._index
        pipeline = self.spec.name
        if self._spec_ok and name not in {s.name for s in self.spec.steps}:
            print(f"Warning: step {name} is not in pipeline spec {pipeline}")
        try:
            started = {
                "pipeline": pipeline,
                "run_id": self.run_id,
                "env": self.env,
                "step": name,
                "index": index,
                "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            self.store.write(
                marker_key(pipeline, self.env, self.run_id, index, name),
                started,
                START_MARKER_TTL_SECONDS,
            )
        except Exception as exc:
            print(f"Warning: Waypoint start marker failed for {name}: {exc}")
        return index

    def finish(self, name: str, index: int, inputs: Dict[str, object], result: object) -> None:
        """Write the finish record for a step that returned. Never raises."""
        pipeline = self.spec.name
        try:
            now = datetime.now(timezone.utc)
            record: Dict[str, object] = {
                "pipeline": pipeline,
                "run_id": self.run_id,
                "env": self.env,
                "step": name,
                "index": index,
                "inputs": {k: count_items(v) for k, v in inputs.items()},
                "output": count_items(result),
                "finished_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            self.store.write(
                step_key(pipeline, self.env, self.run_id, index, name), record, self.ttl_seconds
            )
        except Exception as exc:
            print(f"Warning: Waypoint record failed for {name}: {exc}")

    def run(
        self,
        name: str,
        fn: Callable[..., T],
        *args: object,
        inputs: Optional[Dict[str, object]] = None,
    ) -> T:
        """Call ``fn(*args)`` and record input/output counts.

        ``inputs`` only feeds the record's input counts; it is not passed to fn.
        If fn raises, the exception propagates and no finish record is written. A step that is not
        in the spec is still recorded (the monitor shows it as unplanned) after a warning.
        """
        index = self.begin(name)
        result = fn(*args)
        self.finish(name, index, inputs or {}, result)
        return result
