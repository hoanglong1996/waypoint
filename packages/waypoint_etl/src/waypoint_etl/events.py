"""Author-sent events: ``waypoint_etl.log("Loaded batch 3", step="load", rows=1200)``.

An event is a short message with a level, an optional step and a few small named values. It goes onto a
bounded in-memory queue (the caller never waits on the network) and a background thread writes it to
Redis in batches. Nothing here raises into the pipeline. Contract:
specs/012-duration-and-run-events/contracts/library-api.md and redis-keys.md.
"""

import contextvars
import json
import math
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Mapping, Optional, Sequence, Tuple

from waypoint_etl.keys import EVENT_CAPS, events_key

LEVELS = tuple(EVENT_CAPS)
MAX_MESSAGE = 300
MAX_FIELDS = 10
MAX_TEXT = 100
MAX_STEP = 200
EVENT_VERSION = 1
QUEUE_SIZE = 2000
BATCH_SIZE = 100
FLUSH_EVERY_SECONDS = 1.0
WARN_EVERY_SECONDS = 60.0

_FIELD_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")

# The step a call is running in. A context variable, so it is right per thread and per asyncio task.
current_step: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "waypoint_current_step", default=None
)

Event = Dict[str, object]
Item = Tuple[str, Sequence[str], int]  # (key, JSON values, cap) for ``push_events``


def _clean_text(
    text: str, limit: int, capture: bool, redact: Optional[Callable[[str], str]]
) -> Optional[str]:
    """The text after the author's cleaning function, cut to ``limit``; None when it must be dropped."""
    if not capture:
        return None
    if redact is not None:
        try:
            cleaned = redact(text)
        except Exception:
            return None
        if not isinstance(cleaned, str):
            return None
        text = cleaned
    return text[:limit] or None


def build_event(
    message: str,
    *,
    n: int,
    level: str = "info",
    step: Optional[str] = None,
    fields: Optional[Mapping[str, object]] = None,
    now: Optional[datetime] = None,
    capture_message: bool = True,
    redact: Optional[Callable[[str], str]] = None,
) -> Event:
    """One event with every limit applied (message 300 characters, 10 fields, names, value types).

    With ``capture_message`` off the message is left out and text values are dropped (numbers stay);
    ``redact`` cleans the message and each text value before it is cut. Never raises.
    """
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    event: Event = {
        "v": EVENT_VERSION,
        "n": n,
        "ts": moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z",
        "level": level if level in LEVELS else "info",
    }
    if isinstance(step, str) and 0 < len(step) <= MAX_STEP:
        event["step"] = step
    text = (
        _clean_text(message, MAX_MESSAGE, capture_message, redact)
        if isinstance(message, str)
        else None
    )
    if text is not None:
        event["message"] = text
    kept: Dict[str, object] = {}
    for name, value in (fields or {}).items():
        if len(kept) >= MAX_FIELDS:
            break
        if not isinstance(name, str) or not _FIELD_NAME.match(name) or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                continue
            kept[name] = value
        elif isinstance(value, str):
            cleaned = _clean_text(value, MAX_TEXT, capture_message, redact)
            if cleaned is not None:
                kept[name] = cleaned
    if kept:
        event["fields"] = kept
    return event


class EventWriter:
    """Queues events and writes them from a daemon thread, one transaction per flush.

    ``submit`` never blocks and never raises. The queue holds ``capacity`` events; when it is full an
    info event is dropped, while a warning or error displaces the oldest queued info event. A failing
    store is logged at most once a minute and the batch is discarded.
    """

    def __init__(
        self,
        push: Callable[[Sequence[Item], int], None],
        pipeline: str,
        env: str,
        run_id: str,
        ttl_seconds: int,
        capacity: int = QUEUE_SIZE,
        batch: int = BATCH_SIZE,
        flush_every: float = FLUSH_EVERY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._json = json.dumps
        self._push = push
        self._pipeline = pipeline
        self._env = env
        self._run_id = run_id
        self._ttl = ttl_seconds
        self._capacity = capacity
        self._batch = batch
        self._flush_every = flush_every
        self._clock = clock
        self._items: Deque[Event] = deque()
        self._inflight = 0
        self._cond = threading.Condition()
        self._stopping = False
        self._thread: Optional[threading.Thread] = None
        self._last_warning = float("-inf")
        self.dropped = 0

    def submit(self, event: Event) -> None:
        try:
            with self._cond:
                if self._stopping:
                    return
                if len(self._items) >= self._capacity and not self._make_room(event):
                    self.dropped += 1
                    return
                self._items.append(event)
                self._ensure_thread()
                self._cond.notify_all()
        except Exception:
            return

    def _make_room(self, event: Event) -> bool:
        """Drop the oldest queued info event for a warning or error; False when nothing can go."""
        if event.get("level") == "info":
            return False
        for position, queued in enumerate(self._items):
            if queued.get("level") == "info":
                del self._items[position]
                self.dropped += 1
                return True
        return False

    def _ensure_thread(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="waypoint-events", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            with self._cond:
                if not self._items and not self._stopping:
                    self._cond.wait(self._flush_every)
                if not self._items:
                    if self._stopping:
                        return
                    continue
                take = [self._items.popleft() for _ in range(min(self._batch, len(self._items)))]
                self._inflight += len(take)
            try:
                self._write(take)
            finally:
                with self._cond:
                    self._inflight -= len(take)
                    self._cond.notify_all()

    def _write(self, events: List[Event]) -> None:
        grouped: Dict[str, List[str]] = {}
        for event in events:
            grouped.setdefault(str(event["level"]), []).append(self._json(event))
        items: List[Item] = [
            (events_key(self._pipeline, self._env, self._run_id, level), values, EVENT_CAPS[level])
            for level, values in grouped.items()
        ]
        try:
            self._push(items, self._ttl)
        except Exception as exc:
            now = self._clock()
            if now - self._last_warning >= WARN_EVERY_SECONDS:
                self._last_warning = now
                print(f"Warning: Waypoint events not written: {exc}")

    def flush(self, timeout: float = 2.0) -> None:
        """Wait until everything queued has been written, at most ``timeout`` seconds."""
        deadline = time.monotonic() + timeout
        with self._cond:
            self._cond.notify_all()
            while self._items or self._inflight:
                left = deadline - time.monotonic()
                if left <= 0:
                    return
                self._cond.wait(min(left, 0.05))

    def stop(self, timeout: float = 2.0) -> None:
        """Flush, then end the thread. Safe to call more than once."""
        self.flush(timeout)
        with self._cond:
            self._stopping = True
            self._cond.notify_all()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=min(timeout, 1.0))
