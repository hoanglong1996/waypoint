"""Map step tracking: keys, histogram, counters, retention. Specs 014 data-model.md, research R5, R9, R10."""

import math
import unittest
from typing import Dict, List, Optional, Tuple

from waypoint_etl.keys import (
    EVICT_TTL_SECONDS,
    MAP_DETAIL_LIMIT,
    MAP_EXTRA_FAILED_LIMIT,
    MAP_SLOWEST_KEPT,
    item_key,
    map_key,
)
from waypoint_etl.maps import (
    ItemState,
    MapTracker,
    bucket,
    bucket_value,
    cut_traceback,
    sanitise_key,
)

STEPS = ("fetch", "transform", "load")


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def make(
    declared: Tuple[str, ...] = STEPS, clock: Optional[Clock] = None
) -> Tuple[MapTracker, Clock, List[str]]:
    clock = clock or Clock()
    warnings: List[str] = []
    tracker = MapTracker(
        "demo",
        "qa",
        "20261017T020000Z",
        "accounts",
        4,
        declared,
        lambda key, text: warnings.append(key),
        clock,
    )
    return tracker, clock, warnings


def agg(tracker: MapTracker) -> Dict[str, object]:
    found = tracker.take_dirty()[2]
    assert found is not None
    return found


def run_item(
    tracker: MapTracker,
    clock: Clock,
    key: str,
    seconds: float = 1.0,
    fail_at: Optional[str] = None,
    inputs: int = 5,
    output: int = 5,
) -> Optional[ItemState]:
    """One pass through fetch, transform and load, failing at ``fail_at`` when given."""
    item = tracker.start_item(key)
    if item is None:
        return None
    for position, step in enumerate(STEPS):
        seq = tracker.begin_inner(item, step)
        clock.tick(seconds / len(STEPS))
        if step == fail_at:
            tracker.fail_inner(
                item, step, seq, {"type": "ValueError", "message": "bad", "traceback": "tb"}
            )
            break
        tracker.finish_inner(item, step, seq, {"rows": inputs if position == 0 else output}, output)
    tracker.end_item(item, None)
    return item


class TestSanitiseKey(unittest.TestCase):
    def test_a_valid_key_is_unchanged(self) -> None:
        self.assertEqual(sanitise_key("acct-7", 1), ("acct-7", False))
        self.assertEqual(
            sanitise_key("customer_00012345.part-0007", 1), ("customer_00012345.part-0007", False)
        )

    def test_other_characters_become_underscores(self) -> None:
        self.assertEqual(sanitise_key("a b@c", 3), ("a_b_c", True))
        self.assertEqual(sanitise_key("acct:7", 3), ("acct_7", True))
        self.assertEqual(sanitise_key("é/ü", 3), ("___", True))

    def test_a_long_key_is_cut_to_64(self) -> None:
        key, changed = sanitise_key("k" * 100, 1)
        self.assertEqual((len(key), changed), (64, True))

    def test_empty_and_non_text_keys_use_the_arrival_number(self) -> None:
        self.assertEqual(sanitise_key("", 9), ("item_9", True))
        self.assertEqual(sanitise_key(None, 10), ("item_10", True))
        self.assertEqual(sanitise_key(42, 11), ("item_11", True))


class TestHistogram(unittest.TestCase):
    def test_buckets(self) -> None:
        self.assertEqual(bucket(0), 0)
        self.assertEqual(bucket(0.4), 0)
        self.assertEqual(bucket(1), 0)
        self.assertEqual(bucket(1000), int(math.floor(math.log(1000) / math.log(1.1))))
        self.assertLess(bucket(5), bucket(50))

    def test_a_bucket_value_is_within_five_percent(self) -> None:
        for ms in (1, 2, 3, 17, 250, 3900, 9100, 61_000, 86_400_000):
            self.assertAlmostEqual(bucket_value(bucket(ms)) / ms, 1.0, delta=0.05, msg=str(ms))

    def test_a_day_fits_in_about_190_buckets(self) -> None:
        self.assertLess(bucket(86_400_000), 200)


class TestCutTraceback(unittest.TestCase):
    def test_short_text_is_unchanged(self) -> None:
        self.assertEqual(cut_traceback("abc"), "abc")

    def test_long_text_keeps_the_last_frames_within_the_limit(self) -> None:
        text = "".join(f"frame {i}\n" for i in range(2000))
        cut = cut_traceback(text)
        self.assertLessEqual(len(cut.encode("utf-8")), 2048)
        self.assertTrue(cut.startswith("... (earlier frames omitted)\n"))
        self.assertTrue(cut.endswith("frame 1999\n"))


class TestCounters(unittest.TestCase):
    def test_counts_follow_the_items(self) -> None:
        tracker, clock, _ = make()
        a = tracker.start_item("a")
        tracker.start_item("b")
        self.assertEqual(
            agg(tracker)["counts"], {"started": 2, "running": 2, "done": 0, "failed": 0}
        )
        assert a is not None
        tracker.end_item(a, None)
        run_item(tracker, clock, "c", fail_at="transform")
        counts = agg(tracker)["counts"]
        self.assertEqual(counts, {"started": 3, "running": 1, "done": 1, "failed": 1})

    def test_started_always_equals_running_done_failed(self) -> None:
        tracker, clock, _ = make()
        for n in range(30):
            run_item(tracker, clock, f"k{n}", fail_at="load" if n % 4 == 0 else None)
            tracker.start_item(f"open{n}")
        counts = agg(tracker)["counts"]
        assert isinstance(counts, dict)
        self.assertEqual(counts["started"], counts["running"] + counts["done"] + counts["failed"])
        self.assertEqual(counts["started"], 60)

    def test_an_inner_step_that_failed_makes_the_item_failed(self) -> None:
        tracker, clock, _ = make()
        item = run_item(tracker, clock, "acct-7", fail_at="transform")
        assert item is not None
        self.assertEqual(item.state, "failed")
        record = tracker._item_record(item, compact=False)
        steps = record["steps"]
        assert isinstance(steps, list)
        self.assertEqual([s["state"] for s in steps], ["done", "failed"])  # load never began
        self.assertEqual(steps[1]["error"]["type"], "ValueError")

    def test_a_later_successful_attempt_replaces_a_failed_one(self) -> None:
        tracker, clock, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        first = tracker.begin_inner(item, "fetch")
        tracker.fail_inner(item, "fetch", first, {"type": "OSError", "traceback": "t"})
        second = tracker.begin_inner(item, "fetch")
        tracker.finish_inner(item, "fetch", second, {"x": 1}, 4)
        tracker.end_item(item, None)
        self.assertEqual(item.state, "done")
        inner = agg(tracker)["inner"]
        assert isinstance(inner, dict)
        self.assertEqual(inner["fetch"], {"running": 0, "done": 1, "failed": 0, "in": 1, "out": 4})
        record = tracker._item_record(item, compact=False)
        steps = record["steps"]
        assert isinstance(steps, list)
        self.assertEqual((len(steps), steps[0]["attempt"], steps[0]["state"]), (1, 2, "done"))

    def test_an_item_level_error_fails_an_item_without_a_failed_step(self) -> None:
        tracker, clock, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        seq = tracker.begin_inner(item, "fetch")
        tracker.finish_inner(item, "fetch", seq, {}, 1)
        tracker.end_item(item, {"type": "KeyError", "message": "x", "traceback": "t"})
        self.assertEqual(item.state, "failed")
        record = tracker._item_record(item, compact=False)
        self.assertEqual(record["error"], {"type": "KeyError", "message": "x", "traceback": "t"})
        listed = agg(tracker)["failed_items"]
        self.assertEqual(listed, [{"key": "a", "step": "fetch", "error_type": "KeyError"}])

    def test_a_stale_sequence_number_is_ignored(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        old = tracker.begin_inner(item, "fetch")
        tracker.begin_inner(item, "fetch")  # a retry began
        tracker.finish_inner(item, "fetch", old, {}, 1)  # the first attempt finishing late
        self.assertEqual(item.results["fetch"].state, "running")
        tracker.finish_inner(item, "fetch", 0, {}, 1)  # a dropped step (sequence 0)
        self.assertEqual(item.results["fetch"].state, "running")

    def test_calls_after_an_item_ended_change_nothing(self) -> None:
        tracker, clock, _ = make()
        item = run_item(tracker, clock, "a")
        assert item is not None
        before = agg(tracker)
        self.assertEqual(tracker.begin_inner(item, "fetch"), 0)
        tracker.end_item(item, {"type": "X", "traceback": ""})
        self.assertEqual(item.state, "done")
        self.assertFalse(tracker.has_dirty())  # nothing changed
        self.assertEqual(before["counts"], {"started": 1, "running": 0, "done": 1, "failed": 0})

    def test_inner_counts_across_items(self) -> None:
        tracker, clock, _ = make()
        run_item(tracker, clock, "a")
        run_item(tracker, clock, "b", fail_at="transform")
        c = tracker.start_item("c")
        assert c is not None
        tracker.begin_inner(c, "fetch")
        inner = agg(tracker)["inner"]
        assert isinstance(inner, dict)
        self.assertEqual(list(inner), ["fetch", "transform", "load"])
        self.assertEqual(
            inner["fetch"], {"running": 1, "done": 2, "failed": 0, "in": 10, "out": 10}
        )
        self.assertEqual(inner["transform"]["failed"], 1)
        self.assertEqual(inner["load"], {"running": 0, "done": 1, "failed": 0, "in": 5, "out": 5})

    def test_too_many_inner_steps_are_dropped_with_a_warning(self) -> None:
        tracker, _, warnings = make()
        item = tracker.start_item("a")
        assert item is not None
        for n in range(25):
            tracker.begin_inner(item, f"s{n}")
        self.assertEqual(len(item.results), 20)
        self.assertIn("inner:s20", warnings)

    def test_in_out_and_loss(self) -> None:
        tracker, clock, _ = make()
        run_item(tracker, clock, "ok", inputs=48, output=40)
        run_item(tracker, clock, "lost", inputs=48, output=0)
        found = agg(tracker)
        self.assertEqual(found["in_total"], 96)  # the first inner step's inputs
        self.assertEqual(
            found["out_total"], 40
        )  # the last inner step's output, 0 for the lost item
        self.assertEqual(found["lost_items"], 1)

    def test_loss_counts_an_item_once(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        for step in STEPS:
            seq = tracker.begin_inner(item, step)
            tracker.finish_inner(item, step, seq, {"rows": 3}, 0)
        tracker.end_item(item, None)
        self.assertEqual(agg(tracker)["lost_items"], 1)

    def test_a_failed_item_adds_no_output(self) -> None:
        tracker, clock, _ = make()
        run_item(tracker, clock, "a", fail_at="load", inputs=7)
        found = agg(tracker)
        self.assertEqual((found["in_total"], found["out_total"]), (7, 0))


class TestDuplicatesAndKeys(unittest.TestCase):
    def test_a_duplicate_key_is_refused_and_counted_once(self) -> None:
        tracker, clock, warnings = make()
        first = run_item(tracker, clock, "acct-1")
        self.assertIsNotNone(first)
        self.assertIsNone(tracker.start_item("acct-1"))
        self.assertIn("dup:acct-1", warnings)
        self.assertEqual(
            agg(tracker)["counts"], {"started": 1, "running": 0, "done": 1, "failed": 0}
        )

    def test_a_key_that_collides_after_sanitising_is_a_duplicate(self) -> None:
        tracker, _, _ = make()
        self.assertIsNotNone(tracker.start_item("a b"))
        self.assertIsNone(tracker.start_item("a_b"))

    def test_a_changed_key_warns(self) -> None:
        tracker, _, warnings = make()
        item = tracker.start_item("a b@c")
        assert item is not None
        self.assertEqual(item.key, "a_b_c")
        self.assertEqual(warnings, ["key:a b@c"])

    def test_an_empty_key_uses_the_arrival_number(self) -> None:
        tracker, _, _ = make()
        tracker.start_item("x")
        item = tracker.start_item("")
        assert item is not None
        self.assertEqual((item.key, item.arrival), ("item_2", 2))

    def test_refused_duplicates_do_not_use_an_arrival_number(self) -> None:
        tracker, _, _ = make()
        tracker.start_item("a")
        tracker.start_item("a")
        third = tracker.start_item("b")
        assert third is not None
        self.assertEqual(third.arrival, 2)


class TestDurations(unittest.TestCase):
    def test_histogram_sum_slowest_and_failures(self) -> None:
        tracker, clock, _ = make()
        for n in range(8):
            run_item(
                tracker, clock, f"k{n}", seconds=float(n + 1), fail_at="load" if n == 6 else None
            )
        duration = agg(tracker)["duration"]
        assert isinstance(duration, dict)
        self.assertEqual(duration["count"], 8)
        self.assertEqual(duration["sum_ms"], sum((n + 1) * 1000 for n in range(8)))
        hist = duration["hist"]
        self.assertEqual(sum(hist.values()), 8)
        self.assertTrue(all(isinstance(k, str) for k in hist))
        self.assertEqual(
            [s["key"] for s in duration["slowest"]], ["k7", "k6", "k5", "k4", "k3"]
        )  # exact, slowest first, at most 5
        self.assertEqual(duration["slowest"][0], {"key": "k7", "ms": 8000})

    def test_only_the_first_twenty_failures_are_listed(self) -> None:
        tracker, clock, _ = make()
        for n in range(30):
            run_item(tracker, clock, f"f{n}", fail_at="fetch")
        found = agg(tracker)
        listed = found["failed_items"]
        assert isinstance(listed, list)
        self.assertEqual([f["key"] for f in listed], [f"f{n}" for n in range(20)])
        self.assertEqual(listed[0], {"key": "f0", "step": "fetch", "error_type": "ValueError"})
        self.assertEqual(found["counts"]["failed"], 30)  # type: ignore[index]


class TestMetricsInItems(unittest.TestCase):
    def test_metrics_merge_per_inner_step_into_the_item_record(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        tracker.begin_inner(item, "transform")
        for value in (1, 2, 3):
            self.assertIsNone(tracker.record_metric(item, "transform", "rejected", value, "add"))
        tracker.record_metric(item, "transform", "peak", 5, "max")
        tracker.record_metric(item, "transform", "peak", 9, "max")
        tracker.record_metric(item, "transform", "peak", 7, "max")
        tracker.record_metric(item, "transform", "rows", 10, "set")
        tracker.record_metric(item, "transform", "rows", 4, "set")
        record = tracker._item_record(item, compact=False)
        self.assertEqual(record["metrics"], {"transform": {"rejected": 6, "peak": 9, "rows": 4}})

    def test_a_retry_shows_only_the_latest_attempts_metrics(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        tracker.begin_inner(item, "fetch")
        tracker.record_metric(item, "fetch", "n", 5, "set")
        tracker.begin_inner(item, "fetch")
        tracker.record_metric(item, "fetch", "m", 1, "set")
        record = tracker._item_record(item, compact=False)
        self.assertEqual(record["metrics"], {"fetch": {"m": 1}})

    def test_reasons_for_dropped_calls(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        self.assertEqual(tracker.record_metric(item, "fetch", "n", 1, "set"), "step")
        tracker.begin_inner(item, "fetch")
        self.assertEqual(tracker.record_metric(item, "fetch", "Bad", 1, "set"), "name")
        self.assertEqual(tracker.record_metric(item, "fetch", "n", True, "set"), "value")  # type: ignore[arg-type]
        self.assertEqual(tracker.record_metric(item, "fetch", "n", 1, "avg"), "mode")
        for n in range(20):
            tracker.record_metric(item, "fetch", f"m{n}", 1, "set")
        self.assertEqual(tracker.record_metric(item, "fetch", "extra", 1, "set"), "limit")

    def test_no_metrics_key_without_metrics_and_none_in_a_compact_record(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        tracker.begin_inner(item, "fetch")
        self.assertNotIn("metrics", tracker._item_record(item, compact=False))
        tracker.record_metric(item, "fetch", "n", 1, "set")
        self.assertNotIn("metrics", tracker._item_record(item, compact=True))


class TestRecordShapes(unittest.TestCase):
    def test_the_aggregate_shape(self) -> None:
        tracker, clock, _ = make()
        run_item(tracker, clock, "a", seconds=3.0)
        found = agg(tracker)
        self.assertEqual(
            sorted(found),
            sorted(
                [
                    "v",
                    "pipeline",
                    "env",
                    "run_id",
                    "map",
                    "index",
                    "started_at",
                    "ended_at",
                    "updated_at",
                    "counts",
                    "in_total",
                    "out_total",
                    "lost_items",
                    "inner",
                    "duration",
                    "failed_items",
                    "detail",
                ]
            ),
        )
        self.assertEqual((found["v"], found["map"], found["index"]), (1, "accounts", 4))
        self.assertIsNone(found["ended_at"])
        self.assertEqual(
            found["detail"],
            {
                "limit": 1000,
                "kept": 1,
                "extra_failed_limit": 1000,
                "failed_without_record": 0,
                "slow_kept": 0,
            },
        )
        tracker.end_block()
        self.assertIsNotNone(agg(tracker)["ended_at"])

    def test_the_item_record_shape(self) -> None:
        tracker, clock, _ = make()
        item = run_item(tracker, clock, "acct-7", seconds=3.0, fail_at="transform")
        assert item is not None
        writes, evictions, aggregate = tracker.take_dirty()
        self.assertEqual(evictions, [])
        self.assertIsNotNone(aggregate)
        ((key, record),) = writes
        self.assertEqual(key, "waypoint:demo:qa:20261017T020000Z:item:accounts:acct-7")
        self.assertEqual(
            (record["v"], record["map"], record["key"], record["index"], record["state"]),
            (1, "accounts", "acct-7", 1, "failed"),
        )
        self.assertEqual(record["duration_ms"], 2000)
        self.assertIn("finished_at", record)
        self.assertNotIn("compact", record)
        self.assertEqual(
            tracker.aggregate_key(), map_key("demo", "qa", "20261017T020000Z", "accounts")
        )

    def test_a_running_item_has_no_finish_fields(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        tracker.begin_inner(item, "fetch")
        record = tracker._item_record(item, compact=False)
        self.assertEqual(record["state"], "running")
        self.assertNotIn("finished_at", record)
        self.assertNotIn("duration_ms", record)
        step = record["steps"][0]  # type: ignore[index]
        self.assertEqual((step["state"], step["inputs"], step["output"]), ("running", {}, None))

    def test_a_full_records_trace_is_cut_to_2048_bytes(self) -> None:
        tracker, _, _ = make()
        item = tracker.start_item("a")
        assert item is not None
        seq = tracker.begin_inner(item, "fetch")
        trace = "".join(f"frame {i}\n" for i in range(3000))
        tracker.fail_inner(
            item, "fetch", seq, {"type": "E", "message": "m" * 500, "traceback": trace}
        )
        tracker.end_item(item, None)
        record = tracker._item_record(item, compact=False)
        error = record["steps"][0]["error"]  # type: ignore[index]
        self.assertLessEqual(len(error["traceback"].encode("utf-8")), 2048)
        self.assertTrue(error["traceback"].endswith("frame 2999\n"))
        self.assertEqual(len(error["message"]), 500)

    def test_writes_clear_the_dirty_marks(self) -> None:
        tracker, _, _ = make()
        tracker.start_item("a")
        self.assertTrue(tracker.has_dirty())
        tracker.take_dirty()
        self.assertFalse(tracker.has_dirty())
        self.assertEqual(tracker.take_dirty(), ([], [], None))


class TestRetention(unittest.TestCase):
    """Research R5: 1,000 full records, 1,000 further failed (compact), the 50 slowest later ones."""

    def fill(self, tracker: MapTracker, clock: Clock, n: int, prefix: str = "k") -> None:
        for i in range(n):
            run_item(tracker, clock, f"{prefix}{i}", seconds=1.0)

    def test_the_first_thousand_keep_full_records(self) -> None:
        tracker, clock, _ = make()
        self.fill(tracker, clock, MAP_DETAIL_LIMIT)
        writes, evictions, aggregate = tracker.take_dirty()
        self.assertEqual(len(writes), 1000)
        self.assertTrue(all("compact" not in r for _, r in writes))
        assert aggregate is not None
        self.assertEqual(aggregate["detail"]["kept"], 1000)  # type: ignore[index]

    def test_later_items_leave_only_the_aggregate(self) -> None:
        tracker, clock, _ = make()
        self.fill(tracker, clock, MAP_DETAIL_LIMIT)
        tracker.take_dirty()
        self.fill(tracker, clock, 200, "later")  # all equally fast: the first 50 become "slowest"
        writes, _, aggregate = tracker.take_dirty()
        assert aggregate is not None
        self.assertEqual(aggregate["counts"]["started"], 1200)  # type: ignore[index]
        self.assertEqual(len(writes), MAP_SLOWEST_KEPT)  # nothing else was kept
        self.assertEqual(aggregate["detail"]["kept"], 1050)  # type: ignore[index]

    def test_a_later_failed_item_keeps_a_compact_record(self) -> None:
        tracker, clock, _ = make()
        self.fill(tracker, clock, MAP_DETAIL_LIMIT)
        tracker.take_dirty()
        item = tracker.start_item("bad")
        assert item is not None
        seq = tracker.begin_inner(item, "fetch")
        tracker.record_metric(item, "fetch", "n", 3, "set")  # dropped: no record of its own
        tracker.fail_inner(
            item,
            "fetch",
            seq,
            {"type": "ValueError", "message": "m" * 400, "traceback": "tb\n" * 50},
        )
        tracker.end_item(item, None)
        writes, _, _ = tracker.take_dirty()
        ((key, record),) = writes
        self.assertEqual(key, item_key("demo", "qa", "20261017T020000Z", "accounts", "bad"))
        self.assertTrue(record["compact"])
        self.assertNotIn("metrics", record)
        error = record["steps"][0]["error"]  # type: ignore[index]
        self.assertEqual(error["traceback"], "")
        self.assertEqual(len(error["message"]), 200)
        self.assertEqual(error["type"], "ValueError")

    def test_a_running_item_beyond_the_limit_is_not_written(self) -> None:
        tracker, clock, _ = make()
        self.fill(tracker, clock, MAP_DETAIL_LIMIT)
        tracker.take_dirty()
        item = tracker.start_item("late")
        assert item is not None
        tracker.begin_inner(item, "fetch")
        writes, _, aggregate = tracker.take_dirty()
        self.assertEqual(writes, [])
        assert aggregate is not None
        self.assertEqual(aggregate["counts"]["running"], 1)  # type: ignore[index]

    def test_failures_beyond_the_extra_limit_are_only_counted(self) -> None:
        tracker, clock, _ = make()
        self.fill(tracker, clock, MAP_DETAIL_LIMIT)
        tracker.take_dirty()
        for i in range(MAP_EXTRA_FAILED_LIMIT + 37):
            run_item(tracker, clock, f"x{i}", fail_at="fetch")
        writes, _, aggregate = tracker.take_dirty()
        assert aggregate is not None
        self.assertEqual(len(writes), MAP_EXTRA_FAILED_LIMIT)
        detail = aggregate["detail"]
        self.assertEqual(detail["failed_without_record"], 37)  # type: ignore[index]
        self.assertEqual(aggregate["counts"]["failed"], MAP_EXTRA_FAILED_LIMIT + 37)  # type: ignore[index]
        self.assertEqual(
            detail["kept"], MAP_DETAIL_LIMIT + MAP_EXTRA_FAILED_LIMIT  # type: ignore[index]
        )

    def test_the_slowest_later_items_are_kept_and_displaced_ones_retired(self) -> None:
        tracker, clock, _ = make()
        self.fill(tracker, clock, MAP_DETAIL_LIMIT)
        tracker.take_dirty()
        durations = [
            10.0 + i for i in range(60)
        ]  # each later item is slower than every earlier one
        for i, seconds in enumerate(durations):
            run_item(tracker, clock, f"s{i}", seconds=seconds)
        writes, evictions, aggregate = tracker.take_dirty()
        assert aggregate is not None
        written = {k.rsplit(":", 1)[1] for k, _ in writes}
        retired = {k.rsplit(":", 1)[1] for k, _ in evictions}
        # the ten fastest were displaced by slower ones; a displaced record is never also written
        self.assertEqual(retired, {f"s{i}" for i in range(10)})
        self.assertEqual(written, {f"s{i}" for i in range(10, 60)})
        self.assertEqual(aggregate["detail"]["slow_kept"], 50)  # type: ignore[index]
        self.assertTrue(all(r.get("compact") for _, r in evictions))
        self.assertEqual(aggregate["counts"]["done"], 1060)  # type: ignore[index]

    def test_a_faster_item_does_not_displace_a_slow_one(self) -> None:
        tracker, clock, _ = make()
        self.fill(tracker, clock, MAP_DETAIL_LIMIT)
        for i in range(MAP_SLOWEST_KEPT):
            run_item(tracker, clock, f"s{i}", seconds=50.0)
        tracker.take_dirty()
        run_item(tracker, clock, "quick", seconds=1.0)
        writes, evictions, _ = tracker.take_dirty()
        self.assertEqual((writes, evictions), ([], []))

    def test_the_eviction_ttl_is_one_second(self) -> None:
        self.assertEqual(EVICT_TTL_SECONDS, 1)

    def test_totals_cover_every_item_whatever_is_kept(self) -> None:
        tracker, clock, _ = make()
        for i in range(1300):
            run_item(tracker, clock, f"k{i}", seconds=1.0, inputs=2, output=2)
        found = agg(tracker)
        self.assertEqual(found["in_total"], 2600)
        self.assertEqual(found["out_total"], 2600)
        self.assertEqual(found["duration"]["count"], 1300)  # type: ignore[index]
        self.assertEqual(sum(found["duration"]["hist"].values()), 1300)  # type: ignore[index]
        self.assertEqual(found["inner"]["load"]["done"], 1300)  # type: ignore[index]
        self.assertEqual(found["lost_items"], 0)

    def test_memory_holds_only_detailed_and_running_items(self) -> None:
        tracker, clock, _ = make()
        for i in range(1500):
            run_item(tracker, clock, f"k{i}", seconds=1.0)
        self.assertEqual(len(tracker._items), MAP_DETAIL_LIMIT)


if __name__ == "__main__":
    unittest.main()
