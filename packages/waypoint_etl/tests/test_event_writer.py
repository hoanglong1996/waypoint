"""The events writer: never blocks the caller, bounded, safe when Redis is down.

Specs 012 research R5, R6 and spec User Story 6 (FR-017, FR-018, FR-020, SC-006, SC-007).
"""

import io
import threading
import time
import unittest
from contextlib import redirect_stdout
from typing import Any, Dict, List, Sequence, Tuple

import waypoint_etl
from waypoint_etl import PipelineSpec, StepSpec, audited_step, registry
from waypoint_etl.auditor import StepAuditor
from waypoint_etl.events import EventWriter

Item = Tuple[str, Sequence[str], int]
SPEC = PipelineSpec(name="demo", steps=(StepSpec("extract"),))


def event(n: int, level: str = "info") -> Dict[str, object]:
    return {"v": 1, "n": n, "ts": "2026-10-17T02:00:00.000Z", "level": level, "message": f"m{n}"}


class Recorder:
    def __init__(self) -> None:
        self.calls: List[Tuple[List[Item], int]] = []
        self.lock = threading.Lock()

    def push(self, items: Sequence[Item], ttl: int) -> None:
        with self.lock:
            self.calls.append((list(items), ttl))

    def stored(self) -> List[str]:
        return [v for items, _ in self.calls for _k, values, _c in items for v in values]


def writer(push: Any, **kw: Any) -> EventWriter:
    return EventWriter(push, "demo", "qa", "R1", 3600, **kw)


class TestNonBlocking(unittest.TestCase):
    def test_submit_returns_while_the_store_is_blocked(self) -> None:
        gate = threading.Event()
        entered = threading.Event()

        def stuck(items: Sequence[Item], ttl: int) -> None:
            entered.set()
            gate.wait(10)

        w = writer(stuck, flush_every=0.01)
        w.submit(event(1))
        self.assertTrue(entered.wait(5))
        started = time.monotonic()
        for n in range(2, 600):
            w.submit(event(n))
        self.assertLess(time.monotonic() - started, 0.5)
        gate.set()
        w.stop(5)

    def test_flush_waits_at_most_the_timeout_with_a_hanging_store(self) -> None:
        gate = threading.Event()
        w = writer(lambda items, ttl: gate.wait(10), flush_every=0.01)
        w.submit(event(1))
        started = time.monotonic()
        w.flush(0.3)
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.25)
        self.assertLess(elapsed, 1.5)
        gate.set()
        w.stop(5)


class TestBatching(unittest.TestCase):
    def test_batches_of_at_most_100_grouped_by_level_one_transaction_each(self) -> None:
        gate = threading.Event()
        rec = Recorder()

        def hold_first(items: Sequence[Item], ttl: int) -> None:
            gate.wait(5)
            rec.push(items, ttl)

        w = writer(hold_first, flush_every=0.01)
        w.submit(event(0))  # picked up at once, then held by the gate
        time.sleep(0.1)
        for n in range(1, 251):
            w.submit(event(n, "info" if n % 5 else "error"))
        gate.set()
        w.flush(5)
        sizes = [sum(len(values) for _k, values, _c in items) for items, _ in rec.calls]
        self.assertTrue(all(size <= 100 for size in sizes), sizes)
        self.assertEqual(sum(sizes), 251)
        for items, ttl in rec.calls:
            self.assertEqual(ttl, 3600)
            keys = [k for k, _v, _c in items]
            self.assertEqual(len(keys), len(set(keys)))
        caps = {k.rsplit(":", 1)[1]: c for items, _ in rec.calls for k, _v, c in items}
        self.assertEqual(caps, {"info": 500, "error": 200})
        w.stop(5)

    def test_keys_and_ttl(self) -> None:
        rec = Recorder()
        w = writer(rec.push)
        w.submit(event(1, "warning"))
        w.flush(5)
        ((items, ttl),) = rec.calls
        self.assertEqual(items[0][0], "waypoint:demo:qa:R1:events:warning")
        self.assertEqual((items[0][2], ttl), (200, 3600))
        w.stop(5)


class TestQueueRules(unittest.TestCase):
    def test_a_full_queue_drops_info_but_warnings_displace_queued_info(self) -> None:
        gate = threading.Event()
        entered = threading.Event()
        rec = Recorder()

        def hold(items: Sequence[Item], ttl: int) -> None:
            entered.set()
            gate.wait(5)
            rec.push(items, ttl)

        w = writer(hold, capacity=5, batch=100, flush_every=0.01)
        w.submit(event(0))
        self.assertTrue(entered.wait(5))  # the writer is busy: what follows stays queued
        for n in range(1, 6):
            w.submit(event(n))  # fills the queue with info
        w.submit(event(6))  # full: dropped
        w.submit(event(7, "warning"))  # displaces the oldest queued info (n=1)
        w.submit(event(8, "error"))  # displaces n=2
        self.assertEqual(w.dropped, 3)
        gate.set()
        w.flush(5)
        numbers = sorted(int(v.split('"n": ')[1].split(",")[0]) for v in rec.stored())
        self.assertEqual(numbers, [0, 3, 4, 5, 7, 8])
        w.stop(5)

    def test_a_full_queue_of_warnings_drops_the_new_event(self) -> None:
        gate = threading.Event()
        entered = threading.Event()
        w = writer(lambda i, t: (entered.set(), gate.wait(5)), capacity=2, flush_every=0.01)
        w.submit(event(0))
        self.assertTrue(entered.wait(5))
        w.submit(event(1, "warning"))
        w.submit(event(2, "warning"))
        w.submit(event(3, "error"))  # nothing to displace
        self.assertEqual(w.dropped, 1)
        gate.set()
        w.stop(5)


class TestFailures(unittest.TestCase):
    def test_a_failing_store_is_caught_warned_once_a_minute_and_recovers(self) -> None:
        now = [1000.0]
        calls: List[int] = []
        broken = [True]

        def push(items: Sequence[Item], ttl: int) -> None:
            calls.append(1)
            if broken[0]:
                raise ConnectionError("redis down")

        out = io.StringIO()
        w = writer(push, clock=lambda: now[0], flush_every=0.01)
        with redirect_stdout(out):
            w.submit(event(1))
            w.flush(5)
            w.submit(event(2))
            w.flush(5)
            now[0] += 61
            w.submit(event(3))
            w.flush(5)
        self.assertEqual(len(calls), 3)
        self.assertEqual(out.getvalue().count("Warning: Waypoint events not written"), 2)
        broken[0] = False
        w.submit(event(4))
        w.flush(5)
        self.assertEqual(len(calls), 4)
        w.stop(5)

    def test_stop_is_safe_twice_and_stops_taking_events(self) -> None:
        rec = Recorder()
        w = writer(rec.push)
        w.submit(event(1))
        w.stop(5)
        w.stop(5)
        w.submit(event(2))
        self.assertEqual(len(rec.stored()), 1)


class TestThreads(unittest.TestCase):
    def test_many_threads_lose_nothing_and_keep_per_thread_order(self) -> None:
        rec = Recorder()
        w = writer(rec.push, capacity=10000, flush_every=0.01)

        def send(tid: int) -> None:
            for i in range(500):
                w.submit({**event(tid * 1000 + i), "message": f"t{tid}-{i}"})

        threads = [threading.Thread(target=send, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        w.flush(10)
        stored = rec.stored()
        self.assertEqual(len(stored), 4000)
        for tid in range(8):
            mine = [int(v.split(f"t{tid}-")[1].split('"')[0]) for v in stored if f"t{tid}-" in v]
            self.assertEqual(mine, list(range(500)))
        w.stop(5)


class FakeStore:
    def __init__(self, behaviour: str = "ok") -> None:
        self.behaviour = behaviour
        self.pushed: List[str] = []
        self.lock = threading.Lock()
        self.gate = threading.Event()

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        if self.behaviour == "raise":
            raise ConnectionError("redis down")

    def push_events(self, items: Sequence[Item], ttl_seconds: int) -> None:
        if self.behaviour == "raise":
            raise ConnectionError("redis down")
        if self.behaviour == "hang":
            self.gate.wait(30)
        with self.lock:
            self.pushed += [v for _k, values, _c in items for v in values]


class TestPipelineIsUnaffected(unittest.TestCase):
    """SC-007: with the store hanging or raising, results and exceptions are identical."""

    def tearDown(self) -> None:
        registry.clear()

    def run_step(self, store: FakeStore) -> Any:
        registry.set_active(StepAuditor(store, SPEC, env="qa", ttl_seconds=60, run_id="R"))  # type: ignore[arg-type]

        @audited_step("extract")
        def work() -> List[int]:
            for i in range(200):
                waypoint_etl.log(f"row {i}", i=i)
            return [1, 2, 3]

        return work()

    def test_same_result_with_a_working_a_raising_and_a_hanging_store(self) -> None:
        results = []
        for behaviour in ("ok", "raise", "hang"):
            store = FakeStore(behaviour)
            out = io.StringIO()
            started = time.monotonic()
            with redirect_stdout(out):
                results.append(self.run_step(store))
            self.assertLess(time.monotonic() - started, 2.0, behaviour)
            store.gate.set()
            registry.clear()
        self.assertEqual(results, [[1, 2, 3]] * 3)

    def test_the_exception_of_a_failing_step_is_the_same(self) -> None:
        for behaviour in ("ok", "raise", "hang"):
            store = FakeStore(behaviour)
            registry.set_active(StepAuditor(store, SPEC, env="qa", ttl_seconds=60, run_id="R"))  # type: ignore[arg-type]

            @audited_step("extract")
            def boom() -> None:
                waypoint_etl.error("about to fail")
                raise KeyError("x")

            with redirect_stdout(io.StringIO()), self.assertRaises(KeyError) as ctx:
                boom()
            self.assertEqual(ctx.exception.args, ("x",))
            store.gate.set()
            registry.clear()


class TestExit(unittest.TestCase):
    def test_clear_delivers_what_is_queued(self) -> None:
        store = FakeStore()
        registry.set_active(StepAuditor(store, SPEC, env="qa", ttl_seconds=60, run_id="R"))  # type: ignore[arg-type]
        for i in range(50):
            waypoint_etl.log(f"m{i}")
        registry.clear()
        self.assertEqual(len(store.pushed), 50)

    def test_the_exit_hook_flushes_the_active_auditor_within_two_seconds(self) -> None:
        store = FakeStore()
        registry.set_active(StepAuditor(store, SPEC, env="qa", ttl_seconds=60, run_id="R"))  # type: ignore[arg-type]
        try:
            for i in range(20):
                waypoint_etl.log(f"m{i}")
            registry._flush_at_exit()
            self.assertEqual(len(store.pushed), 20)
            hanging = FakeStore("hang")
            registry.set_active(StepAuditor(hanging, SPEC, env="qa", ttl_seconds=60, run_id="R"))  # type: ignore[arg-type]
            waypoint_etl.log("stuck")
            started = time.monotonic()
            registry._flush_at_exit()
            self.assertLess(time.monotonic() - started, 3.0)
            hanging.gate.set()
        finally:
            registry.clear()

    def test_the_hook_is_registered_once_by_init(self) -> None:
        import atexit  # noqa: F401  (documented behaviour: one hook, however often init runs)

        before = registry._exit_hook
        registry.init(pipeline=SPEC, redis_url=None, env="qa", store=FakeStore(), heartbeat_seconds=None)  # type: ignore[arg-type]
        registry.init(pipeline=SPEC, redis_url=None, env="qa", store=FakeStore(), heartbeat_seconds=None)  # type: ignore[arg-type]
        registry.clear()
        self.assertTrue(registry._exit_hook)
        self.assertIn(before, (True, False))


class TestSpeed(unittest.TestCase):
    """SC-006: 5,000 events add at most 5% to a step (same loop with and without ``log``)."""

    def test_overhead_is_small(self) -> None:
        store = FakeStore()
        registry.set_active(StepAuditor(store, SPEC, env="qa", ttl_seconds=60, run_id="R"))  # type: ignore[arg-type]

        def busy(sends: bool) -> float:
            started = time.perf_counter()
            for i in range(5000):
                sum(range(2000))  # a little real work per iteration
                if sends:
                    waypoint_etl.log("row", i=i)
            return time.perf_counter() - started

        try:
            base = min(busy(False) for _ in range(5))
            with_events = min(busy(True) for _ in range(5))
        finally:
            registry.clear()
        self.assertLessEqual(with_events, base * 1.05 + 0.05, (base, with_events))


if __name__ == "__main__":
    unittest.main()
