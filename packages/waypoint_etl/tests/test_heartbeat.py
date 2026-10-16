import contextlib
import io
import os
import re
import subprocess
import sys
import threading
import time
import unittest
from typing import Callable, Dict, List, Tuple

import waypoint_etl
from waypoint_etl import PipelineSpec, StepSpec, audited_step, registry

SPEC = PipelineSpec(name="demo", steps=(StepSpec("extract"),))
Entry = Tuple[str, Dict[str, object], int]


class FakeStore:
    def __init__(self) -> None:
        self.records: List[Entry] = []
        self.lock = threading.Lock()

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        with self.lock:
            self.records.append((key, record, ttl_seconds))

    def alive(self) -> List[Entry]:
        with self.lock:
            return [r for r in self.records if r[0].endswith(":alive")]


def wait_for(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


class TestHeartbeatBeats(unittest.TestCase):
    """specs/009-run-liveness-heartbeat/contracts/redis-keys.md: the alive item."""

    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def _init(self, store: FakeStore, seconds: float = 0.02, **kw: object) -> None:
        ok = waypoint_etl.init(
            pipeline=SPEC,
            redis_url=None,
            env="qa",
            run_id="R1",
            store=store,
            heartbeat_seconds=seconds,
            **kw,  # type: ignore[arg-type]
        )
        self.assertTrue(ok)

    def test_a_beat_is_written_right_after_init_not_after_a_full_interval(self) -> None:
        store = FakeStore()
        self._init(store, seconds=60)
        self.assertTrue(wait_for(lambda: len(store.alive()) >= 1))

    def test_beats_repeat_every_interval(self) -> None:
        store = FakeStore()
        self._init(store)
        self.assertTrue(wait_for(lambda: len(store.alive()) >= 4))

    def test_the_item_lives_at_the_alive_key_with_the_runs_ttl(self) -> None:
        store = FakeStore()
        self._init(store, ttl_days=2)
        self.assertTrue(wait_for(lambda: len(store.alive()) >= 1))
        key, _record, ttl = store.alive()[0]
        self.assertEqual(key, "waypoint:demo:qa:R1:alive")
        self.assertEqual(ttl, 2 * 86400)

    def test_the_item_holds_identities_and_a_time_only(self) -> None:
        store = FakeStore()
        self._init(store)
        self.assertTrue(wait_for(lambda: len(store.alive()) >= 1))
        record = store.alive()[0][1]
        self.assertEqual(set(record), {"v", "pipeline", "env", "run_id", "beat_at"})
        self.assertEqual(
            (record["v"], record["pipeline"], record["env"], record["run_id"]),
            (1, "demo", "qa", "R1"),
        )
        self.assertRegex(str(record["beat_at"]), re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$"))

    def test_the_flow_is_still_the_first_write(self) -> None:
        store = FakeStore()
        self._init(store, seconds=60)
        self.assertTrue(wait_for(lambda: len(store.alive()) >= 1))
        self.assertEqual(store.records[0][0], "waypoint:demo:qa:R1:flow")

    def test_default_interval_is_fifteen_seconds(self) -> None:
        self.assertEqual(waypoint_etl.keys.HEARTBEAT_SECONDS, 15)


class FailingStore(FakeStore):
    """Every write fails, like an unreachable Redis."""

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        raise ConnectionError("redis down")


class SlowAliveStore(FakeStore):
    """Heartbeat writes block for a long time; everything else is instant."""

    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        if key.endswith(":alive"):
            time.sleep(self.delay)
        super().write(key, record, ttl_seconds)


def heartbeat_threads() -> List[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "waypoint-heartbeat" and t.is_alive()]


def init_with(store: FakeStore, seconds: object, run_id: str = "R1") -> bool:
    return waypoint_etl.init(
        pipeline=SPEC,
        redis_url=None,
        env="qa",
        run_id=run_id,
        store=store,
        heartbeat_seconds=seconds,  # type: ignore[arg-type]
    )


class TestHeartbeatNeverHarms(unittest.TestCase):
    """User Story 4: the signal is diagnostic only (FR-004, FR-005, SC-004)."""

    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_unreachable_store_changes_nothing_for_the_pipeline(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(init_with(FailingStore(), 0.01))

            @audited_step("extract")
            def extract() -> List[int]:
                return [1, 2, 3]

            time.sleep(0.15)  # many beats fail meanwhile
            self.assertEqual(extract(), [1, 2, 3])
        self.assertIn("Warning:", out.getvalue())

    def test_failed_beats_warn_at_most_once_a_minute(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            init_with(FailingStore(), 0.01)
            time.sleep(0.2)
            registry.clear()
        self.assertEqual(out.getvalue().count("Waypoint heartbeat failed"), 1)

    def test_a_blocked_store_never_delays_a_step(self) -> None:
        store = SlowAliveStore(delay=1.0)
        init_with(store, 0.01)

        @audited_step("extract")
        def extract() -> int:
            return 1

        started = time.monotonic()
        for _ in range(20):
            extract()
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(len([r for r in store.records if ":step:" in r[0]]), 20)

    def test_clear_stops_further_beats(self) -> None:
        store = FakeStore()
        init_with(store, 0.01)
        self.assertTrue(wait_for(lambda: len(store.alive()) >= 2))
        registry.clear()
        count = len(store.alive())
        time.sleep(0.1)
        self.assertEqual(len(store.alive()), count)
        self.assertEqual(heartbeat_threads(), [])

    def test_clear_twice_and_without_init_is_harmless(self) -> None:
        registry.clear()
        init_with(FakeStore(), 0.01)
        registry.clear()
        registry.clear()

    def test_a_second_init_stops_the_first_runs_heartbeat(self) -> None:
        first, second = FakeStore(), FakeStore()
        with contextlib.redirect_stdout(io.StringIO()):  # "init called again" warning
            init_with(first, 0.01, run_id="R1")
            self.assertTrue(wait_for(lambda: len(first.alive()) >= 2))
            init_with(second, 0.01, run_id="R2")
        count = len(first.alive())
        self.assertTrue(wait_for(lambda: len(second.alive()) >= 2))
        self.assertEqual(len(first.alive()), count)
        self.assertEqual(len(heartbeat_threads()), 1)
        self.assertEqual(second.alive()[0][0], "waypoint:demo:qa:R2:alive")

    def test_the_thread_is_a_daemon(self) -> None:
        init_with(FakeStore(), 60)
        self.assertTrue(wait_for(lambda: len(heartbeat_threads()) == 1))
        self.assertTrue(heartbeat_threads()[0].daemon)

    def test_heartbeat_can_be_turned_off(self) -> None:
        for seconds in (None, 0, -1):
            with self.subTest(seconds=seconds):
                store = FakeStore()
                self.assertTrue(init_with(store, seconds))
                time.sleep(0.05)
                self.assertEqual((heartbeat_threads(), store.alive()), ([], []))
                registry.clear()

    def test_a_process_exits_while_its_heartbeat_is_still_running(self) -> None:
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
        code = (
            "import waypoint_etl\n"
            "from waypoint_etl import PipelineSpec, StepSpec\n"
            "class S:\n"
            "    def write(self, key, record, ttl): pass\n"
            "waypoint_etl.init(pipeline=PipelineSpec(name='d', steps=(StepSpec('x'),)),"
            " redis_url=None, env='qa', store=S(), heartbeat_seconds=0.01)\n"
            "print('done')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONPATH": src},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "done"), result.stderr)


if __name__ == "__main__":
    unittest.main()
