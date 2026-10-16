import json
import unittest
from datetime import datetime, timezone

from app.domain.parsing import (
    parse_alive,
    parse_died,
    parse_flows,
    parse_markers,
    parse_records,
    pipeline_of_key,
)
from tests.fakes import PIPELINE, make_marker, make_run, split

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
