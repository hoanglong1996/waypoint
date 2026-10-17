import json
import unittest
from typing import Any, Dict, List, Optional

from app.domain.flow import parse_flow
from tests.fakes import callrail_flow_steps, flow_value

RUN = "20261015T020000Z"


def parse(steps: List[Dict[str, Any]], **kw: Any) -> Any:
    return parse_flow("demo", "prod", RUN, flow_value("demo", "prod", RUN, steps, **kw))


def step(name: str, *sources: str, **extra: Any) -> Dict[str, Any]:
    return {
        "name": name,
        "inputs": [{"name": f"i{n}", "from": s} for n, s in enumerate(sources)],
        **extra,
    }


class TestParseFlow(unittest.TestCase):
    def test_valid_flow(self) -> None:
        status, flow = parse(
            callrail_flow_steps(), groups=[{"key": "gads", "label": "Google Ads"}], label="CallRail"
        )
        self.assertEqual(status, "ok")
        self.assertEqual(flow.label, "CallRail")
        self.assertEqual(len(flow.steps), 9)
        merge = flow.steps[6]
        self.assertEqual(
            [(i.name, i.source) for i in merge.inputs][0], ("calls", "read_callrail_call")
        )
        self.assertTrue(flow.steps[8].returns_nothing)
        self.assertEqual(flow.groups[0].label, "Google Ads")
        self.assertIsNone(flow.steps[0].group)  # group 'callrail' is not declared here
        self.assertEqual(flow.problems, ())

    def test_invalid_cases(self) -> None:
        good = json.loads(flow_value("demo", "prod", RUN, [step("a")]))
        cases: Dict[str, Optional[str]] = {
            "version not a number": flow_value("demo", "prod", RUN, [step("a")], v="x"),  # type: ignore[arg-type]
            "version is a bool": flow_value("demo", "prod", RUN, [step("a")], v=True),
            "not json": "{nope",
            "not an object": "[1]",
            "no steps": flow_value("demo", "prod", RUN, []),
            "steps not a list": json.dumps({**good, "steps": "x"}),
            "pipeline mismatch": flow_value("other", "prod", RUN, [step("a")]),
            "env mismatch": flow_value("demo", "qa", RUN, [step("a")]),
            "run mismatch": flow_value("demo", "prod", "20250101T000000Z", [step("a")]),
            "only bad steps": flow_value("demo", "prod", RUN, [{"name": "Bad Name"}]),
        }
        for label, raw in cases.items():
            with self.subTest(label):
                self.assertEqual(parse_flow("demo", "prod", RUN, raw or ""), ("invalid", None))

    def test_newer_record_version_is_unsupported_not_invalid(self) -> None:
        for v in (2, 9, 0):
            raw = flow_value("demo", "prod", RUN, [step("a")], v=v)
            self.assertEqual(parse_flow("demo", "prod", RUN, raw), ("unsupported", None))

    def test_dangling_input_kept_and_reported(self) -> None:
        status, flow = parse([step("a"), step("b", "zzz")])
        self.assertEqual(status, "ok")
        (inp,) = flow.steps[1].inputs
        self.assertTrue(inp.dangling)
        self.assertEqual(flow.problems, ("input 'i0' of 'b' names unknown step 'zzz'",))

    def test_cycle_is_reported_and_rendered_acyclic(self) -> None:
        status, flow = parse([step("a", "b"), step("b", "a")])
        self.assertEqual(status, "ok")
        self.assertTrue(any(p.startswith("cycle:") for p in flow.problems))
        edges = [(i.source, s.name) for s in flow.steps for i in s.inputs]
        self.assertEqual(len(edges), 1)  # one edge of the loop is gone

    def test_self_input_is_dangling_not_a_loop(self) -> None:
        _, flow = parse([step("a", "a")])
        self.assertTrue(flow.steps[0].inputs[0].dangling)

    def test_duplicate_and_invalid_steps_dropped(self) -> None:
        _, flow = parse([step("a"), step("a"), {"name": 5}, step("b", "a")])
        self.assertEqual([s.name for s in flow.steps], ["a", "b"])
        self.assertEqual(len(flow.problems), 2)

    def test_long_labels_truncated_and_text_trimmed(self) -> None:
        _, flow = parse([step("a", label="x" * 100)], label="y" * 100)
        self.assertEqual(len(flow.steps[0].label or ""), 40)
        self.assertEqual(len(flow.label or ""), 60)

    def test_unknown_fields_ignored(self) -> None:
        _, flow = parse([step("a", caller_name="Jane Doe", col=2, row=-1)])
        self.assertNotIn("Jane", repr(flow))
        self.assertEqual(flow.steps[0].col, 2.0)
        self.assertIsNone(flow.steps[0].row)  # negative hint ignored

    def test_more_than_100_steps_capped(self) -> None:
        status, flow = parse([step(f"s{i}") for i in range(150)])
        self.assertEqual(status, "ok")
        self.assertEqual(len(flow.steps), 100)
        self.assertTrue(any("first 100" in p for p in flow.problems))


if __name__ == "__main__":
    unittest.main()


class TestMetricDeclarations(unittest.TestCase):
    def test_declarations_are_read_into_the_step(self) -> None:
        status, flow = parse(
            [
                step(
                    "load",
                    metrics=[
                        {
                            "name": "rejected",
                            "label": " Rejected rows ",
                            "unit": "rows",
                            "warn_above": 100,
                        },
                        {"name": "cov", "warn_below": 90.5},
                        {"name": "plain"},
                    ],
                ),
                step("other"),
            ]
        )
        self.assertEqual(status, "ok")
        self.assertEqual(flow.problems, ())
        rejected, cov, plain = flow.steps[0].metrics
        self.assertEqual(
            (
                rejected.name,
                rejected.label,
                rejected.unit,
                rejected.warn_above,
                rejected.warn_below,
            ),
            ("rejected", "Rejected rows", "rows", 100.0, None),
        )
        self.assertEqual((cov.warn_below, cov.warn_above, cov.unit), (90.5, None, None))
        self.assertEqual((plain.label, plain.unit), (None, None))
        self.assertEqual(flow.steps[1].metrics, ())

    def test_label_and_unit_are_cut(self) -> None:
        _, flow = parse([step("a", metrics=[{"name": "m", "label": "L" * 60, "unit": "U" * 30}])])
        self.assertEqual(len(flow.steps[0].metrics[0].label), 40)
        self.assertEqual(len(flow.steps[0].metrics[0].unit), 16)

    def test_bad_declarations_are_dropped_and_reported_without_failing_the_flow(self) -> None:
        bad = [
            {"name": "Bad"},
            {"name": ""},
            {"name": 5},
            "text",
            {"name": "warn", "warn_above": "9"},
            {"name": "warn2", "warn_below": True},
            {"name": "warn3", "warn_above": float("inf")},
            {"name": "dup"},
            {"name": "dup", "unit": "x"},
            {"name": "good", "warn_above": 5},
        ]
        status, flow = parse([step("a", metrics=bad), step("b")])
        self.assertEqual(status, "ok")
        self.assertEqual([m.name for m in flow.steps[0].metrics], ["dup", "good"])
        self.assertEqual(sum("metric declaration" in p for p in flow.problems), 8)
        self.assertTrue(all("'a'" in p for p in flow.problems))

    def test_more_than_twenty_are_cut(self) -> None:
        status, flow = parse([step("a", metrics=[{"name": f"m{i}"} for i in range(25)])])
        self.assertEqual(len(flow.steps[0].metrics), 20)
        self.assertEqual(len(flow.problems), 5)

    def test_metrics_not_a_list_is_dropped(self) -> None:
        status, flow = parse([step("a", metrics={"name": "m"})])
        self.assertEqual(status, "ok")
        self.assertEqual(flow.steps[0].metrics, ())
        self.assertEqual(len(flow.problems), 1)

    def test_a_flow_without_metrics_is_unchanged(self) -> None:
        status, flow = parse(callrail_flow_steps())
        self.assertEqual(status, "ok")
        self.assertEqual(flow.problems, ())
        self.assertTrue(all(s.metrics == () for s in flow.steps))

    def test_declarations_survive_cycle_repair(self) -> None:
        a = step("a", "b", metrics=[{"name": "m"}])
        b = step("b", "a")
        _, flow = parse([b, a])
        self.assertTrue(any("cycle" in p for p in flow.problems))
        self.assertEqual([s.metrics for s in flow.steps if s.name == "a"][0][0].name, "m")


def map_step(
    name: str = "accounts", inner: Optional[List[Dict[str, Any]]] = None, **extra: Any
) -> Dict[str, Any]:
    if inner is None:
        inner = [
            {"name": "fetch", "inputs": []},
            {
                "name": "transform",
                "inputs": [{"name": "rows", "from": "fetch"}],
                "metrics": [{"name": "rejected", "unit": "rows", "warn_above": 100}],
            },
            {"name": "load", "label": "Load", "inputs": [{"name": "rows", "from": "transform"}]},
        ]
    return {
        "name": name,
        "kind": "map",
        "inputs": [{"name": "accounts", "from": "list_accounts"}],
        "steps": inner,
        **extra,
    }


class TestMapSteps(unittest.TestCase):
    def test_a_map_step_keeps_its_item_flow_out_of_the_top_level(self) -> None:
        status, flow = parse(
            [
                step("list_accounts"),
                map_step(over="list_accounts", max_concurrency=5),
                step("publish", "accounts"),
            ]
        )
        self.assertEqual(status, "ok")
        self.assertEqual([s.name for s in flow.steps], ["list_accounts", "accounts", "publish"])
        accounts = flow.steps[1]
        self.assertEqual((accounts.map.over, accounts.map.max_concurrency), ("list_accounts", 5))
        self.assertEqual([s.name for s in accounts.map.steps], ["fetch", "transform", "load"])
        self.assertEqual(accounts.map.steps[1].metrics[0].warn_above, 100.0)
        self.assertEqual(accounts.map.steps[2].label, "Load")
        self.assertEqual(
            [(i.name, i.source, i.dangling) for i in accounts.map.steps[1].inputs],
            [("rows", "fetch", False)],
        )
        self.assertIsNone(flow.steps[0].map)
        self.assertEqual(flow.problems, ())

    def test_an_inner_input_may_come_from_a_top_level_step(self) -> None:
        inner = [{"name": "fetch", "inputs": [{"name": "src", "from": "list_accounts"}]}]
        _, flow = parse([step("list_accounts"), map_step(inner=inner)])
        self.assertFalse(flow.steps[1].map.steps[0].inputs[0].dangling)
        self.assertEqual(flow.problems, ())

    def test_bad_optional_fields_are_dropped_with_a_problem_and_the_step_stays(self) -> None:
        for bad in (0, -2, True, "5", 2.5):
            with self.subTest(max_concurrency=bad):
                status, flow = parse([step("list_accounts"), map_step(max_concurrency=bad)])
                self.assertEqual(status, "ok")
                self.assertIsNone(flow.steps[1].map.max_concurrency)
                self.assertTrue(any("accounts" in p for p in flow.problems))
        _, flow = parse([step("list_accounts"), map_step(over="later"), step("later")])
        self.assertIsNone(flow.steps[1].map.over)
        self.assertTrue(flow.problems)

    def test_bad_inner_steps_are_dropped_or_flagged_never_raised(self) -> None:
        cases = {
            "duplicate of a top-level step": [{"name": "list_accounts", "inputs": []}],
            "nested map": [{"name": "inner", "kind": "map", "steps": [{"name": "x"}]}],
            "invalid name": [{"name": "Bad Name"}],
            "duplicate inner": [{"name": "a"}, {"name": "a"}],
        }
        for label, inner in cases.items():
            with self.subTest(label):
                status, flow = parse([step("list_accounts"), map_step(inner=inner)])
                self.assertEqual(status, "ok")
                self.assertTrue(flow.problems, label)
                names = [s.name for s in flow.steps[1].map.steps]
                self.assertNotIn("inner", names)
                self.assertLessEqual(names.count("a"), 1)
                self.assertNotIn("list_accounts", names)
        _, flow = parse(
            [
                step("list_accounts"),
                map_step(inner=[{"name": "a", "inputs": [{"name": "i", "from": "ghost"}]}]),
            ]
        )
        self.assertTrue(flow.steps[1].map.steps[0].inputs[0].dangling)
        self.assertTrue(flow.problems)

    def test_more_than_twenty_inner_steps_are_cut(self) -> None:
        inner = [{"name": f"s{i}"} for i in range(25)]
        _, flow = parse([step("list_accounts"), map_step(inner=inner)])
        self.assertEqual(len(flow.steps[1].map.steps), 20)
        self.assertTrue(flow.problems)

    def test_an_inner_input_from_a_later_inner_step_is_dangling(self) -> None:
        inner = [{"name": "a", "inputs": [{"name": "i", "from": "b"}]}, {"name": "b"}]
        _, flow = parse([step("list_accounts"), map_step(inner=inner)])
        self.assertTrue(flow.steps[1].map.steps[0].inputs[0].dangling)

    def test_a_flow_without_a_map_step_is_unchanged(self) -> None:
        _, flow = parse(callrail_flow_steps())
        self.assertTrue(all(s.map is None for s in flow.steps))

    def test_a_cycle_drop_keeps_the_map_declaration(self) -> None:
        steps = [
            step("a", "b"),
            map_step("m", inner=[{"name": "x"}]),
            step("b", "m"),
        ]
        steps[1]["inputs"] = [{"name": "i", "from": "a"}]
        _, flow = parse(steps)
        self.assertTrue(any("cycle" in p for p in flow.problems))
        self.assertIsNotNone(next(s for s in flow.steps if s.name == "m").map)
