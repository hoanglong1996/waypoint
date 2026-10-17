"""Step metrics: ``waypoint_etl.metric("rejected", 42, mode="add")``.

A metric is a named number on a step attempt. Calls are merged in memory (set, add or max, under one
lock) and a background thread writes each changed attempt's full record at most once a second, so a
tight loop costs a dictionary update and never a network call. Nothing here raises into the pipeline.
Contract: specs/013-step-metrics/contracts/library-api.md and redis-keys.md.
"""

import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from waypoint_etl.keys import (
    MAX_METRIC_NAME,
    MAX_METRICS_PER_STEP,
    METRIC_FLUSH_SECONDS,
    METRICS_VERSION,
    metrics_key,
)
from waypoint_etl.stores import StepAuditStore

MODES = ("set", "add", "max")
WARN_EVERY_SECONDS = 60.0

_NAME = re.compile(rf"^[a-z0-9_]{{1,{MAX_METRIC_NAME}}}$")

Number = Union[int, float]
Attempt = Tuple[int, str]  # (step attempt index, step name)


def valid_name(name: object) -> bool:
    return isinstance(name, str) and _NAME.match(name) is not None


def valid_value(value: object) -> bool:
    """An ``int`` or ``float`` that is finite; a ``bool`` is not a number here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not (isinstance(value, float) and not math.isfinite(value))


class MetricState:
    """The merged metrics of every step attempt of one run, safe to call from many threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: Dict[Attempt, Dict[str, Number]] = {}
        self._dirty: Set[Attempt] = set()

    def apply(self, attempt: Attempt, name: str, value: Number, mode: str) -> Optional[str]:
        """Merge one call. Returns None when applied, else the reason it was dropped:
        ``name``, ``value``, ``mode``, ``limit`` or ``overflow``."""
        if not valid_name(name):
            return "name"
        if not valid_value(value):
            return "value"
        if mode not in MODES:
            return "mode"
        with self._lock:
            current = self._values.get(attempt)
            if current is None:
                current = {}
            known = current.get(name)
            if known is None and len(current) >= MAX_METRICS_PER_STEP:
                return "limit"
            result: Number = value
            if known is not None:
                if mode == "add":
                    result = known + value
                elif mode == "max":
                    result = value if value > known else known
            if isinstance(result, float) and not math.isfinite(result):
                return "overflow"
            current[name] = result
            self._values[attempt] = current
            self._dirty.add(attempt)
        return None

    def take_dirty(self) -> List[Tuple[Attempt, Dict[str, Number]]]:
        """The attempts changed since the last call, with a copy of their values."""
        with self._lock:
            taken = [(a, dict(self._values[a])) for a in sorted(self._dirty)]
            self._dirty.clear()
        return taken

    def has_dirty(self) -> bool:
        with self._lock:
            return bool(self._dirty)

    def snapshot(self) -> Dict[Attempt, Dict[str, Number]]:
        """A copy of every attempt's values; the dirty marks are left alone."""
        with self._lock:
            return {a: dict(v) for a, v in self._values.items()}


class MetricWriter:
    """Writes changed metric records from a daemon thread, each as the attempt's full state.

    ``notify`` never blocks and never raises. A failing store is logged at most once a minute and the
    batch is dropped (the attempt is written again, in full, on its next call).
    """

    def __init__(
        self,
        store: StepAuditStore,
        state: MetricState,
        pipeline: str,
        env: str,
        run_id: str,
        ttl_seconds: int,
        flush_every: float = METRIC_FLUSH_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._state = state
        self._pipeline = pipeline
        self._env = env
        self._run_id = run_id
        self._ttl = ttl_seconds
        self._flush_every = flush_every
        self._clock = clock
        self._cond = threading.Condition()
        self._inflight = 0
        self._stopping = False
        self._force = False
        self._thread: Optional[threading.Thread] = None
        self._last_warning = float("-inf")
        self.writes = 0

    def notify(self) -> None:
        try:
            with self._cond:
                if self._stopping:
                    return
                self._ensure_thread()
                self._cond.notify_all()
        except Exception:
            return

    def _ensure_thread(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="waypoint-metrics", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        last = float("-inf")
        while True:
            with self._cond:
                while not self._stopping and not self._state.has_dirty():
                    self._cond.wait(self._flush_every)
                if self._stopping and not self._state.has_dirty():
                    return
                # at most one write pass per interval, so a hot loop is merged into a single write;
                # flush() and stop() skip the wait
                while not self._force and not self._stopping:
                    left = last + self._flush_every - time.monotonic()
                    if left <= 0:
                        break
                    self._cond.wait(left)
                batch = self._state.take_dirty()
                self._inflight += 1
            try:
                self._write(batch)
            finally:
                last = time.monotonic()
                with self._cond:
                    self._inflight -= 1
                    self._cond.notify_all()

    def _write(self, batch: List[Tuple[Attempt, Dict[str, Number]]]) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for (index, step), values in batch:
            record: Dict[str, object] = {
                "v": METRICS_VERSION,
                "pipeline": self._pipeline,
                "env": self._env,
                "run_id": self._run_id,
                "step": step,
                "index": index,
                "updated_at": now,
                "metrics": values,
            }
            try:
                self._store.write(
                    metrics_key(self._pipeline, self._env, self._run_id, index, step),
                    record,
                    self._ttl,
                )
                self.writes += 1
            except Exception as exc:
                at = self._clock()
                if at - self._last_warning >= WARN_EVERY_SECONDS:
                    self._last_warning = at
                    print(f"Warning: Waypoint metrics not written: {exc}")
                return  # the store is failing: leave the rest for the next pass

    def flush(self, timeout: float = 2.0) -> None:
        """Wait until every change has been written, at most ``timeout`` seconds."""
        deadline = time.monotonic() + timeout
        with self._cond:
            if self._state.has_dirty() and not self._stopping:
                self._ensure_thread()
            self._force = True
            self._cond.notify_all()
            while self._state.has_dirty() or self._inflight:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cond.wait(min(left, 0.05))
            self._force = False

    def stop(self, timeout: float = 2.0) -> None:
        """Flush, then end the thread. Safe to call more than once."""
        started = time.monotonic()
        self.flush(timeout)
        with self._cond:
            self._stopping = True
            self._cond.notify_all()
        thread = self._thread
        left = max(0.0, timeout - (time.monotonic() - started))
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=min(left, 1.0))
