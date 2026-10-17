"""The metric writer: coalescing, never blocking, failing stores, flush. Specs 013 R2."""

import io
import threading
import time
import unittest
from contextlib import redirect_stdout
from typing import Dict, List, Tuple

from waypoint_etl.metrics import MetricState, MetricWriter
from waypoint_etl.stores import NoopStepAuditStore


class Store:
    def __init__(self) -> None:
        self.records: List[Tuple[str, Dict[str, object], int]] = []
        self.fail = False
        self.hang = threading.Event()

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.hang.wait()
        if self.fail:
            raise ConnectionError("redis down")
        self.records.append((key, record, ttl_seconds))


def writer(store: object, flush_every: float = 0.05) -> Tuple[MetricState, MetricWriter]:
    state = MetricState()
    return state, MetricWriter(
        store,  # type: ignore[arg-type]
        state,
        "demo",
        "qa",
        "20261017T020000Z",
        3600,
        flush_every=flush_every,
    )


class TestMetricWriter(unittest.TestCase):
    def test_a_change_is_written_with_the_full_record_and_ttl(self) -> None:
        store = Store()
        store.hang.set()
        state, w = writer(store)
        state.apply((2, "load"), "rows", 5, "set")
        w.notify()
        w.flush()
        self.assertEqual(len(store.records), 1)
        key, record, ttl = store.records[0]
        self.assertEqual(key, "waypoint:demo:qa:20261017T020000Z:metrics:02-load")
        self.assertEqual(record["metrics"], {"rows": 5})
        self.assertEqual(record["index"], 2)
        self.assertEqual(ttl, 3600)
        w.stop()

    def test_many_calls_are_merged_into_few_writes(self) -> None:
        store = Store()
        store.hang.set()
        state, w = writer(store, flush_every=0.2)
        for _ in range(1000):
            state.apply((1, "s"), "n", 1, "add")
            w.notify()
        w.flush()
        self.assertLess(len(store.records), 6)
        self.assertEqual(store.records[-1][1]["metrics"], {"n": 1000})
        w.stop()

    def test_notify_never_blocks_when_the_store_hangs(self) -> None:
        store = Store()  # hang is not set: write blocks
        state, w = writer(store)
        began = time.monotonic()
        for _ in range(1000):
            state.apply((1, "s"), "n", 1, "add")
            w.notify()
        self.assertLess(time.monotonic() - began, 0.5)
        began = time.monotonic()
        w.stop(timeout=0.3)  # bounded even though the write is stuck
        self.assertLess(time.monotonic() - began, 1.5)
        store.hang.set()

    def test_failing_store_logs_once_and_recovers(self) -> None:
        store = Store()
        store.hang.set()
        store.fail = True
        state, w = writer(store)
        out = io.StringIO()
        with redirect_stdout(out):
            for _ in range(3):
                state.apply((1, "s"), "n", 1, "add")
                w.notify()
                w.flush()
        self.assertEqual(out.getvalue().count("metrics not written"), 1)
        self.assertEqual(store.records, [])
        store.fail = False
        state.apply((1, "s"), "n", 1, "add")
        w.notify()
        w.flush()
        self.assertEqual(store.records[-1][1]["metrics"], {"n": 4})  # the full state, not a delta
        w.stop()

    def test_stop_delivers_pending_values_and_is_repeatable(self) -> None:
        store = Store()
        store.hang.set()
        state, w = writer(store, flush_every=5.0)
        state.apply((1, "s"), "n", 3, "set")
        w.notify()
        w.stop()
        w.stop()
        self.assertEqual(store.records[-1][1]["metrics"], {"n": 3})

    def test_a_store_without_metrics_support_is_fine(self) -> None:
        state, w = writer(NoopStepAuditStore())
        state.apply((1, "s"), "n", 1, "set")
        w.notify()
        w.stop()


if __name__ == "__main__":
    unittest.main()
