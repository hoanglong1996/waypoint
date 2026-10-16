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
