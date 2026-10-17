import json
import unittest
from datetime import datetime, timedelta, timezone

from app.domain.parsing import (
    parse_alive,
    parse_died,
    parse_events,
    parse_failures,
    parse_flows,
    parse_markers,
    parse_records,
    pipeline_of_key,
)
from tests.fakes import PIPELINE, make_failure, make_marker, make_run, split

RUN = "20261015T020000Z"


class TestParsing(unittest.TestCase):
    def test_valid_run_parsed(self) -> None:
        result = parse_records("prod", PIPELINE, split(make_run("prod", RUN))[1])
        self.assertEqual(len(result.records), 9)
        self.assertEqual(result.unreadable_total, 0)

    def test_invalid_records_counted_for_their_run(self) -> None:
        raw = split(make_run("prod", RUN, corrupt=(0,)))[1]
        key, value = raw[1]
        data = json.loads(value)
        bad_cases = {
            "missing field": {k: v for k, v in data.items() if k != "inputs"},
            "negative count": {**data, "output": -1},
            "null input": {**data, "inputs": {"accounts": None}},
            "run mismatch": {**data, "run_id": "20250101T000000Z"},
            "bad index": {**data, "index": "x"},
            "step mismatch": {**data, "step": "mystery"},
            "pipeline mismatch": {**data, "pipeline": "other"},
            "bad time": {**data, "finished_at": "yesterday"},
        }
        for label, bad in bad_cases.items():
            with self.subTest(label):
                result = parse_records("prod", PIPELINE, [(key, json.dumps(bad))])
                self.assertEqual(result.records, [])
                self.assertEqual(result.unreadable_by_run, {RUN: 1})

    def test_bad_json_counted(self) -> None:
        result = parse_records("prod", PIPELINE, split(make_run("prod", RUN, corrupt=(0,)))[1])
        self.assertEqual(len(result.records), 8)
        self.assertEqual(result.unreadable_by_run, {RUN: 1})

    def test_unparseable_key_is_unattributed(self) -> None:
        result = parse_records("prod", PIPELINE, [("waypoint:callrail:prod:garbage", "{}")])
        self.assertEqual(result.unreadable_unattributed, 1)
        self.assertEqual(result.unreadable_by_run, {})
        self.assertEqual(result.unreadable_total, 1)

    def test_extra_fields_ignored_and_not_retained(self) -> None:
        key, value = split(make_run("prod", RUN))[1][0]
        data = json.loads(value)
        data["caller_name"] = "Jane Doe"
        result = parse_records("prod", PIPELINE, [(key, json.dumps(data))])
        self.assertEqual(len(result.records), 1)
        self.assertNotIn("caller_name", repr(result.records[0]))
        self.assertNotIn("Jane", repr(result.records[0]))

    def test_optional_finish_fields_are_parsed(self) -> None:
        # specs/012: library 0.4.0 adds started_at and duration_ms to the finish record
        key, value = split(make_run("prod", RUN))[1][0]
        data = json.loads(value)
        data["started_at"] = "2026-10-15T02:00:01Z"
        data["duration_ms"] = 1500
        record = parse_records("prod", PIPELINE, [(key, json.dumps(data))]).records[0]
        self.assertEqual(record.started_at, datetime(2026, 10, 15, 2, 0, 1, tzinfo=timezone.utc))
        self.assertEqual(record.duration_ms, 1500)

    def test_finish_fields_are_none_on_older_records(self) -> None:
        record = parse_records("prod", PIPELINE, split(make_run("prod", RUN))[1]).records[0]
        self.assertIsNone(record.started_at)
        self.assertIsNone(record.duration_ms)

    def test_bad_optional_finish_fields_are_ignored_not_unreadable(self) -> None:
        key, value = split(make_run("prod", RUN))[1][0]
        base = json.loads(value)
        bad_cases = [
            {"duration_ms": "5"},
            {"duration_ms": -1},
            {"duration_ms": True},
            {"duration_ms": 1.5},
            {"started_at": "x"},
            {"started_at": 5},
        ]
        for extra in bad_cases:
            with self.subTest(extra=extra):
                result = parse_records("prod", PIPELINE, [(key, json.dumps({**base, **extra}))])
                self.assertEqual(result.unreadable_total, 0)
                (record,) = result.records
                self.assertIsNone(
                    record.duration_ms if "duration_ms" in extra else record.started_at
                )

    def test_step_names_are_not_whitelisted(self) -> None:
        key = f"waypoint:other:prod:{RUN}:step:01-anything_goes"
        record = {
            "pipeline": "other",
            "run_id": RUN,
            "env": "prod",
            "step": "anything_goes",
            "index": 1,
            "inputs": {},
            "output": 2,
            "finished_at": "2026-10-15T02:00:08Z",
        }
        result = parse_records("prod", "other", [(key, json.dumps(record))])
        self.assertEqual(len(result.records), 1)

    def test_old_layout_keys_are_ignored_and_not_counted(self) -> None:
        raw = [
            (f"callrail:audit:prod:{RUN}:01-read_callrail_account", "{}"),
            (f"callrail:running:prod:{RUN}:01-read_callrail_account", "{}"),
        ]
        self.assertEqual(parse_records("prod", PIPELINE, raw).unreadable_total, 0)
        self.assertEqual(parse_markers("prod", PIPELINE, raw), [])
        self.assertEqual(parse_flows("prod", PIPELINE, raw), {})
        self.assertIsNone(pipeline_of_key("prod", raw[0][0]))

    def test_keys_under_any_other_prefix_are_ignored_and_not_counted(self) -> None:
        previous = "etl" + "-audit"  # the prefix used before the rename to Waypoint
        raw = [
            (f"{previous}:{PIPELINE}:prod:{RUN}:flow", "{}"),
            (f"{previous}:{PIPELINE}:prod:{RUN}:step:01-read_callrail_account", "{}"),
            (f"{previous}:{PIPELINE}:prod:{RUN}:running:01-read_callrail_account", "{}"),
            (f"someone-else:{PIPELINE}:prod:{RUN}:step:01-a", "{}"),
        ]
        self.assertEqual(parse_records("prod", PIPELINE, raw).unreadable_total, 0)
        self.assertEqual(parse_records("prod", PIPELINE, raw).records, [])
        self.assertEqual(parse_markers("prod", PIPELINE, raw), [])
        self.assertEqual(parse_flows("prod", PIPELINE, raw), {})
        for key, _ in raw:
            self.assertIsNone(pipeline_of_key("prod", key))

    def test_other_pipeline_and_bad_pipeline_names_are_skipped(self) -> None:
        raw = split(make_run("prod", RUN, pipeline="demo"))[1]
        self.assertEqual(parse_records("prod", PIPELINE, raw).unreadable_total, 0)
        self.assertEqual(parse_records("prod", "demo", raw).unreadable_total, 0)
        self.assertEqual(len(parse_records("prod", "demo", raw).records), 9)
        self.assertIsNone(pipeline_of_key("prod", f"waypoint:Bad:prod:{RUN}:flow"))
        self.assertIsNone(pipeline_of_key("prod", f"waypoint:a:b:prod:{RUN}:flow"))
        self.assertEqual(pipeline_of_key("prod", f"waypoint:demo:prod:{RUN}:flow"), "demo")
        self.assertIsNone(pipeline_of_key("qa", f"waypoint:demo:prod:{RUN}:flow"))

    def test_flows_by_run(self) -> None:
        flows = parse_flows("prod", PIPELINE, split(make_run("prod", RUN))[0])
        self.assertEqual(flows[RUN][0], "ok")


STARTED = datetime(2026, 10, 15, 2, 0, 8, tzinfo=timezone.utc)


class TestParseMarkers(unittest.TestCase):
    def _marker(self, **overrides: object) -> list:  # type: ignore[type-arg]
        key, value = make_marker("prod", RUN, 3, STARTED)
        data = {**json.loads(value), **overrides}
        return [(key, json.dumps(data))]

    def test_valid_marker_parsed(self) -> None:
        (marker,) = parse_markers("prod", PIPELINE, [make_marker("prod", RUN, 3, STARTED)])
        self.assertEqual(
            (marker.pipeline, marker.run_id, marker.step, marker.index, marker.started_at),
            (PIPELINE, RUN, "read_instances", 4, STARTED),
        )

    def test_invalid_markers_are_dropped_without_error(self) -> None:
        bad = [
            self._marker(env="qa"),
            self._marker(run_id="20260101T000000Z"),
            self._marker(step="read_partners"),
            self._marker(pipeline="other"),
            self._marker(index=0),
            self._marker(index=True),
            self._marker(started_at="yesterday"),
            self._marker(started_at=None),
            [(self._marker()[0][0], "{not json")],
            [(self._marker()[0][0], "[1]")],
            [("waypoint:callrail:prod:garbage", "{}")],
            [(f"waypoint:callrail:prod:{RUN}:step:01-read_callrail_account", "{}")],
        ]
        for raw in bad:
            self.assertEqual(parse_markers("prod", PIPELINE, raw), [], raw)

    def test_other_env_ignored(self) -> None:
        self.assertEqual(parse_markers("qa", PIPELINE, [make_marker("prod", RUN, 0, STARTED)]), [])


if __name__ == "__main__":
    unittest.main()


def _alive_key(run: str = RUN, env: str = "prod", pipeline: str = PIPELINE) -> str:
    return f"waypoint:{pipeline}:{env}:{run}:alive"


def _alive_value(**over: object) -> str:
    data = {
        "v": 1,
        "pipeline": PIPELINE,
        "env": "prod",
        "run_id": RUN,
        "beat_at": "2026-10-15T02:05:00Z",
    }
    data.update(over)
    return json.dumps(data)


def _died_value(**over: object) -> str:
    data = {
        "v": 1,
        "pipeline": PIPELINE,
        "env": "prod",
        "run_id": RUN,
        "judged_at": "2026-10-15T02:07:00Z",
        "last_seen_at": "2026-10-15T02:05:00Z",
    }
    data.update(over)
    return json.dumps(data)


class TestAliveAndDied(unittest.TestCase):
    """specs/009-run-liveness-heartbeat/contracts/redis-keys.md"""

    def test_valid_alive_is_keyed_by_run(self) -> None:
        out = parse_alive("prod", PIPELINE, [(_alive_key(), _alive_value())])
        self.assertEqual(list(out), [RUN])
        self.assertEqual(out[RUN].beat_at, datetime(2026, 10, 15, 2, 5, 0, tzinfo=timezone.utc))

    def test_invalid_alive_is_dropped_without_counting(self) -> None:
        cases = {
            "not json": "{nope",
            "not an object": "[1]",
            "pipeline mismatch": _alive_value(pipeline="other"),
            "env mismatch": _alive_value(env="qa"),
            "run mismatch": _alive_value(run_id="20250101T000000Z"),
            "missing time": json.dumps(
                {"v": 1, "pipeline": PIPELINE, "env": "prod", "run_id": RUN}
            ),
            "unreadable time": _alive_value(beat_at="yesterday"),
            "time is a number": _alive_value(beat_at=5),
        }
        for label, value in cases.items():
            with self.subTest(label):
                self.assertEqual(parse_alive("prod", PIPELINE, [(_alive_key(), value)]), {})

    def test_alive_ignores_other_keys_envs_and_pipelines(self) -> None:
        other = [
            (f"waypoint:{PIPELINE}:prod:{RUN}:flow", _alive_value()),
            (f"waypoint:{PIPELINE}:prod:{RUN}:running:01-x", _alive_value()),
            (_alive_key(env="qa"), _alive_value(env="qa")),
            (_alive_key(pipeline="other"), _alive_value(pipeline="other")),
            (f"waypoint:{PIPELINE}:prod:{RUN}:alive:extra", _alive_value()),
            (f"waypoint:{PIPELINE}:prod:not-a-run:alive", _alive_value()),
        ]
        self.assertEqual(parse_alive("prod", PIPELINE, other), {})

    def test_valid_died_is_keyed_by_run(self) -> None:
        key = f"waypoint:{PIPELINE}:prod:{RUN}:died"
        out = parse_died("prod", PIPELINE, [(key, _died_value())])
        verdict = out[RUN]
        self.assertEqual(verdict.judged_at, datetime(2026, 10, 15, 2, 7, 0, tzinfo=timezone.utc))
        self.assertEqual(verdict.last_seen_at, datetime(2026, 10, 15, 2, 5, 0, tzinfo=timezone.utc))

    def test_invalid_died_is_dropped(self) -> None:
        key = f"waypoint:{PIPELINE}:prod:{RUN}:died"
        for label, value in {
            "not json": "x",
            "no judged_at": _died_value(judged_at=None),
            "bad last_seen": _died_value(last_seen_at="soon"),
            "run mismatch": _died_value(run_id="20250101T000000Z"),
        }.items():
            with self.subTest(label):
                self.assertEqual(parse_died("prod", PIPELINE, [(key, value)]), {})


class TestParseFailures(unittest.TestCase):
    """specs/011-step-failure-errors/data-model.md: Failure item"""

    AT = datetime(2026, 10, 17, 2, 3, 41, tzinfo=timezone.utc)

    def _item(self, **kw: object) -> tuple:  # type: ignore[type-arg]
        return make_failure("prod", RUN, 1, self.AT, **kw)  # type: ignore[arg-type]

    def test_valid_item_parses(self) -> None:
        failures, unreadable = parse_failures("prod", PIPELINE, [self._item()])
        self.assertEqual(unreadable, {})
        (f,) = failures
        self.assertEqual((f.step, f.index, f.run_id), ("read_callrail_call", 2, RUN))
        self.assertEqual(f.failed_at, self.AT)
        self.assertEqual(f.started_at, self.AT - timedelta(seconds=5))
        self.assertEqual((f.error.type, f.error.message), ("ValueError", "boom"))
        self.assertIn("ValueError: boom", f.error.traceback)

    def test_invalid_items_are_skipped_and_counted_for_their_run(self) -> None:
        key, value = self._item()
        data = json.loads(value)
        bad_cases = {
            "bad json": "{nope",
            "not an object": "[1]",
            "pipeline": {**data, "pipeline": "other"},
            "env": {**data, "env": "qa"},
            "run": {**data, "run_id": "20250101T000000Z"},
            "step": {**data, "step": "mystery"},
            "index not int": {**data, "index": "2"},
            "index zero": {**data, "index": 0},
            "index differs from key": {**data, "index": 3},
            "bad failed_at": {**data, "failed_at": "yesterday"},
            "bad started_at": {**data, "started_at": 5},
            "no error": {k: v for k, v in data.items() if k != "error"},
            "error not object": {**data, "error": "x"},
            "empty type": {**data, "error": {**data["error"], "type": ""}},
            "type not string": {**data, "error": {**data["error"], "type": 5}},
            "traceback not string": {**data, "error": {**data["error"], "traceback": 5}},
            "message not string": {**data, "error": {**data["error"], "message": 5}},
        }
        for label, bad in bad_cases.items():
            with self.subTest(label):
                raw = bad if isinstance(bad, str) else json.dumps(bad)
                failures, unreadable = parse_failures("prod", PIPELINE, [(key, raw)])
                self.assertEqual(failures, [])
                self.assertEqual(unreadable, {RUN: 1})

    def test_long_message_and_traceback_are_shortened_not_rejected(self) -> None:
        error = {"type": "T" * 500, "message": "m" * 900, "traceback": "a\n" * 9000 + "LAST\n"}
        (f,) = parse_failures("prod", PIPELINE, [self._item(error=error)])[0]
        self.assertEqual(len(f.error.type), 200)
        self.assertEqual(len(f.error.message or ""), 500)
        self.assertLessEqual(len(f.error.traceback.encode("utf-8")), 8192)
        self.assertTrue(f.error.traceback.endswith("LAST\n"))

    def test_missing_message_is_none(self) -> None:
        error = {"type": "KeyError", "traceback": "KeyError\n"}
        (f,) = parse_failures("prod", PIPELINE, [self._item(error=error)])[0]
        self.assertIsNone(f.error.message)

    def test_foreign_and_non_failure_keys_are_ignored_not_counted(self) -> None:
        key, value = self._item()
        other_pipeline = key.replace(f"waypoint:{PIPELINE}:", "waypoint:other:")
        other_env = key.replace(":prod:", ":qa:")
        step_key = key.replace(":failed:", ":step:")
        raw = [(other_pipeline, value), (other_env, value), (step_key, value)]
        self.assertEqual(parse_failures("prod", PIPELINE, raw), ([], {}))

    def test_malformed_key_under_the_pipeline_is_not_counted_per_run(self) -> None:
        failures, unreadable = parse_failures(
            "prod", PIPELINE, [(f"waypoint:{PIPELINE}:prod:{RUN}:failed:x", "{}")]
        )
        self.assertEqual(failures, [])
        self.assertEqual(unreadable, {})

    def test_unknown_fields_are_dropped(self) -> None:
        key, value = self._item()
        data = {**json.loads(value), "extra": "x"}
        (f,) = parse_failures("prod", PIPELINE, [(key, json.dumps(data))])[0]
        self.assertFalse(hasattr(f, "extra"))


def event_json(level: str = "info", **over: object) -> str:
    base = {
        "v": 1,
        "n": 1,
        "ts": "2026-10-15T02:03:41.482Z",
        "level": level,
        "message": "Loaded batch 3",
    }
    return json.dumps({**base, **over})


def event_key(
    level: str = "info", run: str = RUN, pipeline: str = PIPELINE, env: str = "prod"
) -> str:
    return f"waypoint:{pipeline}:{env}:{run}:events:{level}"


class TestParseEvents(unittest.TestCase):
    """Specs 012 data-model.md "Run event"."""

    def parse(self, key: str, *elements: str):  # type: ignore[no-untyped-def]
        return parse_events("prod", PIPELINE, [(key, list(elements))])

    def test_a_valid_event_parses(self) -> None:
        events, unreadable = self.parse(
            event_key("warning"),
            event_json("warning", n=4, step="load", fields={"rows": 1200, "source": "api"}),
        )
        self.assertEqual(unreadable, {})
        (e,) = events
        self.assertEqual((e.run_id, e.level, e.n, e.step), (RUN, "warning", 4, "load"))
        self.assertEqual(e.message, "Loaded batch 3")
        self.assertEqual(e.fields, {"rows": 1200, "source": "api"})
        self.assertEqual(e.ts, datetime(2026, 10, 15, 2, 3, 41, 482000, tzinfo=timezone.utc))

    def test_damaged_elements_are_skipped_and_counted_for_their_run(self) -> None:
        cases = {
            "bad json": "{nope",
            "not an object": "[1]",
            "wrong version": event_json(v=2),
            "no version": json.dumps({"n": 1, "ts": "2026-10-15T02:03:41Z", "level": "info"}),
            "level differs from the list": event_json("error"),
            "missing ts": event_json(ts=None),
            "bad ts": event_json(ts="yesterday"),
            "n zero": event_json(n=0),
            "n text": event_json(n="1"),
            "n bool": event_json(n=True),
        }
        for label, raw in cases.items():
            with self.subTest(label):
                events, unreadable = self.parse(event_key("info"), raw)
                self.assertEqual(events, [])
                self.assertEqual(unreadable, {RUN: 1})

    def test_the_rest_survives_a_damaged_element(self) -> None:
        events, unreadable = self.parse(event_key(), event_json(n=1), "{x", event_json(n=3))
        self.assertEqual([e.n for e in events], [1, 3])
        self.assertEqual(unreadable, {RUN: 1})

    def test_long_message_is_shortened_not_rejected(self) -> None:
        (e,), _ = self.parse(event_key(), event_json(message="x" * 900))
        self.assertEqual(len(e.message or ""), 300)

    def test_missing_or_wrong_type_message_and_step_are_none(self) -> None:
        for extra in ({"message": None}, {"message": 5}, {"message": ""}):
            with self.subTest(extra=extra):
                (e,), _ = self.parse(event_key(), event_json(**extra))
                self.assertIsNone(e.message)
        (e,), _ = self.parse(event_key(), event_json(step=7))
        self.assertIsNone(e.step)
        (e,), _ = self.parse(event_key(), event_json(step=""))
        self.assertIsNone(e.step)

    def test_fields_are_limited_and_filtered_not_rejected(self) -> None:
        many = {f"f{i}": i for i in range(15)}
        (e,), _ = self.parse(event_key(), event_json(fields=many))
        self.assertEqual(len(e.fields or {}), 10)
        bad = {
            "ok": 1,
            "bad name!": 2,
            "x" * 41: 3,
            "flag": True,
            "list": [1],
            "obj": {"a": 1},
            "long": "y" * 101,
            "text": "short",
            "pi": 3.14,
            "none": None,
        }
        (e,), unreadable = self.parse(event_key(), event_json(fields=bad))
        self.assertEqual(e.fields, {"ok": 1, "text": "short", "pi": 3.14})
        self.assertEqual(unreadable, {})
        (e,), _ = self.parse(event_key(), event_json(fields={"bad name!": 1}))
        self.assertIsNone(e.fields)
        (e,), _ = self.parse(event_key(), event_json(fields="nope"))
        self.assertIsNone(e.fields)

    def test_non_finite_numbers_are_dropped(self) -> None:
        raw = '{"v":1,"n":1,"ts":"2026-10-15T02:03:41Z","level":"info","fields":{"a":NaN,"b":Infinity,"c":2}}'
        (e,), _ = self.parse(event_key(), raw)
        self.assertEqual(e.fields, {"c": 2})

    def test_other_pipelines_envs_and_non_event_keys_are_ignored_not_counted(self) -> None:
        pairs = [
            (event_key(pipeline="demo"), ["{x"]),
            (event_key(env="qa"), ["{x"]),
            (f"waypoint:{PIPELINE}:prod:{RUN}:events:debug", ["{x"]),
            (f"waypoint:{PIPELINE}:prod:{RUN}:step:01-a", ["{x"]),
            (f"waypoint:{PIPELINE}:prod:{RUN}:events", ["{x"]),
        ]
        events, unreadable = parse_events("prod", PIPELINE, pairs)
        self.assertEqual((events, unreadable), ([], {}))

    def test_events_of_all_levels_and_runs_are_gathered(self) -> None:
        other = "20261014T020000Z"
        pairs = [
            (event_key("info"), [event_json(n=1)]),
            (event_key("error"), [event_json("error", n=2)]),
            (event_key("info", run=other), [event_json(n=1)]),
        ]
        events, _ = parse_events("prod", PIPELINE, pairs)
        self.assertEqual(
            sorted((e.run_id, e.level) for e in events),
            [(other, "info"), (RUN, "error"), (RUN, "info")],
        )


if __name__ == "__main__":
    unittest.main()
