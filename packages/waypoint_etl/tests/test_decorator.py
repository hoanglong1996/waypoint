import asyncio
import json
import unittest
from typing import Dict, List, Optional, Tuple

from waypoint_etl import GroupSpec, PipelineSpec, StepSpec, audited_step, registry, wrap
from waypoint_etl.auditor import StepAuditor
from waypoint_etl.testing import assert_spec_matches

SPEC = PipelineSpec(
    name="demo",
    groups=(GroupSpec("g", "G"),),
    steps=(
        StepSpec("extract", group="g"),
        StepSpec("clean", inputs=(("rows", "extract"),)),
        StepSpec("join", inputs=(("left", "extract"), ("right", "clean"))),
    ),
)
Entry = Tuple[str, Dict[str, object], int]


class FakeStore:
    def __init__(self) -> None:
        self.records: List[Entry] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.records.append((key, record, ttl_seconds))

    def finished(self) -> List[Dict[str, object]]:
        return [r for k, r, _ in self.records if ":step:" in k]

    def keys(self, part: str) -> List[str]:
        return [k for k, _, _ in self.records if part in k]


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        registry.set_active(StepAuditor(self.store, SPEC, env="qa", ttl_seconds=60, run_id="R"))

    def tearDown(self) -> None:
        registry.clear()


class TestDecorator(Case):
    def test_returns_value_and_keeps_metadata(self) -> None:
        @audited_step("extract")
        def fetch(limit: int) -> List[int]:
            """Doc."""
            return list(range(limit))

        self.assertEqual(fetch(3), [0, 1, 2])
        self.assertEqual(fetch.__name__, "fetch")
        self.assertEqual(fetch.__doc__, "Doc.")

    def test_marker_before_and_record_after(self) -> None:
        seen: List[int] = []

        @audited_step("extract")
        def fetch() -> List[int]:
            seen.append(len(self.store.keys(":running:")))
            return [1, 2]

        fetch()
        self.assertEqual(seen, [1])
        record = self.store.finished()[0]
        self.assertEqual((record["step"], record["output"], record["index"]), ("extract", 2, 1))

    def test_input_counts_come_from_parameter_names(self) -> None:
        @audited_step("clean")
        def clean(rows: List[int], unrelated: List[int]) -> List[int]:
            return rows[:1]

        clean([1, 2, 3], [9, 9])
        self.assertEqual(self.store.finished()[0]["inputs"], {"rows": 3})

    def test_none_and_single_object_counts(self) -> None:
        @audited_step("clean")
        def clean(rows: object) -> Optional[str]:
            return None

        clean(None)
        clean("abc")
        self.assertEqual(
            [r["inputs"] for r in self.store.finished()], [{"rows": None}, {"rows": 1}]
        )
        self.assertIsNone(self.store.finished()[0]["output"])

    def test_inputs_rename(self) -> None:
        @audited_step("join", inputs={"a": "left", "b": "right"})
        def join(a: List[int], b: List[int]) -> List[int]:
            return a + b

        join([1], [2, 3])
        self.assertEqual(self.store.finished()[0]["inputs"], {"left": 1, "right": 2})

    def test_keyword_arguments(self) -> None:
        @audited_step("clean")
        def clean(rows: List[int]) -> List[int]:
            return rows

        clean(rows=[1, 2])
        self.assertEqual(self.store.finished()[0]["inputs"], {"rows": 2})

    def test_methods_skip_self(self) -> None:
        class UseCase:
            @audited_step("clean")
            def execute(self, rows: List[int]) -> int:
                return len(rows)

        self.assertEqual(UseCase().execute([1, 2]), 2)
        self.assertEqual(self.store.finished()[0]["inputs"], {"rows": 2})

    def test_exception_propagates_without_finish_record(self) -> None:
        @audited_step("extract")
        def boom() -> None:
            raise ValueError("bad")

        with self.assertRaises(ValueError):
            boom()
        self.assertEqual(len(self.store.keys(":running:")), 1)
        self.assertEqual(self.store.finished(), [])

    def test_async_step(self) -> None:
        @audited_step("clean")
        async def clean(rows: List[int]) -> List[int]:
            return rows[:1]

        self.assertEqual(asyncio.run(clean([1, 2])), [1])
        record = self.store.finished()[0]
        self.assertEqual((record["inputs"], record["output"]), ({"rows": 2}, 1))

    def test_step_missing_from_spec_is_still_recorded(self) -> None:
        @audited_step("surprise")
        def surprise() -> int:
            return 1

        surprise()
        self.assertEqual(self.store.finished()[0]["step"], "surprise")

    def test_same_step_called_twice_gets_two_indexes(self) -> None:
        @audited_step("extract")
        def fetch() -> int:
            return 1

        fetch()
        fetch()
        self.assertEqual([r["index"] for r in self.store.finished()], [1, 2])

    def test_no_item_contents_are_written(self) -> None:
        secret = ["caller-name-555-0100"]

        @audited_step("clean")
        def clean(rows: List[str]) -> List[str]:
            return rows

        clean(secret)
        self.assertNotIn("caller-name", json.dumps([r for _, r, _ in self.store.records]))

    def test_wrap_audits_an_unedited_object(self) -> None:
        class Plain:
            def execute(self, rows: List[int]) -> int:
                return len(rows)

        plain = Plain()
        wrap(plain, "execute", step="clean")
        self.assertEqual(plain.execute([1, 2, 3]), 3)
        self.assertEqual(self.store.finished()[0]["inputs"], {"rows": 3})


class TestSpecMatches(Case):
    def test_matching_and_mismatching(self) -> None:
        class Good:
            @audited_step("extract")
            def a(self) -> None: ...

            @audited_step("clean")
            def b(self) -> None: ...

            @audited_step("join")
            def c(self) -> None: ...

        assert_spec_matches(SPEC, Good())

        class Bad:
            @audited_step("extract")
            def a(self) -> None: ...

            @audited_step("other")
            def b(self) -> None: ...

        with self.assertRaises(AssertionError) as ctx:
            assert_spec_matches(SPEC, Bad)
        self.assertIn("other", str(ctx.exception))
        self.assertIn("clean", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
