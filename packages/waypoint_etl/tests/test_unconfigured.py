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

    def test_events_before_init_do_nothing_and_say_nothing(self) -> None:
        import io
        from contextlib import redirect_stdout

        import waypoint_etl

        out = io.StringIO()
        with redirect_stdout(out):
            self.assertIsNone(waypoint_etl.log("a", rows=1))
            self.assertIsNone(waypoint_etl.warn("b", step="extract"))
            self.assertIsNone(waypoint_etl.error("c"))
        self.assertEqual(out.getvalue(), "")

    def test_events_after_a_failed_init_do_nothing(self) -> None:
        import waypoint_etl

        self.assertFalse(waypoint_etl.init(pipeline=SPEC, redis_url=None, env="qa"))
        self.assertIsNone(waypoint_etl.log("still fine"))

    def test_events_after_clear_do_nothing(self) -> None:
        import waypoint_etl

        registry.set_active(StepAuditor(RaisingStore(), SPEC, env="qa", ttl_seconds=1))
        registry.clear()
        self.assertIsNone(waypoint_etl.log("gone"))

    def test_bad_arguments_never_raise(self) -> None:
        import waypoint_etl

        registry.set_active(StepAuditor(RaisingStore(), SPEC, env="qa", ttl_seconds=1))
        for message in (None, 5, object()):
            waypoint_etl.log(message)  # type: ignore[arg-type]
        waypoint_etl.log("x", level=None)  # type: ignore[arg-type]
        waypoint_etl.log("x", **{"bad name": object()})


if __name__ == "__main__":
    unittest.main()
