"""Declared metrics: ``Metric`` validation and the flow record. Specs 013 R5, FR-010 to FR-012."""

import io
import unittest
from contextlib import redirect_stdout
from typing import Any, Dict, List, Tuple

import waypoint_etl
from waypoint_etl import Metric, PipelineSpec, StepSpec, registry
from waypoint_etl.keys import FLOW_VERSION
from waypoint_etl.spec import validate_spec


def spec_with(*metrics: Metric) -> PipelineSpec:
    return PipelineSpec(name="demo", steps=(StepSpec("load", metrics=metrics),))


class TestMetricDeclaration(unittest.TestCase):
    def test_valid(self) -> None:
        validate_spec(
            spec_with(
                Metric("rejected", label="Rejected rows", unit="rows", warn_above=100),
                Metric("coverage", unit="%", warn_below=90),
                Metric("band", warn_below=1, warn_above=1),
                Metric("plain"),
            )
        )

    def test_invalid_declarations_are_refused(self) -> None:
        cases: Dict[str, Tuple[Metric, ...]] = {
            "bad name": (Metric("Rejected"),),
            "empty name": (Metric(""),),
            "long name": (Metric("x" * 65),),
            "duplicate": (Metric("a"), Metric("a")),
            "long label": (Metric("a", label="x" * 41),),
            "long unit": (Metric("a", unit="x" * 17),),
            "bool limit": (Metric("a", warn_above=True),),
            "nan limit": (Metric("a", warn_below=float("nan")),),
            "inf limit": (Metric("a", warn_above=float("inf")),),
            "text limit": (Metric("a", warn_above="9"),),  # type: ignore[arg-type]
            "crossed": (Metric("a", warn_below=5, warn_above=1),),
            "too many": tuple(Metric(f"m{i}") for i in range(21)),
        }
        for label, metrics in cases.items():
            with self.subTest(label), self.assertRaises(ValueError) as caught:
                validate_spec(spec_with(*metrics))
            if label in ("bad name", "duplicate", "long label"):
                self.assertIn("'load'", str(caught.exception))

    def test_twenty_is_allowed(self) -> None:
        validate_spec(spec_with(*(Metric(f"m{i}") for i in range(20))))

    def test_invalid_declaration_disables_auditing_with_a_warning(self) -> None:
        registry.clear()
        out = io.StringIO()
        with redirect_stdout(out):
            ok = waypoint_etl.init(
                pipeline=spec_with(Metric("Bad")), redis_url=None, env="qa", store=Store()
            )
        self.assertFalse(ok)
        self.assertIn("invalid pipeline spec", out.getvalue())
        registry.clear()


class Store:
    def __init__(self) -> None:
        self.records: List[Tuple[str, Dict[str, Any], int]] = []

    def write(self, key: str, record: Dict[str, Any], ttl_seconds: int) -> None:
        self.records.append((key, record, ttl_seconds))


class TestFlowRecord(unittest.TestCase):
    def tearDown(self) -> None:
        registry.clear()

    def test_flow_carries_declarations_only_where_declared(self) -> None:
        store = Store()
        spec = PipelineSpec(
            name="demo",
            steps=(
                StepSpec("read"),
                StepSpec(
                    "load",
                    inputs=(("rows", "read"),),
                    metrics=(
                        Metric("rejected", label="Rejected rows", unit="rows", warn_above=100),
                        Metric("coverage", warn_below=90.5),
                        Metric("plain"),
                    ),
                ),
            ),
        )
        waypoint_etl.init(
            pipeline=spec, redis_url=None, env="qa", store=store, heartbeat_seconds=None
        )
        flow = [r for k, r, _ in store.records if k.endswith(":flow")][0]
        self.assertEqual(flow["v"], FLOW_VERSION)
        self.assertEqual(FLOW_VERSION, 1)
        read, load = flow["steps"]
        self.assertNotIn("metrics", read)
        self.assertEqual(
            load["metrics"],
            [
                {"name": "rejected", "label": "Rejected rows", "unit": "rows", "warn_above": 100},
                {"name": "coverage", "warn_below": 90.5},
                {"name": "plain"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
