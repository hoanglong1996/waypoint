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


if __name__ == "__main__":
    unittest.main()
