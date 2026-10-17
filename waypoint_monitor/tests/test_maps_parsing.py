"""Parsing and validating map aggregates and item records (specs/014 contracts/redis-keys.md)."""

import json
import unittest
from typing import Any, List, Tuple

from app.domain import parsing
from app.domain.parsing import (
    parse_events,
    parse_items,
    parse_maps,
    pipeline_of_key,
)
from tests.fakes import FakeStore, item_steps, make_aggregate, make_item

R1 = "20261015T020000Z"
R2 = "20261014T020000Z"
Raw = List[Tuple[str, str]]


def agg(**kw: Any) -> Tuple[str, str]:
    return make_aggregate("prod", kw.pop("run_id", R1), **kw)


def mutate(pair: Tuple[str, str], **changes: Any) -> Tuple[str, str]:
    value = json.loads(pair[1])
    for k, v in changes.items():
        if v is KeyError:
            value.pop(k, None)
        else:
            value[k] = v
    return pair[0], json.dumps(value)


class TestKeyIsolation(unittest.TestCase):
    """Research R3: no existing key pattern may match the new keys."""

    MAP_KEY = f"waypoint:callrail:prod:{R1}:map:accounts"
    ITEM_KEY = f"waypoint:callrail:prod:{R1}:item:accounts:acct-7"

    def test_existing_patterns_ignore_map_and_item_keys(self) -> None:
        patterns = [
            parsing._KEY,
            parsing._MARKER_KEY,
            parsing._FLOW_KEY,
            parsing._FAILED_KEY,
            parsing._EVENTS_KEY,
            parsing._METRICS_KEY,
            parsing._ALIVE_KEY,
            parsing._DIED_KEY,
        ]
        for key in (self.MAP_KEY, self.ITEM_KEY):
            for pattern in patterns:
                with self.subTest(key=key, pattern=pattern.pattern):
                    self.assertIsNone(pattern.match(key))

    def test_the_pipeline_is_still_found_from_either_key(self) -> None:
        self.assertEqual(pipeline_of_key("prod", self.MAP_KEY), "callrail")
        self.assertEqual(pipeline_of_key("prod", self.ITEM_KEY), "callrail")

    def test_the_other_lists_of_the_fake_store_never_return_them(self) -> None:
        store = FakeStore()
        store.maps.append(agg())
        store.items.append(make_item("prod", R1, "acct-7", 7))
        self.assertEqual(store.list_pipelines("prod"), ["callrail"])
        for call in (
            store.list_records,
            store.list_markers,
            store.list_failures,
            store.list_metrics,
            store.list_flows,
            store.list_alive,
            store.list_died,
        ):
            self.assertEqual(call("prod", "callrail"), [])
        self.assertEqual(len(store.list_maps("prod", "callrail")), 1)
        self.assertEqual(len(store.list_items("prod", "callrail", R1, "accounts")), 1)
        self.assertEqual(store.list_items("prod", "callrail", R1, "other"), [])


class TestParseMaps(unittest.TestCase):
    def test_a_valid_aggregate(self) -> None:
        pair = agg(
            running=4,
            done=5,
            failed=1,
            ended=False,
            durations_ms=[2000, 3900, 9120],
            slowest=[("acct-7", 9120)],
            inner={"fetch": {"running": 2, "done": 8, "failed": 0, "in": 10, "out": 480}},
            failed_items=[("acct-7", "transform", "ValueError")],
            failed_without_record=0,
            lost_items=1,
            in_total=480,
            out_total=455,
        )
        records, unreadable = parse_maps("prod", "callrail", [pair])
        self.assertEqual(unreadable, {})
        (a,) = records
        self.assertEqual((a.run_id, a.map, a.index), (R1, "accounts", 2))
        self.assertEqual(
            (a.counts.started, a.counts.running, a.counts.done, a.counts.failed), (10, 4, 5, 1)
        )
        self.assertIsNone(a.ended_at)
        self.assertEqual((a.in_total, a.out_total, a.lost_items), (480, 455, 1))
        self.assertEqual(a.inner[0].name, "fetch")
        self.assertEqual((a.inner[0].inputs_total, a.inner[0].output_total), (10, 480))
        self.assertEqual((a.count, a.sum_ms), (3, 15020))
        self.assertEqual(sum(a.hist.values()), 3)
        self.assertEqual(a.slowest, (("acct-7", 9120),))
        self.assertEqual(a.failed_items, (("acct-7", "transform", "ValueError"),))
        self.assertEqual((a.kept, a.failed_without_record), (10, 0))

    def test_an_ended_aggregate_has_its_end_time(self) -> None:
        (a,), _ = parse_maps("prod", "callrail", [agg(done=3)])
        self.assertIsNotNone(a.ended_at)

    def test_every_malformed_aggregate_is_unreadable_for_its_run_and_others_are_kept(self) -> None:
        good = agg(done=2, run_id=R2)
        base = agg(done=2)
        bad = {
            "version": mutate(base, v=2),
            "invalid json": (base[0], "{not json"),
            "not an object": (base[0], "[1]"),
            "started != sum": mutate(
                base, counts={"started": 5, "running": 1, "done": 2, "failed": 0}
            ),
            "negative count": mutate(
                base, counts={"started": 1, "running": -1, "done": 2, "failed": 0}
            ),
            "bool count": mutate(
                base, counts={"started": 3, "running": True, "done": 2, "failed": 0}
            ),
            "counts missing": mutate(base, counts=KeyError),
            "wrong run id": mutate(base, run_id=R2),
            "wrong env": mutate(base, env="qa"),
            "wrong pipeline": mutate(base, pipeline="other"),
            "wrong map": mutate(base, map="other"),
            "bad index": mutate(base, index=0),
            "no start": mutate(base, started_at=None),
            "hist key": mutate(
                base, duration={"count": 1, "sum_ms": 5, "hist": {"x": 1}, "slowest": []}
            ),
            "hist value": mutate(
                base, duration={"count": 1, "sum_ms": 5, "hist": {"3": -1}, "slowest": []}
            ),
            "six slowest": mutate(
                base,
                duration={
                    "count": 6,
                    "sum_ms": 6,
                    "hist": {"1": 6},
                    "slowest": [{"key": f"k{i}", "ms": 1} for i in range(6)],
                },
            ),
            "21 failed items": mutate(
                base,
                failed_items=[{"key": f"k{i}", "step": "s", "error_type": "E"} for i in range(21)],
            ),
            "21 inner steps": mutate(
                base,
                inner={
                    f"s{i}": {"running": 0, "done": 0, "failed": 0, "in": 0, "out": 0}
                    for i in range(21)
                },
            ),
            "bad slowest key": mutate(
                base,
                duration={
                    "count": 1,
                    "sum_ms": 5,
                    "hist": {},
                    "slowest": [{"key": "a b", "ms": 1}],
                },
            ),
        }
        for label, pair in bad.items():
            with self.subTest(label):
                records, unreadable = parse_maps("prod", "callrail", [pair, good])
                self.assertEqual([r.run_id for r in records], [R2], label)
                self.assertEqual(unreadable.get(R1, 0), 1, label)

    def test_wrong_typed_optional_fields_are_treated_as_absent(self) -> None:
        pair = mutate(agg(done=2), ended_at="yesterday", updated_at=7, lost_items="x")
        (a,), unreadable = parse_maps("prod", "callrail", [pair])
        self.assertEqual(unreadable, {})
        self.assertIsNone(a.ended_at)
        self.assertIsNone(a.updated_at)
        self.assertEqual(a.lost_items, 0)

    def test_keys_that_are_not_ours_are_ignored(self) -> None:
        pair = agg(done=1)
        other_env = ("waypoint:callrail:qa:" + R1 + ":map:accounts", pair[1])
        other_pipe = ("waypoint:other:prod:" + R1 + ":map:accounts", pair[1])
        not_map = (f"waypoint:callrail:prod:{R1}:step:01-a", pair[1])
        records, unreadable = parse_maps("prod", "callrail", [other_env, other_pipe, not_map])
        self.assertEqual((records, unreadable), ([], {}))


class TestParseItems(unittest.TestCase):
    def parse(self, *pairs: Tuple[str, str]) -> Tuple[Any, int]:
        return parse_items("prod", "callrail", R1, "accounts", list(pairs))

    def test_full_and_compact_records(self) -> None:
        full = make_item(
            "prod",
            R1,
            "acct-7",
            7,
            "failed",
            metrics={"transform": {"rejected": 4, "bad": True, "Bad Name": 1}},
        )
        compact = make_item(
            "prod",
            R1,
            "acct-9",
            9,
            "failed",
            compact=True,
            steps=[
                {
                    "step": "transform",
                    "attempt": 1,
                    "state": "failed",
                    "inputs": {"rows": 3},
                    "output": None,
                    "error": {"type": "ValueError", "message": "x" * 600},
                }
            ],
        )
        items, unreadable = self.parse(full, compact)
        self.assertEqual(unreadable, 0)
        a, b = items
        self.assertEqual((a.key, a.index, a.state, a.compact), ("acct-7", 7, "failed", False))
        self.assertEqual([s.step for s in a.steps], ["fetch", "transform"])
        self.assertEqual(a.steps[1].error.type, "ValueError")
        self.assertEqual(a.steps[0].inputs, {"account": 1})
        self.assertEqual(a.metrics, {"transform": {"rejected": 4}})  # bool and bad name dropped
        self.assertTrue(b.compact)
        self.assertEqual(b.steps[0].error.traceback, "")
        self.assertEqual(len(b.steps[0].error.message), 500)

    def test_a_running_item_has_no_end_or_duration(self) -> None:
        pair = make_item("prod", R1, "acct-1", 1, "running", steps=item_steps(running="fetch"))
        (item,), _ = self.parse(pair)
        self.assertIsNone(item.finished_at)
        self.assertIsNone(item.duration_ms)
        self.assertEqual(item.steps[0].state, "running")

    def test_a_long_traceback_is_cut_to_2048_bytes_keeping_the_last_frames(self) -> None:
        tail = "LAST FRAME\n"
        trace = "x" * 5000 + tail
        steps = item_steps(failed_at="transform")
        steps[1]["error"]["traceback"] = trace
        (item,), _ = self.parse(make_item("prod", R1, "acct-7", 7, "failed", steps=steps))
        cut = item.steps[1].error.traceback
        self.assertLessEqual(len(cut.encode()), 2048)
        self.assertTrue(cut.endswith(tail))
        self.assertIn("omitted", cut)

    def test_item_level_error_is_kept(self) -> None:
        pair = make_item(
            "prod", R1, "acct-2", 2, "failed", steps=[],
            error={"type": "KeyError", "message": "k", "traceback": "tb"},
        )  # fmt: skip
        (item,), _ = self.parse(pair)
        self.assertEqual(item.error.type, "KeyError")

    def test_malformed_records_are_unreadable_and_others_kept(self) -> None:
        good = make_item("prod", R1, "acct-1", 1)
        base = make_item("prod", R1, "acct-2", 2)
        key = base[0]
        too_many = [dict(item_steps()[0], step=f"s{i}") for i in range(21)]
        bad = {
            "version": mutate(base, v=2),
            "invalid json": (key, "{nope"),
            "not an object": (key, "3"),
            "wrong run": mutate(base, run_id=R2),
            "wrong env": mutate(base, env="qa"),
            "wrong pipeline": mutate(base, pipeline="x"),
            "wrong map": mutate(base, map="x"),
            "wrong key": mutate(base, key="acct-3"),
            "bad index": mutate(base, index=True),
            "bad state": mutate(base, state="skipped"),
            "no start": mutate(base, started_at="soon"),
            "21 steps": mutate(base, steps=too_many),
            "step state": mutate(base, steps=[dict(item_steps()[0], state="odd")]),
            "step count": mutate(base, steps=[dict(item_steps()[0], inputs={"a": -1})]),
            "steps not a list": mutate(base, steps="x"),
        }
        for label, pair in bad.items():
            with self.subTest(label):
                items, unreadable = self.parse(good, pair)
                self.assertEqual([i.key for i in items], ["acct-1"], label)
                self.assertEqual(unreadable, 1, label)

    def test_a_key_outside_the_allowed_set_is_not_an_item(self) -> None:
        bad_key = (
            f"waypoint:callrail:prod:{R1}:item:accounts:a b",
            make_item("prod", R1, "a b", 3)[1],
        )
        items, unreadable = self.parse(bad_key)
        self.assertEqual((items, unreadable), ([], 0))

    def test_wrong_typed_optional_fields_are_absent(self) -> None:
        pair = mutate(
            make_item("prod", R1, "acct-1", 1), finished_at="x", duration_ms="slow", compact="yes"
        )
        (item,), unreadable = self.parse(pair)
        self.assertEqual(unreadable, 0)
        self.assertIsNone(item.finished_at)
        self.assertIsNone(item.duration_ms)
        self.assertFalse(item.compact)

    def test_other_runs_maps_and_keys_are_ignored(self) -> None:
        same_run_other_map = make_item("prod", R1, "acct-1", 1, map_name="other")
        other_run = make_item("prod", R2, "acct-1", 1)
        step_key = (f"waypoint:callrail:prod:{R1}:step:01-a", "{}")
        self.assertEqual(self.parse(same_run_other_map, other_run, step_key), ([], 0))


class TestEventItemField(unittest.TestCase):
    def events(self, **fields: Any) -> Any:
        store = FakeStore()
        store.add_event(R1, "info", 1, "2026-10-15T02:00:01.000Z", "hi", step="fetch", **fields)
        raw = store.read_events("prod", "callrail", R1)
        return parse_events("prod", "callrail", raw)[0]

    def test_an_event_keeps_a_valid_item_key(self) -> None:
        self.assertEqual(self.events(item="acct-7")[0].item, "acct-7")

    def test_an_event_without_or_with_a_bad_item_has_none(self) -> None:
        self.assertIsNone(self.events()[0].item)
        self.assertIsNone(self.events(item="a b")[0].item)
        self.assertIsNone(self.events(item="x" * 65)[0].item)
        self.assertEqual(len(self.events(item="a b")), 1)  # the event itself stays readable


if __name__ == "__main__":
    unittest.main()
