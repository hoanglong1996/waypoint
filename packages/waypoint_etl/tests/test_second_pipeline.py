"""A second, unrelated pipeline adopts Waypoint using only ``waypoint_etl``."""

import unittest
from typing import Dict, List, Tuple

from waypoint_etl.auditor import StepAuditor
from waypoint_etl.spec import PipelineSpec, StepSpec

SAMPLE = PipelineSpec(
    name="sample",
    steps=(
        StepSpec("extract"),
        StepSpec("clean", inputs=(("rows", "extract"),)),
        StepSpec("load", inputs=(("rows", "clean"),), returns_nothing=True),
    ),
)


class Store:
    def __init__(self) -> None:
        self.writes: List[Tuple[str, Dict[str, object], int]] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.writes.append((key, record, ttl_seconds))


class TestSecondPipeline(unittest.TestCase):
    def test_keys_follow_the_contract_and_carry_no_callrail_names(self) -> None:
        store = Store()
        auditor = StepAuditor(store, SAMPLE, env="qa", ttl_seconds=60, run_id="20261016T020000Z")
        rows = auditor.run("extract", lambda: [1, 2, 3])
        rows = auditor.run("clean", lambda r: r[:2], rows, inputs={"rows": rows})
        auditor.run("load", lambda r: None, rows, inputs={"rows": rows})

        keys = [k for k, _, _ in store.writes]
        self.assertEqual(keys[0], "waypoint:sample:qa:20261016T020000Z:flow")
        self.assertIn("waypoint:sample:qa:20261016T020000Z:step:02-clean", keys)
        self.assertIn("waypoint:sample:qa:20261016T020000Z:running:03-load", keys)
        self.assertTrue(all(k.startswith("waypoint:sample:") for k in keys))
        self.assertNotIn("callrail", repr(store.writes))


class ManyStore(Store):
    """A store with ``write_many``: a pipeline with no map step must never call it."""

    def __init__(self) -> None:
        super().__init__()
        self.many_calls = 0

    def write_many(self, items: object, ttl_seconds: int) -> None:
        self.many_calls += 1


class TestNoMapStep(unittest.TestCase):
    """Specs 014 FR-028: a pipeline that never calls the map scopes behaves as in 0.5.0."""

    def test_a_sequential_run_writes_no_map_or_item_keys(self) -> None:
        store = ManyStore()
        auditor = StepAuditor(store, SAMPLE, env="qa", ttl_seconds=60, run_id="20261016T020000Z")
        rows = auditor.run("extract", lambda: [1, 2, 3])
        rows = auditor.run("clean", lambda r: r[:2], rows, inputs={"rows": rows})
        auditor.run("load", lambda r: None, rows, inputs={"rows": rows})
        auditor.stop()
        keys = [k for k, _, _ in store.writes]
        self.assertEqual(
            keys,
            [
                "waypoint:sample:qa:20261016T020000Z:flow",
                "waypoint:sample:qa:20261016T020000Z:running:01-extract",
                "waypoint:sample:qa:20261016T020000Z:step:01-extract",
                "waypoint:sample:qa:20261016T020000Z:running:02-clean",
                "waypoint:sample:qa:20261016T020000Z:step:02-clean",
                "waypoint:sample:qa:20261016T020000Z:running:03-load",
                "waypoint:sample:qa:20261016T020000Z:step:03-load",
            ],
        )
        self.assertEqual(store.many_calls, 0)

    def test_the_step_record_is_the_same_shape_as_before(self) -> None:
        store = ManyStore()
        auditor = StepAuditor(store, SAMPLE, env="qa", ttl_seconds=60, run_id="R1")
        auditor.run("extract", lambda: [1, 2, 3])
        record = [r for k, r, _ in store.writes if ":step:" in k][0]
        self.assertEqual(
            sorted(record),
            [
                "duration_ms",
                "env",
                "finished_at",
                "index",
                "inputs",
                "output",
                "pipeline",
                "run_id",
                "started_at",
                "step",
            ],
        )
        self.assertEqual((record["inputs"], record["output"]), ({}, 3))


if __name__ == "__main__":
    unittest.main()
