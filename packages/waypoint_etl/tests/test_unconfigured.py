import unittest
from typing import Dict, List

from waypoint_etl import PipelineSpec, StepSpec, audited_step, registry
from waypoint_etl.auditor import StepAuditor

SPEC = PipelineSpec(name="demo", steps=(StepSpec("extract"),))


class RaisingStore:
    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        raise ConnectionError("redis down")


class TestUnconfigured(unittest.TestCase):
    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_step_behaves_like_the_original(self) -> None:
        @audited_step("extract")
        def fetch(n: int) -> List[int]:
            return list(range(n))

        self.assertEqual(fetch(2), [0, 1])
        self.assertIsNone(registry.get_active())

    def test_original_exception_is_untouched(self) -> None:
        @audited_step("extract")
        def boom() -> None:
            raise KeyError("x")

        with self.assertRaises(KeyError):
            boom()

    def test_store_failure_never_changes_the_result(self) -> None:
        registry.set_active(StepAuditor(RaisingStore(), SPEC, env="qa", ttl_seconds=1))

        @audited_step("extract")
        def fetch() -> List[int]:
            return [1, 2]

        self.assertEqual(fetch(), [1, 2])


if __name__ == "__main__":
    unittest.main()
