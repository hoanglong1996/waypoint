"""A step that raises: a failure item is written and the exception reaches the caller unchanged.

Contract: specs/011-step-failure-errors/contracts/{redis-keys,library-api}.md
"""

import asyncio
import io
import json
import traceback
import unittest
from contextlib import redirect_stdout
from typing import Dict, List, Optional, Tuple

from waypoint_etl import PipelineSpec, StepSpec, audited_step, registry
from waypoint_etl.auditor import StepAuditor

SPEC = PipelineSpec(
    name="demo",
    steps=(StepSpec("extract"), StepSpec("clean", inputs=(("rows", "extract"),))),
)
Entry = Tuple[str, Dict[str, object], int]


class Store:
    def __init__(self, fail_on: Optional[str] = None) -> None:
        self.records: List[Entry] = []
        self.fail_on = fail_on

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        if self.fail_on is not None and self.fail_on in key:
            raise ConnectionError("redis down")
        self.records.append((key, record, ttl_seconds))

    def failures(self) -> List[Entry]:
        return [e for e in self.records if ":failed:" in e[0]]

    def keys(self, part: str) -> List[str]:
        return [k for k, _, _ in self.records if part in k]


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store()
        self.use(self.store)

    def use(self, store: Store, **kw: object) -> None:
        registry.set_active(
            StepAuditor(store, SPEC, env="qa", ttl_seconds=60, run_id="R", **kw)  # type: ignore[arg-type]
        )

    def tearDown(self) -> None:
        registry.clear()


class TestFailureRecord(Case):
    def test_decorated_step_writes_one_failure_item_and_reraises_the_same_exception(self) -> None:
        raised = ValueError("bad row")

        @audited_step("extract")
        def fetch() -> None:
            raise raised

        with self.assertRaises(ValueError) as ctx:
            fetch()
        self.assertIs(ctx.exception, raised)
        self.assertEqual(ctx.exception.args, ("bad row",))
        ((key, record, ttl),) = self.store.failures()
        self.assertEqual(key, "waypoint:demo:qa:R:failed:01-extract")
        self.assertEqual(ttl, 60)  # the run's ttl
        self.assertEqual(
            {k: record[k] for k in ("v", "pipeline", "env", "run_id", "step", "index")},
            {"v": 1, "pipeline": "demo", "env": "qa", "run_id": "R", "step": "extract", "index": 1},
        )
        marker = json.loads(json.dumps(self.store.keys(":running:")))  # the marker stays in place
        self.assertEqual(len(marker), 1)
        self.assertEqual(self.store.keys(":step:"), [])
        error = record["error"]
        assert isinstance(error, dict)
        self.assertEqual((error["type"], error["message"]), ("ValueError", "bad row"))
        self.assertIn("in fetch", str(error["traceback"]))
        self.assertRegex(str(record["failed_at"]), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_started_at_is_the_start_markers_value(self) -> None:
        @audited_step("extract")
        def fetch() -> None:
            raise ValueError("x")

        with self.assertRaises(ValueError):
            fetch()
        marker = next(r for k, r, _ in self.store.records if ":running:" in k)
        (item,) = self.store.failures()
        self.assertEqual(item[1]["started_at"], marker["started_at"])

    def test_exception_is_identical_with_and_without_monitoring(self) -> None:
        def boom() -> None:
            try:
                raise KeyError("inner")
            except KeyError as inner:
                raise ValueError("outer") from inner

        def frames(exc: BaseException) -> List[str]:
            return [f"{f.name}:{f.line}" for f in traceback.extract_tb(exc.__traceback__)]

        with self.assertRaises(ValueError) as plain:
            boom()
        wrapped = audited_step("extract")(boom)
        with self.assertRaises(ValueError) as watched:
            wrapped()
        self.assertEqual(type(watched.exception), type(plain.exception))
        self.assertEqual(watched.exception.args, plain.exception.args)
        self.assertIs(type(watched.exception.__cause__), KeyError)
        self.assertEqual(frames(watched.exception)[-2:], frames(plain.exception)[-2:])
        self.assertEqual(len(self.store.failures()), 1)

    def test_async_step_is_recorded_and_reraised_the_same_way(self) -> None:
        raised = RuntimeError("async boom")

        @audited_step("extract")
        async def fetch() -> None:
            await asyncio.sleep(0)
            raise raised

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(fetch())
        self.assertIs(ctx.exception, raised)
        ((key, record, _),) = self.store.failures()
        self.assertEqual(key, "waypoint:demo:qa:R:failed:01-extract")
        self.assertEqual(record["error"]["type"], "RuntimeError")  # type: ignore[index]

    def test_auditor_run_records_the_same_way(self) -> None:
        auditor = StepAuditor(self.store, SPEC, env="qa", ttl_seconds=60, run_id="R")
        raised = ValueError("via run")

        def boom() -> None:
            raise raised

        with self.assertRaises(ValueError) as ctx:
            auditor.run("extract", boom)
        self.assertIs(ctx.exception, raised)
        self.assertEqual(len(self.store.failures()), 1)

    def test_a_returning_step_is_unchanged(self) -> None:
        @audited_step("extract")
        def fetch() -> List[int]:
            return [1, 2]

        self.assertEqual(fetch(), [1, 2])
        self.assertEqual(self.store.failures(), [])
        ((key, record, _),) = [e for e in self.store.records if ":step:" in e[0]]
        self.assertEqual(key, "waypoint:demo:qa:R:step:01-extract")
        # 0.4.0 adds the optional started_at and duration_ms (specs/012); nothing is removed
        self.assertEqual(
            set(record),
            {
                "pipeline",
                "run_id",
                "env",
                "step",
                "index",
                "inputs",
                "output",
                "finished_at",
                "started_at",
                "duration_ms",
            },
        )

    def test_a_retry_has_a_higher_index_and_its_own_key(self) -> None:
        @audited_step("extract")
        def fetch() -> None:
            raise ValueError("again")

        for _ in range(2):
            with self.assertRaises(ValueError):
                fetch()
        self.assertEqual(
            [k for k, _, _ in self.store.failures()],
            ["waypoint:demo:qa:R:failed:01-extract", "waypoint:demo:qa:R:failed:02-extract"],
        )

    def test_without_an_active_auditor_the_step_is_the_plain_function(self) -> None:
        registry.clear()

        @audited_step("extract")
        def fetch() -> None:
            raise ValueError("plain")

        with self.assertRaises(ValueError):
            fetch()
        self.assertEqual(self.store.records, [])

    def test_successful_records_equal_the_previous_version_layout(self) -> None:
        # 0.2.x wrote exactly these three kinds of item for a returning step
        @audited_step("extract")
        def fetch() -> List[int]:
            return [1]

        fetch()
        kinds = sorted(k.split(":")[4] for k, _, _ in self.store.records)
        self.assertEqual(kinds, ["flow", "running", "step"])


class TestNeverChangesTheOutcome(Case):
    def test_a_store_that_is_down_leaves_the_exception_alone_and_warns(self) -> None:
        self.use(Store(fail_on=":"))

        @audited_step("extract")
        def fetch() -> None:
            raise ValueError("original")

        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(ValueError) as ctx:
            fetch()
        self.assertEqual(str(ctx.exception), "original")
        self.assertIn("Warning: Waypoint failure record failed for extract", out.getvalue())

    def test_only_the_failure_write_failing_is_survived(self) -> None:
        store = Store(fail_on=":failed:")
        self.use(store)

        @audited_step("extract")
        def fetch() -> None:
            raise ValueError("original")

        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            fetch()
        self.assertEqual(len(store.keys(":running:")), 1)

    def test_an_exception_that_cannot_be_printed_is_still_recorded_and_reraised(self) -> None:
        class Bad(Exception):
            def __str__(self) -> str:
                raise RuntimeError("no str")

        @audited_step("extract")
        def fetch() -> None:
            raise Bad()

        with self.assertRaises(Bad):
            fetch()
        ((_, record, _),) = self.store.failures()
        self.assertEqual(record["error"]["message"], "<unprintable>")  # type: ignore[index]

    def test_a_cleaning_function_that_raises_never_replaces_the_step_error(self) -> None:
        def broken(_: str) -> str:
            raise RuntimeError("cleaner bug")

        self.use(self.store, redact=broken)

        @audited_step("extract")
        def fetch() -> None:
            raise ValueError("original")

        with self.assertRaises(ValueError) as ctx:
            fetch()
        self.assertEqual(str(ctx.exception), "original")
        (item,) = self.store.failures()
        self.assertNotIn("message", item[1]["error"])  # type: ignore[arg-type]

    def test_building_the_error_failing_never_replaces_the_step_error(self) -> None:
        from unittest.mock import patch

        @audited_step("extract")
        def fetch() -> None:
            raise ValueError("original")

        with patch("waypoint_etl.auditor.build_error", side_effect=RuntimeError("bug")):
            with redirect_stdout(io.StringIO()), self.assertRaises(ValueError) as ctx:
                fetch()
        self.assertEqual(str(ctx.exception), "original")

    def test_exit_requests_are_not_failures(self) -> None:
        @audited_step("extract")
        def stop() -> None:
            raise SystemExit(3)

        @audited_step("clean")
        def interrupt() -> None:
            raise KeyboardInterrupt()

        with self.assertRaises(SystemExit):
            stop()
        with self.assertRaises(KeyboardInterrupt):
            interrupt()
        self.assertEqual(self.store.failures(), [])

    def test_a_cancelled_async_step_is_not_a_failure(self) -> None:
        @audited_step("extract")
        async def wait() -> None:
            await asyncio.sleep(10)

        async def main() -> None:
            task = asyncio.ensure_future(wait())
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(main())
        self.assertEqual(self.store.failures(), [])


if __name__ == "__main__":
    unittest.main()
