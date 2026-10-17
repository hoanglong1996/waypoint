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
from waypoint_etl.maps import ItemHandle, ItemState, MapBlock, MapTracker, MapWriter, current_item
from waypoint_etl.metrics import MetricState, MetricWriter
from waypoint_etl.spec import MapStepSpec, Metric, PipelineSpec, StepSpec, validate_spec
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


def _step_entry(s: StepSpec) -> Dict[str, object]:
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
    return entry


def _map_entry(m: MapStepSpec) -> Dict[str, object]:
    entry: Dict[str, object] = {
        "name": m.name,
        "kind": "map",
        "inputs": [{"name": n, "from": src} for n, src in m.inputs],
    }
    for field, optional in (
        ("over", m.over),
        ("max_concurrency", m.max_concurrency),
        ("label", m.label),
        ("group", m.group),
        ("col", m.col),
        ("row", m.row),
    ):
        if optional is not None:
            entry[field] = optional
    entry["steps"] = [_step_entry(inner) for inner in m.steps]
    return entry


def _flow_value(spec: PipelineSpec, env: str, run_id: str) -> Dict[str, object]:
    steps: List[Dict[str, object]] = [
        _map_entry(s) if isinstance(s, MapStepSpec) else _step_entry(s) for s in spec.steps
    ]
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
        self._blocks: Dict[str, MapBlock] = {}
        self._block_lock = threading.Lock()
        self._outputs: Dict[str, Optional[int]] = {}
        self._map_warned: Set[str] = set()
        self._known_steps = {s.name for s in spec.steps} | {
            inner.name for s in spec.steps if isinstance(s, MapStepSpec) for inner in s.steps
        }
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
        for block in self._open_blocks():
            block.writer.stop(max(0.0, 2.0 - (time.monotonic() - started)))

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
            pass
        try:
            for block in self._open_blocks():
                block.writer.flush(max(0.0, timeout - (time.monotonic() - started)))
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
            handle = current_item.get()
            if handle is not None:
                self._record_item_metric(handle, name, value, step, mode)
                return
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

    def _record_item_metric(
        self,
        handle: ItemHandle,
        name: str,
        value: Union[int, float],
        step: Optional[str],
        mode: str,
    ) -> None:
        """Merge a metric call made inside an item into that item's inner step."""
        if handle.item is None:
            return
        named = step or current_step.get()
        if named is None or named == handle.block.name:
            self._warn_metric(
                "no-inner-step", "metric dropped: no inner step is running in this item"
            )
            return
        reason = handle.block.tracker.record_metric(handle.item, named, name, value, mode)
        if reason == "step":
            self._warn_metric(f"step:{named}", f"step {named!r} has not started in this item")
        elif reason is not None:
            self._warn_metric(f"{reason}:{name}", f"metric {name!r} dropped ({reason})")
        else:
            handle.block.writer.notify()

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
            handle = current_item.get()
            if handle is not None and handle.item is None:
                return  # a discarded (duplicate) pass records nothing
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
                    item=handle.item.key if handle is not None and handle.item else None,
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
        """Write the start marker for step ``name`` and return its 1-based index. Never raises.

        Inside an item (a map step) the inner step is recorded on the item instead and its
        per-item sequence number is returned.
        """
        handle = current_item.get()
        if handle is not None:
            return self._begin_inner(handle, name)
        return self._begin_run(name)

    def _begin_inner(self, handle: ItemHandle, name: str) -> int:
        if handle.item is None:
            return 0
        if name not in self._known_steps:
            self._warn_map(f"unplanned:{name}", f"inner step {name} is not in pipeline spec")
        seq = handle.block.tracker.begin_inner(handle.item, name)
        handle.block.writer.notify()
        return seq

    def _begin_run(self, name: str) -> int:
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
        Inside an item the inner step is closed on the item instead.
        """
        handle = current_item.get()
        if handle is not None:
            self._finish_inner(handle, name, index, inputs, result)
            return
        self._outputs[name] = count_items(result)
        self._finish_run(
            name, index, {k: count_items(v) for k, v in inputs.items()}, count_items(result)
        )

    def _finish_inner(
        self, handle: ItemHandle, name: str, seq: int, inputs: Dict[str, object], result: object
    ) -> None:
        if handle.item is None:
            return
        counts = {k: count_items(v) for k, v in inputs.items()}
        handle.block.tracker.finish_inner(handle.item, name, seq, counts, count_items(result))
        handle.block.writer.notify()

    def _finish_run(
        self, name: str, index: int, inputs: Dict[str, Optional[int]], output: Optional[int]
    ) -> None:
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
                "inputs": dict(inputs),
                "output": output,
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
        Inside an item the failure is recorded on the item instead.
        """
        handle = current_item.get()
        if handle is not None:
            if handle.item is not None:
                handle.block.tracker.fail_inner(handle.item, name, index, self._error_of(exc))
                handle.block.writer.notify()
            return
        self._fail_run(name, index, exc)

    def _error_of(self, exc: BaseException) -> Dict[str, str]:
        return build_error(exc, capture_message=self.capture_error_message, redact=self.redact)

    def _fail_run(self, name: str, index: int, exc: BaseException) -> None:
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

    # ---- map steps (specs/014) ---------------------------------------------------------------

    def step_spec(self, name: str) -> Optional[Union[StepSpec, MapStepSpec]]:
        """The declared step called ``name``, a top-level step first, then an inner step of a map step."""
        for s in self.spec.steps:
            if s.name == name:
                return s
            if isinstance(s, MapStepSpec):
                for inner in s.steps:
                    if inner.name == name:
                        return inner
        return None

    def _map_spec(self, name: str) -> Optional[MapStepSpec]:
        for s in self.spec.steps:
            if isinstance(s, MapStepSpec) and s.name == name:
                return s
        return None

    def _open_blocks(self) -> List[MapBlock]:
        with self._block_lock:
            return list(self._blocks.values())

    def _warn_map(self, key: str, text: str) -> None:
        """One warning per distinct map problem (bounded to 100 kept)."""
        if key in self._map_warned or len(self._map_warned) >= 100:
            return
        self._map_warned.add(key)
        print(f"Warning: Waypoint map step: {text}")

    def open_map(self, name: str) -> Optional[MapBlock]:
        """Start the map step block ``name``: the ordinary start marker, a tracker and a writer.

        None (and nothing recorded) when ``name`` is not a map step of the spec or is already open.
        Never raises.
        """
        try:
            spec = self._map_spec(name)
            if spec is None:
                self._warn_map(
                    f"map:{name}", f"{name!r} is not a map step of pipeline spec {self.spec.name}"
                )
                return None
            with self._block_lock:
                already = name in self._blocks
            if already:
                self._warn_map(f"open:{name}", f"map step {name!r} is already open")
                return None
            index = self._begin_run(name)
            tracker = MapTracker(
                self.spec.name,
                self.env,
                self.run_id,
                name,
                index,
                [inner.name for inner in spec.steps],
                self._warn_map,
            )
            block = MapBlock(name, index, tracker, MapWriter(self.store, tracker, self.ttl_seconds))
            with self._block_lock:
                self._blocks[name] = block
            block.writer.notify()
            return block
        except Exception:
            return None

    def close_map(self, block: MapBlock, exc: Optional[BaseException]) -> None:
        """End the block: deliver its records, then write the step's ordinary finish record, or its
        failure item when an ``Exception`` left the block. Never raises."""
        try:
            block.tracker.end_block()
            block.writer.stop(2.0)
        except Exception:
            pass
        with self._block_lock:
            self._blocks.pop(block.name, None)
        try:
            if exc is None:
                started = block.tracker.started
                self._outputs[block.name] = started
                self._finish_run(block.name, block.index, self._map_inputs(block.name), started)
            elif isinstance(exc, Exception):
                self._fail_run(block.name, block.index, exc)
        except Exception:
            return

    def _map_inputs(self, name: str) -> Dict[str, Optional[int]]:
        """Counts of what the map step was handed: its declared inputs, and ``over`` when given."""
        spec = self._map_spec(name)
        found: Dict[str, Optional[int]] = {}
        if spec is None:
            return found
        for input_name, source in spec.inputs:
            count = self._outputs.get(source)
            if count is not None:
                found[input_name] = count
        if spec.over is not None and spec.over not in {src for _, src in spec.inputs}:
            count = self._outputs.get(spec.over)
            if count is not None:
                found[spec.over] = count
        return found

    def resolve_block(
        self, explicit: Optional[str], contextual: Optional[str]
    ) -> Optional[MapBlock]:
        """The open map block an item belongs to: the named one, else the enclosing one of this
        context, else the run's one open block (a worker thread does not inherit the context)."""
        with self._block_lock:
            if explicit is not None:
                return self._blocks.get(explicit)
            if contextual is not None and contextual in self._blocks:
                return self._blocks[contextual]
            if len(self._blocks) == 1:
                return next(iter(self._blocks.values()))
        return None

    def start_item(self, block: MapBlock, raw_key: object) -> ItemHandle:
        """Open an item. A duplicate key gives a handle with no item: its recordings are dropped."""
        item: Optional[ItemState] = block.tracker.start_item(raw_key)
        block.writer.notify()
        return ItemHandle(block, item)

    def end_item(self, handle: ItemHandle, exc: Optional[BaseException]) -> None:
        """Close an item; an exception that left it marks it failed unless an inner step already failed."""
        if handle.item is None:
            return
        try:
            error = self._error_of(exc) if exc is not None else None
        except Exception:
            error = {"type": "Error", "traceback": ""}
        handle.block.tracker.end_item(handle.item, error)
        handle.block.writer.notify()

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
