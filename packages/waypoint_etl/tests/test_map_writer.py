"""The map writer: coalescing, batching, failing stores, flush, bounded footprint. Specs 014 R4, R5."""

import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout
from typing import Dict, List, Optional, Sequence, Tuple

from waypoint_etl.keys import (
    EVICT_TTL_SECONDS,
    MAP_DETAIL_LIMIT,
    MAP_EXTRA_FAILED_LIMIT,
    MAP_SLOWEST_KEPT,
)
from waypoint_etl.maps import MapTracker, MapWriter
from waypoint_etl.stores import NoopStepAuditStore

RUN = "20261017T020000Z"
STEPS = ("fetch", "transform", "load")
AGG_KEY = f"waypoint:demo:qa:{RUN}:map:accounts"


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Store:
    """Keeps the newest ttl and record of each key, and every batch it was given."""

    def __init__(self) -> None:
        self.batches: List[List[Tuple[str, Dict[str, object]]]] = []
        self.ttls: List[int] = []
        self.live: Dict[str, Tuple[Dict[str, object], int]] = {}
        self.fail = False
        self.hang = threading.Event()
        self.hang.set()

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.write_many([(key, record)], ttl_seconds)

    def write_many(self, items: Sequence[Tuple[str, Dict[str, object]]], ttl_seconds: int) -> None:
        self.hang.wait()
        if self.fail:
            raise ConnectionError("redis down")
        self.batches.append(list(items))
        self.ttls.append(ttl_seconds)
        for key, record in items:
            self.live[key] = (record, ttl_seconds)

    def item_keys(self, long_lived: bool = True) -> List[str]:
        return [
            k
            for k, (_, ttl) in self.live.items()
            if ":item:" in k and (ttl > EVICT_TTL_SECONDS or not long_lived)
        ]


class WriteOnlyStore:
    """A store with only ``write``."""

    def __init__(self) -> None:
        self.records: List[Tuple[str, Dict[str, object], int]] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.records.append((key, record, ttl_seconds))


def tracker(clock: Optional[Clock] = None) -> MapTracker:
    return MapTracker("demo", "qa", RUN, "accounts", 4, STEPS, lambda k, t: None, clock or Clock())


def writer(store: object, t: MapTracker, flush_every: float = 0.05) -> MapWriter:
    return MapWriter(store, t, 3600, flush_every=flush_every)  # type: ignore[arg-type]


def one_item(
    t: MapTracker, clock: Clock, key: str, seconds: float = 1.0, fail: bool = False
) -> None:
    item = t.start_item(key)
    assert item is not None
    seq = t.begin_inner(item, "fetch")
    clock.now += seconds
    if fail:
        t.fail_inner(item, "fetch", seq, {"type": "ValueError", "message": "bad", "traceback": "t"})
    else:
        t.finish_inner(item, "fetch", seq, {"rows": 2}, 2)
    t.end_item(item, None)


class TestMapWriter(unittest.TestCase):
    def test_a_change_writes_the_item_and_the_aggregate_with_the_runs_ttl(self) -> None:
        store, t = Store(), tracker()
        w = writer(store, t)
        t.start_item("acct-1")
        w.notify()
        w.flush()
        self.assertIn(f"waypoint:demo:qa:{RUN}:item:accounts:acct-1", store.live)
        self.assertIn(AGG_KEY, store.live)
        self.assertEqual({ttl for _, ttl in store.live.values()}, {3600})
        w.stop()

    def test_the_block_start_alone_writes_the_aggregate(self) -> None:
        store, t = Store(), tracker()
        w = writer(store, t)
        w.notify()
        w.flush()
        record, _ = store.live[AGG_KEY]
        self.assertEqual(record["counts"], {"started": 0, "running": 0, "done": 0, "failed": 0})
        self.assertIsNone(record["ended_at"])
        w.stop()

    def test_a_thousand_changes_in_one_interval_are_one_batch(self) -> None:
        store, clock = Store(), Clock()
        t = tracker(clock)
        w = writer(store, t, flush_every=0.3)
        for n in range(1000):
            one_item(t, clock, f"k{n}")
            w.notify()
        w.flush()
        self.assertLess(len(store.batches), 6)
        self.assertEqual(len(store.item_keys()), 1000)
        record, _ = store.live[AGG_KEY]
        self.assertEqual(record["counts"]["done"], 1000)  # type: ignore[index]
        w.stop()

    def test_every_batch_ends_with_the_aggregate(self) -> None:
        store, clock = Store(), Clock()
        t = tracker(clock)
        w = writer(store, t)
        one_item(t, clock, "a")
        w.notify()
        w.flush()
        self.assertEqual(store.batches[-1][-1][0], AGG_KEY)
        one_item(t, clock, "b")
        w.notify()
        w.flush()
        self.assertEqual(store.batches[-1][-1][0], AGG_KEY)
        w.stop()

    def test_nothing_is_written_again_when_nothing_changed(self) -> None:
        store, t = Store(), tracker()
        w = writer(store, t)
        t.start_item("a")
        w.notify()
        w.flush()
        count = len(store.batches)
        w.flush()
        time.sleep(0.15)
        self.assertEqual(len(store.batches), count)
        w.stop()

    def test_notify_never_blocks_when_the_store_hangs(self) -> None:
        store, clock = Store(), Clock()
        store.hang.clear()
        t = tracker(clock)
        w = writer(store, t)
        began = time.monotonic()
        for n in range(1000):
            one_item(t, clock, f"k{n}")
            w.notify()
        self.assertLess(time.monotonic() - began, 1.0)
        began = time.monotonic()
        w.stop(timeout=0.3)
        self.assertLess(time.monotonic() - began, 1.5)
        store.hang.set()

    def test_a_failing_store_is_logged_once_and_the_next_change_is_written_in_full(self) -> None:
        store, clock = Store(), Clock()
        store.fail = True
        t = tracker(clock)
        w = writer(store, t)
        out = io.StringIO()
        with redirect_stdout(out):
            for n in range(3):
                one_item(t, clock, f"k{n}")
                w.notify()
                w.flush()
        self.assertEqual(out.getvalue().count("map records not written"), 1)
        store.fail = False
        item = t.start_item("later")
        assert item is not None
        w.notify()
        w.flush()
        self.assertIn(f"waypoint:demo:qa:{RUN}:item:accounts:later", store.live)
        record, _ = store.live[AGG_KEY]
        self.assertEqual(record["counts"]["started"], 4)  # type: ignore[index]
        w.stop()

    def test_a_store_without_write_many_is_written_record_by_record(self) -> None:
        store, clock = WriteOnlyStore(), Clock()
        t = tracker(clock)
        w = writer(store, t)
        one_item(t, clock, "a")
        one_item(t, clock, "b")
        w.notify()
        w.flush()
        keys = [k for k, _, _ in store.records]
        self.assertEqual(keys[-1], AGG_KEY)
        self.assertEqual(len([k for k in keys if ":item:" in k]), 2)
        w.stop()

    def test_the_noop_store_takes_a_batch(self) -> None:
        t = tracker()
        w = writer(NoopStepAuditStore(), t)
        t.start_item("a")
        w.notify()
        w.flush()
        w.stop()

    def test_stop_delivers_and_is_safe_twice(self) -> None:
        store, t = Store(), tracker()
        w = writer(store, t, flush_every=5.0)  # a long interval: stop must not wait it out
        t.start_item("a")
        w.notify()
        began = time.monotonic()
        w.stop()
        self.assertLess(time.monotonic() - began, 2.5)
        self.assertIn(AGG_KEY, store.live)
        w.stop()
        w.notify()  # after stop: ignored

    def test_the_thread_is_a_daemon_and_starts_on_first_notify(self) -> None:
        store, t = Store(), tracker()
        w = writer(store, t)
        self.assertIsNone(w._thread)
        w.notify()
        assert w._thread is not None
        self.assertTrue(w._thread.daemon)
        w.stop()

    def test_displaced_slow_records_are_rewritten_with_a_one_second_ttl(self) -> None:
        store, clock = Store(), Clock()
        t = tracker(clock)
        w = writer(store, t)
        for n in range(MAP_DETAIL_LIMIT):
            one_item(t, clock, f"k{n}")
        for n in range(MAP_SLOWEST_KEPT + 5):
            one_item(t, clock, f"s{n}", seconds=10.0 + n)
        w.notify()
        w.flush()
        long_lived = {k.rsplit(":", 1)[1] for k in store.item_keys()}
        for n in range(5):
            self.assertNotIn(f"s{n}", long_lived)
            self.assertEqual(
                store.live[f"waypoint:demo:qa:{RUN}:item:accounts:s{n}"][1], EVICT_TTL_SECONDS
            )
        self.assertEqual(len({k for k in long_lived if k.startswith("s")}), MAP_SLOWEST_KEPT)
        w.stop()


class TestBoundedFootprint(unittest.TestCase):
    def totals(self, store: Store) -> int:
        # what stays in Redis: a record rewritten with a one-second TTL is gone almost at once
        return sum(len(json.dumps(r)) for r, ttl in store.live.values() if ttl > EVICT_TTL_SECONDS)

    def test_ten_thousand_items_with_failures_and_rising_durations(self) -> None:
        store, clock = Store(), Clock()
        t = tracker(clock)
        w = writer(store, t)
        for n in range(10_000):
            one_item(t, clock, f"k{n}", seconds=1.0 + n / 100, fail=n % 20 == 0)
        w.notify()
        w.flush()
        live = store.item_keys()
        # 1,000 full + the failures after them (450, all below the extra limit) + the 50 slowest
        self.assertLessEqual(
            len(live), MAP_DETAIL_LIMIT + MAP_EXTRA_FAILED_LIMIT + MAP_SLOWEST_KEPT
        )
        self.assertEqual(len(live), 1000 + 450 + 50)
        aggregate, _ = store.live[AGG_KEY]
        self.assertLess(len(json.dumps(aggregate)), 4096)
        self.assertEqual(aggregate["counts"]["started"], 10_000)  # type: ignore[index]
        self.assertEqual(aggregate["counts"]["failed"], 500)  # type: ignore[index]
        self.assertEqual(aggregate["detail"]["kept"], 1500)  # type: ignore[index]
        self.assertLess(self.totals(store), 3_000_000)
        w.stop()

    def test_when_every_item_fails_records_stop_at_the_two_limits(self) -> None:
        store, clock = Store(), Clock()
        t = tracker(clock)
        w = writer(store, t)
        for n in range(10_000):
            one_item(t, clock, f"k{n}", fail=True)
        w.notify()
        w.flush()
        self.assertEqual(len(store.item_keys()), MAP_DETAIL_LIMIT + MAP_EXTRA_FAILED_LIMIT)
        aggregate, _ = store.live[AGG_KEY]
        self.assertEqual(aggregate["detail"]["failed_without_record"], 8000)  # type: ignore[index]
        self.assertEqual(aggregate["counts"]["failed"], 10_000)  # type: ignore[index]
        self.assertEqual(len(aggregate["failed_items"]), 20)  # type: ignore[arg-type]
        self.assertLess(self.totals(store), 4_000_000)
        w.stop()


if __name__ == "__main__":
    unittest.main()
