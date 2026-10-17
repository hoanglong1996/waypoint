"""Writes the flow description once per run and a start marker plus a record for every step.

Only names and counts are recorded: pipeline items may carry personal data, so item contents must
never be serialised here. A storage failure is logged and swallowed - the audit is diagnostic and
must not change what the pipeline does.
"""

import itertools
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Mapping, Optional, Set, TypeVar, Union

from waypoint_etl.errors import build_error
from waypoint_etl.events import EventWriter, build_event, current_step
from waypoint_etl.heartbeat import Heartbeat
from waypoint_etl.keys import (
    FLOW_VERSION,
    START_MARKER_TTL_SECONDS,
    alive_key,
    failed_key,
    flow_key,
    marker_key,
    step_key,
)
from waypoint_etl.metrics import MetricState, MetricWriter
from waypoint_etl.spec import Metric, PipelineSpec, validate_spec
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


def _stamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _metric_value(metric: Metric) -> Dict[str, object]:
    value: Dict[str, object] = {"name": metric.name}
    for field, optional in (
        ("label", metric.label),
        ("unit", metric.unit),
        ("warn_above", metric.warn_above),
        ("warn_below", metric.warn_below),
    ):
        if optional is not None:
            value[field] = optional
    return value


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
        if s.metrics:
            entry["metrics"] = [_metric_value(m) for m in s.metrics]
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
        capture_error_message: bool = True,
        redact: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.store = store
        self.spec = spec
        self.env = env
        self.ttl_seconds = ttl_seconds
        self.run_id = run_id or _utc_stamp(datetime.now(timezone.utc))
        self.capture_error_message = capture_error_message
        self.redact = redact
        self._index = 0
        self._begun: Dict[int, str] = {}
        self._begun_mono: Dict[int, float] = {}
        self._open: Dict[int, str] = {}
        self._event_numbers = itertools.count(1)
        self._event_lock = threading.Lock()
        self._events: Optional[EventWriter] = None
        self._events_warned = False
        self._latest_index: Dict[str, int] = {}
        self._metric_state = MetricState()
        self._metric_writer: Optional[MetricWriter] = None
        self._metric_warned: Set[str] = set()
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
        """Stop the heartbeat and deliver queued events. Safe to call more than once."""
        if self._heartbeat is not None:
            self._heartbeat.stop()
        started = time.monotonic()
        if self._events is not None:
            self._events.stop()
        if self._metric_writer is not None:
            self._metric_writer.stop(max(0.0, 2.0 - (time.monotonic() - started)))

    def flush_events(self, timeout: float = 2.0) -> None:
        """Write what is queued (events and metrics), waiting at most ``timeout`` seconds in all.

        Never raises.
        """
        started = time.monotonic()
        try:
            if self._events is not None:
                self._events.flush(timeout)
        except Exception:
            pass
        try:
            if self._metric_writer is not None:
                self._metric_writer.flush(max(0.0, timeout - (time.monotonic() - started)))
        except Exception:
            return

    def record_metric(
        self,
        name: str,
        value: Union[int, float],
        step: Optional[str] = None,
        mode: str = "set",
    ) -> None:
        """Merge one metric call into the step attempt it belongs to. Never raises, never blocks."""
        try:
            named = step or current_step.get() or self.current_open_step()
            if named is None:
                return
            index = self._latest_index.get(named)
            if index is None:
                self._warn_metric(f"step:{named}", f"step {named!r} has not started in this run")
                return
            reason = self._metric_state.apply((index, named), name, value, mode)
            if reason is not None:
                self._warn_metric(f"{reason}:{name}", f"metric {name!r} dropped ({reason})")
                return
            if self._metric_writer is None:
                self._metric_writer = MetricWriter(
                    self.store,
                    self._metric_state,
                    self.spec.name,
                    self.env,
                    self.run_id,
                    self.ttl_seconds,
                )
            self._metric_writer.notify()
        except Exception:
            return

    def _warn_metric(self, key: str, text: str) -> None:
        """One warning per distinct problem (bounded to 100 kept)."""
        if key in self._metric_warned or len(self._metric_warned) >= 100:
            return
        self._metric_warned.add(key)
        print(f"Warning: Waypoint metric: {text}")

    def current_open_step(self) -> Optional[str]:
        """The one step that has begun and not ended, else None (steps are sequential)."""
        names = list(self._open.values())
        return names[0] if len(names) == 1 else None

    def send_event(
        self,
        message: str,
        level: str = "info",
        step: Optional[str] = None,
        fields: Optional[Mapping[str, object]] = None,
    ) -> None:
        """Queue an author-sent event for the writer thread. Never raises, never blocks."""
        try:
            writer = self._event_writer()
            if writer is None:
                return
            named = step or current_step.get() or self.current_open_step()
            with self._event_lock:
                n = next(self._event_numbers)
            writer.submit(
                build_event(
                    message,
                    n=n,
                    level=level,
                    step=named,
                    fields=fields,
                    capture_message=self.capture_error_message,
                    redact=self.redact,
                )
            )
        except Exception:
            return

    def _event_writer(self) -> Optional[EventWriter]:
        if self._events is None:
            push = getattr(self.store, "push_events", None)
            if push is None:
                if not self._events_warned:
                    self._events_warned = True
                    print("Warning: Waypoint store cannot take events (no push_events); skipped")
                return None
            self._events = EventWriter(
                push, self.spec.name, self.env, self.run_id, self.ttl_seconds
            )
        return self._events

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
        started_at = _stamp(datetime.now(timezone.utc))
        self._begun[index] = started_at
        self._begun_mono[index] = time.monotonic()
        self._open[index] = name
        self._latest_index[name] = index
        if self._spec_ok and name not in {s.name for s in self.spec.steps}:
            print(f"Warning: step {name} is not in pipeline spec {pipeline}")
        try:
            started = {
                "pipeline": pipeline,
                "run_id": self.run_id,
                "env": self.env,
                "step": name,
                "index": index,
                "started_at": started_at,
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
        """Write the finish record (with the step's start time and duration) for a step that returned.

        Never raises. Contract: specs/012-duration-and-run-events/contracts/redis-keys.md
        """
        pipeline = self.spec.name
        began = self._begun.pop(index, None)
        began_mono = self._begun_mono.pop(index, None)
        self._open.pop(index, None)
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
            if began is not None:
                record["started_at"] = began
            if began_mono is not None:
                record["duration_ms"] = max(0, round((time.monotonic() - began_mono) * 1000))
            self.store.write(
                step_key(pipeline, self.env, self.run_id, index, name), record, self.ttl_seconds
            )
        except Exception as exc:
            print(f"Warning: Waypoint record failed for {name}: {exc}")

    def fail(self, name: str, index: int, exc: BaseException) -> None:
        """Write the failure item for attempt ``index`` of step ``name``. Never raises.

        The start marker is left in place: the monitor lets a failure with the highest attempt index
        win over it. Contract: specs/011-step-failure-errors/contracts/redis-keys.md
        """
        pipeline = self.spec.name
        started_at = self._begun.pop(index, None)
        self._begun_mono.pop(index, None)
        self._open.pop(index, None)
        try:
            now = _stamp(datetime.now(timezone.utc))
            record: Dict[str, object] = {
                "v": FLOW_VERSION,
                "pipeline": pipeline,
                "env": self.env,
                "run_id": self.run_id,
                "step": name,
                "index": index,
                "started_at": started_at or now,
                "failed_at": now,
                "error": build_error(
                    exc, capture_message=self.capture_error_message, redact=self.redact
                ),
            }
            self.store.write(
                failed_key(pipeline, self.env, self.run_id, index, name), record, self.ttl_seconds
            )
        except Exception as exc_write:
            print(f"Warning: Waypoint failure record failed for {name}: {exc_write}")

    def run(
        self,
        name: str,
        fn: Callable[..., T],
        *args: object,
        inputs: Optional[Dict[str, object]] = None,
    ) -> T:
        """Call ``fn(*args)`` and record input/output counts.

        ``inputs`` only feeds the record's input counts; it is not passed to fn.
        If fn raises an ``Exception``, a failure item is written and the exception propagates
        unchanged; no finish record is written. A step that is not in the spec is still recorded
        (the monitor shows it as unplanned) after a warning.
        """
        index = self.begin(name)
        token = current_step.set(name)
        try:
            result = fn(*args)
        except Exception as exc:
            self.fail(name, index, exc)
            raise
        finally:
            current_step.reset(token)
        self.finish(name, index, inputs or {}, result)
        return result
