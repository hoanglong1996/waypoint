"""A background beat that tells Waypoint Monitor the run's process is still alive.

While the pipeline's process exists the beat keeps coming, even when a step is blocked, so the
monitor can tell a hung run (beating, not progressing) from a dead one (beat stopped). Like every
audit write, a failure here is logged and swallowed and never reaches the pipeline.
"""

import threading
import time
from typing import Callable

# One warning per this many seconds, so an unreachable store does not flood the log.
WARN_EVERY_SECONDS = 60.0


class Heartbeat:
    """Calls ``beat`` right away and then every ``interval`` seconds on a daemon thread."""

    def __init__(self, beat: Callable[[], None], interval: float) -> None:
        self._beat = beat
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="waypoint-heartbeat", daemon=True)
        self._last_warning = float("-inf")

    def start(self) -> None:
        if not self._thread.is_alive() and not self._stop.is_set():
            self._thread.start()

    def stop(self) -> None:
        """Stop beating. Safe to call more than once; waits at most a second for the thread."""
        self._stop.set()
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._once()
            if self._stop.wait(self._interval):
                return

    def _once(self) -> None:
        try:
            self._beat()
        except Exception as exc:
            now = time.monotonic()
            if now - self._last_warning >= WARN_EVERY_SECONDS:
                self._last_warning = now
                print(f"Warning: Waypoint heartbeat failed: {exc}")
