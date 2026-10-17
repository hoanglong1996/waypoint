"""Map steps: ``with waypoint_etl.map_step("accounts"): ... with waypoint_etl.item(key): ...``.

A map step runs a linear item flow of inner steps once per item. Everything about items is merged in
memory under one lock (``MapTracker``) and a background thread (``MapWriter``) writes the changed records
at most once a second, so a loop costs dictionary updates and never a network call. Only the first
``MAP_DETAIL_LIMIT`` items, a bounded number of further failed items and the slowest later items keep a
record; the aggregate always counts every item. Nothing here raises into the pipeline. Contract:
specs/014-map-step-fan-out/contracts/redis-keys.md and library-api.md.
"""

import contextvars
import heapq
import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from waypoint_etl.keys import (
    COMPACT_MESSAGE,
    EVICT_TTL_SECONDS,
    HIST_RATIO,
    ITEM_TRACE_BYTES,
    MAP_DETAIL_LIMIT,
    MAP_EXTRA_FAILED_LIMIT,
    MAP_FAILED_LISTED,
    MAP_FLUSH_SECONDS,
    MAP_SLOWEST_KEPT,
    MAP_SLOWEST_LISTED,
    MAP_VERSION,
    MAX_INNER_STEPS,
    MAX_ITEM_KEY,
    item_key,
    map_key,
)
from waypoint_etl.metrics import MetricState, Number
from waypoint_etl.stores import StepAuditStore

WARN_EVERY_SECONDS = 60.0
# Keys remembered to spot a duplicate; past this a repeated key is no longer noticed.
SEEN_CAP = 200_000
OMITTED = "... (earlier frames omitted)\n"

_BAD_KEY_CHARS = re.compile(r"[^A-Za-z0-9_.-]")
_LOG_RATIO = math.log(HIST_RATIO)

Record = Dict[str, object]
Pair = Tuple[str, Record]


class ItemHandle:
    """The item a piece of code is running in: ``item`` is None for a discarded (duplicate) pass."""

    __slots__ = ("block", "item")

    def __init__(self, block: "MapBlock", item: Optional["ItemState"]) -> None:
        self.block = block
        self.item = item


# The item and map a call is running in. Context variables, so they are right per thread and per task.
current_item: "contextvars.ContextVar[Optional[ItemHandle]]" = contextvars.ContextVar(
    "waypoint_current_item", default=None
)
current_map: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "waypoint_current_map", default=None
)


def _stamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitise_key(raw: object, arrival: int) -> Tuple[str, bool]:
    """``(key, changed)``: the key limited to ``[A-Za-z0-9_.-]{1,64}``.

    Other characters become ``_``, a longer key is cut, and an empty or non-text key becomes
    ``item_{arrival}``. ``changed`` says whether the raw key had to be altered.
    """
    if not isinstance(raw, str) or not raw:
        return f"item_{arrival}", True
    key = _BAD_KEY_CHARS.sub("_", raw)[:MAX_ITEM_KEY]
    return key, key != raw


def bucket(ms: float) -> int:
    """Histogram bucket of a duration: ``floor(ln(ms) / ln(1.1))`` for 1 ms and more, else 0."""
    if ms < 1:
        return 0
    return int(math.floor(math.log(ms) / _LOG_RATIO))


def bucket_value(index: int) -> float:
    """The middle (geometric) of a bucket, within 5% of any duration that fell in it."""
    return float(HIST_RATIO ** (index + 0.5))


def cut_traceback(text: str, limit: int = ITEM_TRACE_BYTES) -> str:
    """At most ``limit`` UTF-8 bytes, keeping the last frames."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    room = limit - len(OMITTED.encode("utf-8"))
    return OMITTED + raw[-room:].decode("utf-8", errors="ignore")


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class InnerResult:
    """The latest attempt of one inner step in one item."""

    __slots__ = (
        "step",
        "seq",
        "attempt",
        "state",
        "inputs",
        "output",
        "started_at",
        "started_mono",
        "duration_ms",
        "error",
        "in_n",
        "out_n",
    )

    def __init__(self, step: str, seq: int, attempt: int, started_at: str, mono: float) -> None:
        self.step = step
        self.seq = seq
        self.attempt = attempt
        self.state = "running"
        self.inputs: Dict[str, int] = {}
        self.output: Optional[int] = None
        self.started_at = started_at
        self.started_mono = mono
        self.duration_ms: Optional[int] = None
        self.error: Optional[Dict[str, str]] = None
        self.in_n = 0
        self.out_n = 0


class ItemState:
    """One item of a map step while it runs and after."""

    __slots__ = (
        "key",
        "arrival",
        "detailed",
        "started_at",
        "started_mono",
        "finished_at",
        "duration_ms",
        "state",
        "results",
        "seq",
        "attempts",
        "error",
        "metrics",
        "loss",
        "ended",
    )

    def __init__(self, key: str, arrival: int, started_at: str, mono: float) -> None:
        self.key = key
        self.arrival = arrival
        self.detailed = arrival <= MAP_DETAIL_LIMIT
        self.started_at = started_at
        self.started_mono = mono
        self.finished_at: Optional[str] = None
        self.duration_ms: Optional[int] = None
        self.state = "running"
        self.results: Dict[str, InnerResult] = {}
        self.seq = 0
        self.attempts: Dict[str, int] = {}
        self.error: Optional[Dict[str, str]] = None
        self.metrics: Optional[MetricState] = None
        self.loss = False
        self.ended = False


def _error_json(error: Dict[str, str], compact: bool) -> Dict[str, str]:
    """An error object for a record: a full one keeps a cut trace, a compact one a short message."""
    out: Dict[str, str] = {"type": error.get("type", "Error")}
    message = error.get("message")
    if message is not None:
        out["message"] = message[:COMPACT_MESSAGE] if compact else message
    out["traceback"] = "" if compact else cut_traceback(error.get("traceback", ""))
    return out


class MapTracker:
    """Live state of one map step block: items, counters, histogram and what keeps a record.

    All methods are safe to call from many threads and none raises. ``warn(key, text)`` is called at
    most once per distinct problem by the caller's own bounded memory.
    """

    def __init__(
        self,
        pipeline: str,
        env: str,
        run_id: str,
        name: str,
        index: int,
        declared: Sequence[str],
        warn: Callable[[str, str], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.pipeline = pipeline
        self.env = env
        self.run_id = run_id
        self.name = name
        self.index = index
        self._declared = list(declared)
        self._warn = warn
        self._clock = clock
        self._lock = threading.Lock()
        self._started_at = _stamp(datetime.now(timezone.utc))
        self._ended_at: Optional[str] = None
        self._arrivals = 0
        self._seen: Set[str] = set()
        self._items: Dict[str, ItemState] = {}
        self._counts = {"running": 0, "done": 0, "failed": 0}
        self._in_total = 0
        self._out_total = 0
        self._lost = 0
        self._inner: Dict[str, Dict[str, int]] = {
            step: {"running": 0, "done": 0, "failed": 0, "in": 0, "out": 0} for step in declared
        }
        self._hist: Dict[int, int] = {}
        self._dur_count = 0
        self._dur_sum = 0
        self._slowest: List[Tuple[int, int, str]] = []  # (ms, arrival, key), slowest first
        self._failed_items: List[Tuple[str, str, str]] = []
        self._extra_failed = 0
        self._failed_without_record = 0
        self._slow_heap: List[Tuple[int, int, str, Record]] = []  # min-heap on duration
        self._dirty: Dict[str, ItemState] = {}
        self._pending: List[Pair] = []  # compact records to write
        self._evictions: List[Pair] = []  # displaced slow records, rewritten with a 1-second TTL
        self._agg_dirty = True

    # ---- items -------------------------------------------------------------------------------

    @property
    def started(self) -> int:
        with self._lock:
            return self._arrivals

    def start_item(self, raw_key: object) -> Optional[ItemState]:
        """Register an item; None when its (sanitised) key already started in this map step."""
        try:
            with self._lock:
                arrival = self._arrivals + 1
                key, changed = sanitise_key(raw_key, arrival)
                if changed:
                    shown = raw_key[:40] if isinstance(raw_key, str) else type(raw_key).__name__
                    self._warn(f"key:{shown}", f"item key {shown!r} changed to {key!r}")
                if key in self._seen:
                    self._warn(
                        f"dup:{key}",
                        f"item key {key!r} started twice in map step {self.name!r}; ignored",
                    )
                    return None
                self._arrivals = arrival
                if len(self._seen) < SEEN_CAP:
                    self._seen.add(key)
                item = ItemState(key, arrival, _stamp(datetime.now(timezone.utc)), self._clock())
                self._items[key] = item
                self._counts["running"] += 1
                self._touch(item)
                return item
        except Exception:
            return None

    def _touch(self, item: ItemState) -> None:
        """Mark an item and the aggregate as changed (only items with a full record are written live)."""
        if item.detailed:
            self._dirty[item.key] = item
        self._agg_dirty = True

    def _inner_entry(self, step: str) -> Optional[Dict[str, int]]:
        entry = self._inner.get(step)
        if entry is None:
            if len(self._inner) >= MAX_INNER_STEPS:
                return None
            entry = {"running": 0, "done": 0, "failed": 0, "in": 0, "out": 0}
            self._inner[step] = entry
        return entry

    def _leave(self, result: InnerResult) -> None:
        entry = self._inner.get(result.step)
        if entry is None:
            return
        entry[result.state] -= 1
        if result.state == "done":
            entry["in"] -= result.in_n
            entry["out"] -= result.out_n

    def _enter(self, result: InnerResult) -> None:
        entry = self._inner_entry(result.step)
        if entry is None:
            return
        entry[result.state] += 1
        if result.state == "done":
            entry["in"] += result.in_n
            entry["out"] += result.out_n

    def begin_inner(self, item: ItemState, step: str) -> int:
        """Start an inner step on ``item``; returns its sequence number (0 when it is not recorded)."""
        try:
            with self._lock:
                if item.ended:
                    return 0
                old = item.results.get(step)
                if old is None and len(item.results) >= MAX_INNER_STEPS:
                    self._warn(
                        f"inner:{step}", f"inner step {step!r} dropped: too many inner steps"
                    )
                    return 0
                item.seq += 1
                attempt = item.attempts.get(step, 0) + 1
                item.attempts[step] = attempt
                if old is not None:
                    self._leave(old)
                result = InnerResult(
                    step, item.seq, attempt, _stamp(datetime.now(timezone.utc)), self._clock()
                )
                item.results[step] = result
                self._enter(result)
                self._touch(item)
                return item.seq
        except Exception:
            return 0

    def finish_inner(
        self,
        item: ItemState,
        step: str,
        seq: int,
        inputs: Dict[str, Optional[int]],
        output: Optional[int],
    ) -> None:
        try:
            with self._lock:
                result = item.results.get(step)
                if result is None or result.seq != seq or item.ended:
                    return
                self._leave(result)
                result.state = "done"
                result.inputs = {k: v for k, v in inputs.items() if v is not None and _is_count(v)}
                result.output = output if _is_count(output) else None
                result.duration_ms = max(0, round((self._clock() - result.started_mono) * 1000))
                result.in_n = sum(result.inputs.values())
                result.out_n = result.output or 0
                self._enter(result)
                if (
                    result.output == 0
                    and any(v > 0 for v in result.inputs.values())
                    and not item.loss
                ):
                    item.loss = True
                    self._lost += 1
                self._touch(item)
        except Exception:
            return

    def fail_inner(self, item: ItemState, step: str, seq: int, error: Dict[str, str]) -> None:
        try:
            with self._lock:
                result = item.results.get(step)
                if result is None or result.seq != seq or item.ended:
                    return
                self._leave(result)
                result.state = "failed"
                result.error = error
                result.duration_ms = max(0, round((self._clock() - result.started_mono) * 1000))
                self._enter(result)
                self._touch(item)
        except Exception:
            return

    def record_metric(
        self, item: ItemState, step: str, name: str, value: Number, mode: str
    ) -> Optional[str]:
        """Merge a metric into the item's inner step. None when applied (or deliberately not kept);
        else the reason it was dropped: ``step``, ``name``, ``value``, ``mode``, ``limit``, ``overflow``.
        """
        try:
            with self._lock:
                result = item.results.get(step)
                if result is None:
                    return "step"
                if not item.detailed or item.ended:
                    return None  # an item with no record of its own keeps no metrics
                if item.metrics is None:
                    item.metrics = MetricState()
                state = item.metrics
                attempt = (result.seq, step)
            reason = state.apply(attempt, name, value, mode)
            if reason is None:
                with self._lock:
                    self._touch(item)
            return reason
        except Exception:
            return None

    def end_item(self, item: ItemState, error: Optional[Dict[str, str]]) -> None:
        """Close an item: its state, counters, histogram and whether a record is kept."""
        try:
            with self._lock:
                self._end_item(item, error)
        except Exception:
            return

    def _end_item(self, item: ItemState, error: Optional[Dict[str, str]]) -> None:
        if item.ended:
            return
        item.ended = True
        ms = max(0, round((self._clock() - item.started_mono) * 1000))
        item.duration_ms = ms
        item.finished_at = _stamp(datetime.now(timezone.utc))
        failed_results = [r for r in item.results.values() if r.state == "failed"]
        failed = bool(failed_results) or error is not None
        item.error = error if (error is not None and not failed_results) else None
        item.state = "failed" if failed else "done"
        self._counts["running"] -= 1
        self._counts[item.state] += 1
        self._dur_count += 1
        self._dur_sum += ms
        b = bucket(ms)
        self._hist[b] = self._hist.get(b, 0) + 1
        self._slowest.append((ms, item.arrival, item.key))
        self._slowest.sort(key=lambda t: (-t[0], t[1]))
        del self._slowest[MAP_SLOWEST_LISTED:]
        first = item.results.get(self._declared[0]) if self._declared else None
        last = item.results.get(self._declared[-1]) if self._declared else None
        if first is not None and first.state == "done":
            self._in_total += first.in_n
        if last is not None and last.state == "done" and last.output is not None:
            self._out_total += last.out_n
        if failed and len(self._failed_items) < MAP_FAILED_LISTED:
            where = failed_results[0] if failed_results else None
            step = where.step if where else self._fallback_step(item)
            kind = (where.error if where and where.error else error or {}).get("type", "Error")
            self._failed_items.append((item.key, step, kind))
        self._agg_dirty = True
        if item.detailed:
            self._dirty[item.key] = item
            return
        self._items.pop(item.key, None)
        record = self._item_record(item, compact=True)
        key = item_key(self.pipeline, self.env, self.run_id, self.name, item.key)
        if failed:
            if self._extra_failed < MAP_EXTRA_FAILED_LIMIT:
                self._extra_failed += 1
                self._pending.append((key, record))
            else:
                self._failed_without_record += 1
            return
        entry = (ms, item.arrival, key, record)
        if len(self._slow_heap) < MAP_SLOWEST_KEPT:
            heapq.heappush(self._slow_heap, entry)
            self._pending.append((key, record))
        elif ms > self._slow_heap[0][0]:
            gone = heapq.heapreplace(self._slow_heap, entry)
            self._evictions.append((gone[2], gone[3]))
            self._pending = [p for p in self._pending if p[0] != gone[2]]
            self._pending.append((key, record))

    def _fallback_step(self, item: ItemState) -> str:
        """Where an item that failed outside any inner step was: its latest inner step, else the first."""
        if item.results:
            return list(item.results)[-1]
        return self._declared[0] if self._declared else self.name

    def end_block(self) -> None:
        """The loop left its block: no item is expected to start any more."""
        with self._lock:
            self._ended_at = _stamp(datetime.now(timezone.utc))
            self._agg_dirty = True

    # ---- records -----------------------------------------------------------------------------

    def _item_record(self, item: ItemState, compact: bool) -> Record:
        steps: List[Record] = []
        for r in item.results.values():
            entry: Record = {
                "step": r.step,
                "attempt": r.attempt,
                "state": r.state,
                "inputs": dict(r.inputs),
                "output": r.output,
                "started_at": r.started_at,
            }
            if r.duration_ms is not None:
                entry["duration_ms"] = r.duration_ms
            if r.error is not None:
                entry["error"] = _error_json(r.error, compact)
            steps.append(entry)
        record: Record = {
            "v": MAP_VERSION,
            "pipeline": self.pipeline,
            "env": self.env,
            "run_id": self.run_id,
            "map": self.name,
            "key": item.key,
            "index": item.arrival,
            "state": item.state,
            "started_at": item.started_at,
        }
        if item.finished_at is not None:
            record["finished_at"] = item.finished_at
        if item.duration_ms is not None:
            record["duration_ms"] = item.duration_ms
        record["steps"] = steps
        if not compact and item.metrics is not None:
            snapshot = item.metrics.snapshot()
            metrics = {
                step: dict(snapshot[(r.seq, step)])
                for step, r in item.results.items()
                if (r.seq, step) in snapshot
            }
            if metrics:
                record["metrics"] = metrics
        if item.error is not None:
            record["error"] = _error_json(item.error, compact)
        if compact:
            record["compact"] = True
        return record

    def _aggregate(self) -> Record:
        started = self._arrivals
        kept = min(started, MAP_DETAIL_LIMIT) + self._extra_failed + len(self._slow_heap)
        return {
            "v": MAP_VERSION,
            "pipeline": self.pipeline,
            "env": self.env,
            "run_id": self.run_id,
            "map": self.name,
            "index": self.index,
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "updated_at": _stamp(datetime.now(timezone.utc)),
            "counts": {
                "started": started,
                "running": self._counts["running"],
                "done": self._counts["done"],
                "failed": self._counts["failed"],
            },
            "in_total": self._in_total,
            "out_total": self._out_total,
            "lost_items": self._lost,
            "inner": {step: dict(counts) for step, counts in self._inner.items()},
            "duration": {
                "count": self._dur_count,
                "sum_ms": self._dur_sum,
                "hist": {str(b): n for b, n in sorted(self._hist.items())},
                "slowest": [{"key": k, "ms": ms} for ms, _, k in self._slowest],
            },
            "failed_items": [
                {"key": k, "step": step, "error_type": kind} for k, step, kind in self._failed_items
            ],
            "detail": {
                "limit": MAP_DETAIL_LIMIT,
                "kept": kept,
                "extra_failed_limit": MAP_EXTRA_FAILED_LIMIT,
                "failed_without_record": self._failed_without_record,
                "slow_kept": len(self._slow_heap),
            },
        }

    def has_dirty(self) -> bool:
        with self._lock:
            return bool(self._dirty or self._pending or self._evictions or self._agg_dirty)

    def take_dirty(self) -> Tuple[List[Pair], List[Pair], Optional[Record]]:
        """What changed since the last call: records to write, displaced records to retire, aggregate."""
        with self._lock:
            writes: List[Pair] = [
                (
                    item_key(self.pipeline, self.env, self.run_id, self.name, item.key),
                    self._item_record(item, compact=False),
                )
                for item in sorted(self._dirty.values(), key=lambda i: i.arrival)
            ]
            writes.extend(self._pending)
            evictions = list(self._evictions)
            aggregate = self._aggregate() if self._agg_dirty or writes or evictions else None
            self._dirty.clear()
            self._pending = []
            self._evictions = []
            self._agg_dirty = False
        return writes, evictions, aggregate

    def aggregate_key(self) -> str:
        return map_key(self.pipeline, self.env, self.run_id, self.name)


class MapWriter:
    """Writes changed records from a daemon thread, in one batch per pass.

    ``notify`` never blocks and never raises. A failing store is logged at most once a minute and the
    batch is dropped (a record is written again, in full, on its next change). A store with a
    ``write_many`` takes each batch in one round trip; one without is written to record by record.
    """

    def __init__(
        self,
        store: StepAuditStore,
        tracker: MapTracker,
        ttl_seconds: int,
        flush_every: float = MAP_FLUSH_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._tracker = tracker
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
            self._thread = threading.Thread(target=self._run, name="waypoint-maps", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        last = float("-inf")
        while True:
            with self._cond:
                while not self._stopping and not self._tracker.has_dirty():
                    self._cond.wait(self._flush_every)
                if self._stopping and not self._tracker.has_dirty():
                    return
                # at most one write pass per interval, so a busy loop is merged into one batch;
                # flush() and stop() skip the wait
                while not self._force and not self._stopping:
                    left = last + self._flush_every - time.monotonic()
                    if left <= 0:
                        break
                    self._cond.wait(left)
                batch = self._tracker.take_dirty()
                self._inflight += 1
            try:
                self._write(batch)
            finally:
                last = time.monotonic()
                with self._cond:
                    self._inflight -= 1
                    self._cond.notify_all()

    def _write(self, batch: Tuple[List[Pair], List[Pair], Optional[Record]]) -> None:
        writes, evictions, aggregate = batch
        items = list(writes)
        if aggregate is not None:
            items.append((self._tracker.aggregate_key(), aggregate))
        try:
            if items:
                self._store_many(items, self._ttl)
            if evictions:
                self._store_many(evictions, EVICT_TTL_SECONDS)
            self.writes += 1
        except Exception as exc:
            at = self._clock()
            if at - self._last_warning >= WARN_EVERY_SECONDS:
                self._last_warning = at
                print(f"Warning: Waypoint map records not written: {exc}")

    def _store_many(self, items: List[Pair], ttl: int) -> None:
        many = getattr(self._store, "write_many", None)
        if many is not None:
            many(items, ttl)
            return
        for key, record in items:
            self._store.write(key, record, ttl)

    def flush(self, timeout: float = 2.0) -> None:
        """Wait until every change has been written, at most ``timeout`` seconds."""
        deadline = time.monotonic() + timeout
        with self._cond:
            if self._tracker.has_dirty() and not self._stopping:
                self._ensure_thread()
            self._force = True
            self._cond.notify_all()
            while self._tracker.has_dirty() or self._inflight:
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


class MapBlock:
    """An open map step block: its run-level attempt index, tracker and writer."""

    __slots__ = ("name", "index", "tracker", "writer")

    def __init__(self, name: str, index: int, tracker: MapTracker, writer: MapWriter) -> None:
        self.name = name
        self.index = index
        self.tracker = tracker
        self.writer = writer
