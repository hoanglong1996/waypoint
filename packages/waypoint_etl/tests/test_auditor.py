import json
import unittest
from dataclasses import replace
from typing import Dict, List, Tuple
from unittest import mock

from waypoint_etl.auditor import StepAuditor, count_items
from waypoint_etl.keys import START_MARKER_TTL_SECONDS
from waypoint_etl.spec import GroupSpec, MapStepSpec, Metric, PipelineSpec, StepSpec, validate_spec
from waypoint_etl.stores import NoopStepAuditStore

SPEC = PipelineSpec(
    name="demo",
    label="Demo",
    groups=(GroupSpec("g", "Group"),),
    steps=(
        StepSpec("read_x", label="X", group="g"),
        StepSpec("merge", inputs=(("a", "read_x"), ("b", "read_x")), returns_nothing=True),
    ),
)
Entry = Tuple[str, Dict[str, object], int]


class FakeStore:
    def __init__(self) -> None:
        self.records: List[Entry] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.records.append((key, record, ttl_seconds))


def finished(store: FakeStore) -> List[Entry]:
    return [r for r in store.records if ":step:" in r[0]]


def markers(store: FakeStore) -> List[Entry]:
    return [r for r in store.records if ":running:" in r[0]]


def flows(store: FakeStore) -> List[Entry]:
    return [r for r in store.records if r[0].endswith(":flow")]


class RaisingStore:
    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        raise ConnectionError("redis down")


def auditor(store: object, env: str = "prod", ttl: int = 30 * 86400) -> StepAuditor:
    return StepAuditor(store, SPEC, env=env, ttl_seconds=ttl, run_id="R1")  # type: ignore[arg-type]


class TestCountItems(unittest.TestCase):
    def test_none(self) -> None:
        self.assertIsNone(count_items(None))

    def test_collections(self) -> None:
        self.assertEqual(count_items([]), 0)
        self.assertEqual(count_items(list(range(10))), 10)
        self.assertEqual(count_items((1, 2)), 2)
        self.assertEqual(count_items({1, 2, 3}), 3)

    def test_single_object(self) -> None:
        self.assertEqual(count_items(object()), 1)
        self.assertEqual(count_items("abc"), 1)


class TestValidateSpec(unittest.TestCase):
    def bad(self, spec: PipelineSpec, text: str) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_spec(spec)
        self.assertIn(text, str(ctx.exception))

    def test_valid(self) -> None:
        validate_spec(SPEC)

    def test_pipeline_name(self) -> None:
        for name in ("Demo", "a:b", "", "-x", "x" * 41):
            self.bad(replace(SPEC, name=name), "pipeline name")
        validate_spec(replace(SPEC, name="a-b_1"))

    def test_pipeline_label_too_long(self) -> None:
        self.bad(replace(SPEC, label="x" * 61), "pipeline label")

    def test_step_count(self) -> None:
        self.bad(replace(SPEC, steps=()), "between 1 and")
        many = tuple(StepSpec(f"s{i}") for i in range(101))
        self.bad(replace(SPEC, steps=many, groups=()), "between 1 and")

    def test_step_name(self) -> None:
        self.bad(replace(SPEC, steps=(StepSpec("Bad-Name"),), groups=()), "step name")
        self.bad(replace(SPEC, steps=(StepSpec("x" * 65),), groups=()), "step name")

    def test_duplicate_step(self) -> None:
        self.bad(replace(SPEC, steps=(StepSpec("a"), StepSpec("a")), groups=()), "duplicate")

    def test_step_label_too_long(self) -> None:
        self.bad(replace(SPEC, steps=(StepSpec("a", label="x" * 41),), groups=()), "label of step")

    def test_undeclared_group(self) -> None:
        self.bad(replace(SPEC, steps=(StepSpec("a", group="nope"),)), "undeclared group")

    def test_input_from_unknown_or_later_step(self) -> None:
        unknown = (StepSpec("a", inputs=(("i", "zzz"),)),)
        self.bad(replace(SPEC, steps=unknown, groups=()), "not an earlier step")
        later = (StepSpec("a", inputs=(("i", "b"),)), StepSpec("b"))
        self.bad(replace(SPEC, steps=later, groups=()), "not an earlier step")

    def test_negative_hint(self) -> None:
        self.bad(replace(SPEC, steps=(StepSpec("a", row=-1),), groups=()), "layout hint")


class TestStepAuditor(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        self.auditor = auditor(self.store)

    def test_record_fields_and_key(self) -> None:
        result = self.auditor.run("read_x", lambda: [1, 2, 3])

        self.assertEqual(result, [1, 2, 3])
        key, record, _ = finished(self.store)[0]
        self.assertEqual(key, "waypoint:demo:prod:R1:step:01-read_x")
        self.assertEqual(record["pipeline"], "demo")
        self.assertEqual(record["run_id"], "R1")
        self.assertEqual(record["env"], "prod")
        self.assertEqual(record["step"], "read_x")
        self.assertEqual(record["index"], 1)
        self.assertEqual(record["inputs"], {})
        self.assertEqual(record["output"], 3)
        self.assertTrue(str(record["finished_at"]).endswith("Z"))

    def test_multiple_inputs_and_none_output(self) -> None:
        self.auditor.run("merge", lambda a, b: None, [1], [2, 3], inputs={"a": [1], "b": [2, 3]})

        record = finished(self.store)[0][1]
        self.assertEqual(record["inputs"], {"a": 1, "b": 2})
        self.assertIsNone(record["output"])

    def test_inputs_dict_not_passed_to_fn(self) -> None:
        seen: List[Tuple[object, ...]] = []
        self.auditor.run("read_x", lambda *a: seen.append(a), "x", inputs={"i": [1]})
        self.assertEqual(seen, [("x",)])

    def test_indices_are_sequential(self) -> None:
        self.auditor.run("read_x", lambda: None)
        self.auditor.run("merge", lambda: None)
        self.assertEqual([r["index"] for _, r, _ in finished(self.store)], [1, 2])
        self.assertTrue(finished(self.store)[1][0].endswith(":02-merge"))

    def test_ttl_is_30_days_and_custom(self) -> None:
        self.auditor.run("read_x", lambda: None)
        self.assertEqual(finished(self.store)[0][2], 2592000)
        other = FakeStore()
        auditor(other, env="qa", ttl=7 * 86400).run("read_x", lambda: None)
        self.assertEqual(finished(other)[0][2], 7 * 86400)

    def test_store_failure_is_swallowed(self) -> None:
        self.assertEqual(auditor(RaisingStore()).run("read_x", lambda: [1]), [1])

    def test_step_exception_propagates_and_is_not_recorded(self) -> None:
        self.auditor.run("read_x", lambda: [1])

        def boom() -> None:
            raise ValueError("bad")

        with self.assertRaises(ValueError):
            self.auditor.run("merge", boom)
        self.assertEqual([r["step"] for _, r, _ in finished(self.store)], ["read_x"])

    def test_step_outside_spec_is_still_recorded_with_a_warning(self) -> None:
        self.assertEqual(self.auditor.run("surprise", lambda: [1, 2]), [1, 2])
        self.assertEqual(finished(self.store)[0][1]["step"], "surprise")


class TestFlow(unittest.TestCase):
    def test_start_writes_flow_with_exact_fields_before_any_marker(self) -> None:
        store = FakeStore()
        a = auditor(store)
        a.run("read_x", lambda: None)

        key, value, ttl = store.records[0]
        self.assertEqual(key, "waypoint:demo:prod:R1:flow")
        self.assertEqual(ttl, 30 * 86400)
        self.assertEqual(
            value,
            {
                "v": 1,
                "pipeline": "demo",
                "env": "prod",
                "run_id": "R1",
                "label": "Demo",
                "groups": [{"key": "g", "label": "Group"}],
                "steps": [
                    {"name": "read_x", "inputs": [], "label": "X", "group": "g"},
                    {
                        "name": "merge",
                        "inputs": [
                            {"name": "a", "from": "read_x"},
                            {"name": "b", "from": "read_x"},
                        ],
                        "returns_nothing": True,
                    },
                ],
            },
        )
        json.dumps(value)  # serialisable

    def test_flow_written_once_per_run(self) -> None:
        store = FakeStore()
        a = auditor(store)
        a.start()
        a.run("read_x", lambda: None)
        a.run("merge", lambda: None)
        self.assertEqual(len(flows(store)), 1)

    def test_flow_write_failure_does_not_stop_steps(self) -> None:
        class FlowFails(FakeStore):
            def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
                if key.endswith(":flow"):
                    raise ConnectionError("down")
                super().write(key, record, ttl_seconds)

        store = FlowFails()
        self.assertEqual(auditor(store).run("read_x", lambda: [1]), [1])
        self.assertEqual(len(finished(store)), 1)

    def test_invalid_spec_runs_steps_and_writes_no_flow(self) -> None:
        store = FakeStore()
        bad = StepAuditor(store, replace(SPEC, name="Bad Name"), env="p", ttl_seconds=1, run_id="R")
        self.assertEqual(bad.run("read_x", lambda: [1]), [1])
        self.assertEqual(flows(store), [])
        self.assertEqual(len(finished(store)), 1)

    def test_written_values_hold_counts_only(self) -> None:
        store = FakeStore()
        a = auditor(store)
        secret = ["caller-name-555-0100"]
        a.run("merge", lambda x: secret, secret, inputs={"a": secret})
        text = json.dumps([r for _, r, _ in store.records])
        self.assertNotIn("caller-name", text)


class TestStartMarker(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        self.auditor = auditor(self.store)

    def test_marker_written_before_step_runs(self) -> None:
        seen: List[int] = []
        self.auditor.run("read_x", lambda: seen.append(len(markers(self.store))))
        self.assertEqual(seen, [1])

    def test_marker_key_ttl_and_fields(self) -> None:
        self.auditor.run("read_x", lambda: None)
        key, record, ttl = markers(self.store)[0]
        self.assertEqual(key, "waypoint:demo:prod:R1:running:01-read_x")
        self.assertEqual(ttl, START_MARKER_TTL_SECONDS)
        self.assertEqual(ttl, 86400)
        self.assertEqual(set(record), {"pipeline", "run_id", "env", "step", "index", "started_at"})
        self.assertTrue(str(record["started_at"]).endswith("Z"))

    def test_marker_failure_is_swallowed_and_step_still_runs(self) -> None:
        class MarkerFails(FakeStore):
            def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
                if ":running:" in key:
                    raise ConnectionError("redis down")
                super().write(key, record, ttl_seconds)

        store = MarkerFails()
        self.assertEqual(auditor(store).run("read_x", lambda: [1]), [1])
        self.assertEqual(len(finished(store)), 1)

    def test_marker_stays_and_no_finish_record_when_step_raises(self) -> None:
        def boom() -> None:
            raise ValueError("bad")

        with self.assertRaises(ValueError):
            self.auditor.run("read_x", boom)
        self.assertEqual(len(markers(self.store)), 1)
        self.assertEqual(finished(self.store), [])
        # since 0.3.0 the failure is recorded as its own item (the marker is left in place)
        self.assertEqual(
            [k for k, _, _ in self.store.records if ":failed:" in k],
            ["waypoint:demo:prod:R1:failed:01-read_x"],
        )

    def test_noop_store_works(self) -> None:
        a = StepAuditor(NoopStepAuditStore(), SPEC, env="", ttl_seconds=0, run_id="R")
        self.assertEqual(a.run("read_x", lambda: 5), 5)


class TestFinishTimes(unittest.TestCase):
    """Specs 012: the finish record carries the step's start time and a monotonic duration."""

    def test_finish_has_started_at_and_duration(self) -> None:
        store = FakeStore()
        a = auditor(store)
        index = a.begin("read_x")
        a.finish("read_x", index, {}, [1])
        record = finished(store)[0][1]
        self.assertEqual(record["started_at"], markers(store)[0][1]["started_at"])
        self.assertIsInstance(record["duration_ms"], int)
        self.assertGreaterEqual(record["duration_ms"], 0)  # type: ignore[operator]
        for key in (
            "pipeline",
            "run_id",
            "env",
            "step",
            "index",
            "inputs",
            "output",
            "finished_at",
        ):
            self.assertIn(key, record)

    def test_duration_uses_monotonic_clock(self) -> None:
        store = FakeStore()
        a = auditor(store)
        with mock.patch("waypoint_etl.auditor.time.monotonic", side_effect=[100.0, 102.5]):
            index = a.begin("read_x")
            a.finish("read_x", index, {}, None)
        self.assertEqual(finished(store)[0][1]["duration_ms"], 2500)

    def test_finish_of_unknown_index_omits_new_fields(self) -> None:
        store = FakeStore()
        auditor(store).finish("read_x", 7, {}, None)
        record = finished(store)[0][1]
        self.assertNotIn("started_at", record)
        self.assertNotIn("duration_ms", record)

    def test_run_writes_them_too(self) -> None:
        store = FakeStore()
        auditor(store).run("read_x", lambda: [1, 2])
        record = finished(store)[0][1]
        self.assertIn("started_at", record)
        self.assertIn("duration_ms", record)


class TestMapFlow(unittest.TestCase):
    """Specs 014 contracts/redis-keys.md "Extended: flow record"."""

    MAP_SPEC = PipelineSpec(
        name="demo",
        steps=(
            StepSpec("b"),
            MapStepSpec(
                "accounts",
                over="b",
                max_concurrency=5,
                label="Accounts",
                group=None,
                inputs=(("accounts", "b"),),
                steps=(
                    StepSpec("fetch"),
                    StepSpec(
                        "transform",
                        inputs=(("rows", "fetch"),),
                        metrics=(Metric("rejected", unit="rows", warn_above=100),),
                    ),
                ),
            ),
            StepSpec("publish", inputs=(("done", "accounts"),)),
        ),
    )

    def test_a_map_step_is_written_with_its_item_flow(self) -> None:
        store = FakeStore()
        StepAuditor(store, self.MAP_SPEC, env="prod", ttl_seconds=60, run_id="R1").start()
        _, value, _ = store.records[0]
        self.assertEqual(value["v"], 1)  # the flow version is unchanged
        steps = value["steps"]
        assert isinstance(steps, list)
        self.assertEqual(steps[0], {"name": "b", "inputs": []})
        self.assertEqual(
            steps[1],
            {
                "name": "accounts",
                "kind": "map",
                "inputs": [{"name": "accounts", "from": "b"}],
                "over": "b",
                "max_concurrency": 5,
                "label": "Accounts",
                "steps": [
                    {"name": "fetch", "inputs": []},
                    {
                        "name": "transform",
                        "inputs": [{"name": "rows", "from": "fetch"}],
                        "metrics": [{"name": "rejected", "unit": "rows", "warn_above": 100}],
                    },
                ],
            },
        )
        self.assertEqual(
            steps[2], {"name": "publish", "inputs": [{"name": "done", "from": "accounts"}]}
        )
        json.dumps(value)

    def test_optional_map_fields_are_left_out_when_unset(self) -> None:
        spec = PipelineSpec(name="demo", steps=(MapStepSpec("m", steps=(StepSpec("x"),)),))
        store = FakeStore()
        StepAuditor(store, spec, env="prod", ttl_seconds=60, run_id="R1").start()
        steps = store.records[0][1]["steps"]
        self.assertEqual(
            steps,
            [{"name": "m", "kind": "map", "inputs": [], "steps": [{"name": "x", "inputs": []}]}],
        )

    def test_a_pipeline_without_a_map_step_writes_the_same_bytes_as_before(self) -> None:
        store = FakeStore()
        StepAuditor(store, SPEC, env="prod", ttl_seconds=60, run_id="R1").start()
        self.assertEqual(
            json.dumps(store.records[0][1]),
            '{"v": 1, "pipeline": "demo", "env": "prod", "run_id": "R1", '
            '"steps": [{"name": "read_x", "inputs": [], "label": "X", "group": "g"}, '
            '{"name": "merge", "inputs": [{"name": "a", "from": "read_x"}, '
            '{"name": "b", "from": "read_x"}], "returns_nothing": true}], '
            '"label": "Demo", "groups": [{"key": "g", "label": "Group"}]}',
        )

    def test_step_spec_finds_top_level_and_inner_steps(self) -> None:
        a = StepAuditor(FakeStore(), self.MAP_SPEC, env="prod", ttl_seconds=60, run_id="R1")
        self.assertEqual(a.step_spec("b"), self.MAP_SPEC.steps[0])
        self.assertIsInstance(a.step_spec("accounts"), MapStepSpec)
        inner = a.step_spec("transform")
        assert isinstance(inner, StepSpec)
        self.assertEqual(inner.inputs, (("rows", "fetch"),))
        self.assertIsNone(a.step_spec("nope"))

    def test_an_inner_step_name_is_not_an_unplanned_step_warning(self) -> None:
        a = StepAuditor(FakeStore(), self.MAP_SPEC, env="prod", ttl_seconds=60, run_id="R1")
        with mock.patch("builtins.print") as printed:
            a.run("b", lambda: None)
        printed.assert_not_called()
        self.assertIn("fetch", a._known_steps)


if __name__ == "__main__":
    unittest.main()
