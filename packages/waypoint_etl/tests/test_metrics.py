"""``waypoint_etl.metric``: modes, validation, limits, attempts, threads, no-op cases.

Specs 013 contracts/library-api.md; spec FR-001 to FR-006, SC-002, SC-003, SC-009.
"""

import asyncio
import io
import threading
import time
import unittest
from contextlib import redirect_stdout
from typing import Any, Dict, List, Tuple

import waypoint_etl
from waypoint_etl import PipelineSpec, StepSpec, audited_step, registry
from waypoint_etl.auditor import StepAuditor
from waypoint_etl.keys import MAX_METRICS_PER_STEP, metrics_key
from waypoint_etl.metrics import MetricState, valid_name, valid_value

SPEC = PipelineSpec(
    name="demo",
    steps=(StepSpec("extract"), StepSpec("load", inputs=(("rows", "extract"),))),
)
RUN = "20261017T020000Z"


class Store:
    def __init__(self) -> None:
        self.records: List[Tuple[str, Dict[str, object], int]] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.records.append((key, record, ttl_seconds))

    def latest(self, index: int, step: str) -> Dict[str, Any]:
        key = metrics_key("demo", "qa", RUN, index, step)
        found = [r for k, r, _ in self.records if k == key]
        return dict(found[-1]) if found else {}


def start() -> Tuple[Store, StepAuditor]:
    store = Store()
    waypoint_etl.init(
        pipeline=SPEC,
        redis_url=None,
        env="qa",
        run_id=RUN,
        store=store,
        heartbeat_seconds=None,
    )
    auditor = registry.get_active()
    assert auditor is not None
    return store, auditor


def values(store: Store, index: int, step: str) -> Dict[str, Any]:
    registry.clear()  # flushes the writer
    return dict(store.latest(index, step).get("metrics", {}))


class TestMetric(unittest.TestCase):
    def setUp(self) -> None:
        registry.clear()

    def tearDown(self) -> None:
        registry.clear()

    def test_set_replaces(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            waypoint_etl.metric("rows", 10)
            waypoint_etl.metric("rows", 4)

        run()
        self.assertEqual(values(store, 1, "extract"), {"rows": 4})

    def test_add_and_max(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            for n in (1, 2, 3):
                waypoint_etl.metric("retries", n, mode="add")
            for n in (5, 9, 7):
                waypoint_etl.metric("peak", n, mode="max")

        run()
        self.assertEqual(values(store, 1, "extract"), {"retries": 6, "peak": 9})

    def test_record_has_identity_version_and_ttl(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            waypoint_etl.metric("rows", 1.5)

        run()
        registry.clear()
        key, record, ttl = [r for r in store.records if ":metrics:" in r[0]][-1]
        self.assertEqual(key, "waypoint:demo:qa:20261017T020000Z:metrics:01-extract")
        self.assertEqual(record["v"], 1)
        self.assertEqual(
            {k: record[k] for k in ("pipeline", "env", "run_id", "step", "index")},
            {"pipeline": "demo", "env": "qa", "run_id": RUN, "step": "extract", "index": 1},
        )
        self.assertRegex(str(record["updated_at"]), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(ttl, 30 * 86400)

    def test_mixed_modes_apply_the_latest_operation(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            waypoint_etl.metric("n", 5)
            waypoint_etl.metric("n", 3, mode="add")
            waypoint_etl.metric("n", 4, mode="max")
            waypoint_etl.metric("n", 1, mode="set")

        run()
        self.assertEqual(values(store, 1, "extract"), {"n": 1})

    def test_no_step_and_none_running_does_nothing(self) -> None:
        store, _ = start()
        out = io.StringIO()
        with redirect_stdout(out):
            waypoint_etl.metric("rows", 1)
        registry.clear()
        self.assertEqual([r for r in store.records if ":metrics:" in r[0]], [])
        self.assertEqual(out.getvalue(), "")

    def test_before_init_and_after_failed_init(self) -> None:
        waypoint_etl.metric("rows", 1)  # never initialised
        bad = PipelineSpec(name="Bad Name", steps=(StepSpec("a"),))
        with redirect_stdout(io.StringIO()):
            self.assertFalse(waypoint_etl.init(pipeline=bad, redis_url=None, env="qa"))
        waypoint_etl.metric("rows", 1)

    def test_explicit_step_after_it_finished_lands_on_the_same_attempt(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            waypoint_etl.metric("rows", 1)

        run()
        waypoint_etl.metric("rows", 9, step="extract")
        self.assertEqual(values(store, 1, "extract"), {"rows": 9})

    def test_explicit_step_that_never_began_is_dropped_with_one_warning(self) -> None:
        store, _ = start()
        out = io.StringIO()
        with redirect_stdout(out):
            for _ in range(3):
                waypoint_etl.metric("rows", 1, step="load")
        registry.clear()
        self.assertEqual(out.getvalue().count("has not started"), 1)
        self.assertEqual([r for r in store.records if ":metrics:" in r[0]], [])

    def test_retry_starts_a_fresh_attempt(self) -> None:
        store, _ = start()
        calls = {"n": 0}

        @audited_step("extract")
        def run() -> None:
            calls["n"] += 1
            waypoint_etl.metric("rows", calls["n"] * 10, mode="add")
            if calls["n"] == 1:
                raise ValueError("again")

        with self.assertRaises(ValueError):
            run()
        run()
        registry.clear()
        self.assertEqual(store.latest(1, "extract")["metrics"], {"rows": 10})  # failed attempt
        self.assertEqual(store.latest(2, "extract")["metrics"], {"rows": 20})  # retry from zero

    def test_invalid_input_is_dropped_with_one_warning_per_name(self) -> None:
        store, _ = start()
        out = io.StringIO()

        @audited_step("extract")
        def run() -> None:
            for bad in (True, "3", None, float("nan"), float("inf"), [1]):
                waypoint_etl.metric("rows", bad)  # type: ignore[arg-type]
                waypoint_etl.metric("rows", bad)  # type: ignore[arg-type]
            for name in ("Bad", "", "x" * 65, "has space", "dash-ed"):
                waypoint_etl.metric(name, 1)
            waypoint_etl.metric("ok", 1, mode="sum")
            waypoint_etl.metric("good", 2)

        with redirect_stdout(out):
            run()
        self.assertEqual(values(store, 1, "extract"), {"good": 2})
        self.assertEqual(out.getvalue().count("metric 'rows' dropped (value)"), 1)

    def test_unknown_mode_is_dropped_and_never_raises(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            for mode in ("sum", None, 3):
                waypoint_etl.metric("n", 1, mode=mode)  # type: ignore[arg-type]
            waypoint_etl.metric("n", 7)

        with redirect_stdout(io.StringIO()):
            run()
        self.assertEqual(values(store, 1, "extract"), {"n": 7})

    def test_non_finite_result_is_ignored(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            waypoint_etl.metric("big", 1e308, mode="add")
            waypoint_etl.metric("big", 1e308, mode="add")

        with redirect_stdout(io.StringIO()):
            run()
        self.assertEqual(values(store, 1, "extract"), {"big": 1e308})

    def test_the_21st_name_is_dropped_while_the_first_20_keep_updating(self) -> None:
        store, _ = start()
        out = io.StringIO()

        @audited_step("extract")
        def run() -> None:
            for i in range(MAX_METRICS_PER_STEP + 1):
                waypoint_etl.metric(f"m{i}", 1, mode="add")
            waypoint_etl.metric("m0", 1, mode="add")

        with redirect_stdout(out):
            run()
        got = values(store, 1, "extract")
        self.assertEqual(len(got), MAX_METRICS_PER_STEP)
        self.assertNotIn("m20", got)
        self.assertEqual(got["m0"], 2)
        self.assertEqual(out.getvalue().count("dropped (limit)"), 1)

    def test_threads_add_exactly(self) -> None:
        store, _ = start()

        @audited_step("extract")
        def run() -> None:
            def work() -> None:
                for _ in range(1000):
                    waypoint_etl.metric("n", 1, mode="add")

            # threads started inside the step do not inherit the context variable: name the step
            def named() -> None:
                for _ in range(1000):
                    waypoint_etl.metric("n", 1, mode="add", step="extract")

            threads = [threading.Thread(target=named) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            work()

        run()
        self.assertEqual(values(store, 1, "extract")["n"], 9000)

    def test_async_tasks_attach_to_their_own_running_step(self) -> None:
        store, _ = start()

        @audited_step("extract")
        async def first() -> None:
            await asyncio.sleep(0)
            waypoint_etl.metric("who", 1)

        asyncio.run(first())
        self.assertEqual(values(store, 1, "extract"), {"who": 1})

    def test_hot_loop_costs_a_dictionary_update_not_a_write(self) -> None:
        store, _ = start()
        loops = 100_000

        @audited_step("extract")
        def with_metric() -> float:
            began = time.perf_counter()
            for _ in range(loops):
                waypoint_etl.metric("n", 1, mode="add")
            return time.perf_counter() - began

        elapsed = with_metric()
        registry.clear()
        writes = len([r for r in store.records if ":metrics:" in r[0]])
        self.assertLess(elapsed, 2.0)
        self.assertLess(writes, 10)
        self.assertEqual(store.latest(1, "extract")["metrics"]["n"], loops)


class TestHelpers(unittest.TestCase):
    def test_valid_name_and_value(self) -> None:
        self.assertTrue(valid_name("rows_2"))
        self.assertFalse(valid_name("Rows"))
        self.assertFalse(valid_name(3))
        self.assertTrue(valid_value(3))
        self.assertTrue(valid_value(-0.5))
        self.assertFalse(valid_value(True))
        self.assertFalse(valid_value(float("-inf")))
        self.assertFalse(valid_value("1"))

    def test_state_reports_why_a_call_was_dropped(self) -> None:
        state = MetricState()
        self.assertEqual(state.apply((1, "s"), "Bad", 1, "set"), "name")
        self.assertEqual(state.apply((1, "s"), "a", True, "set"), "value")
        self.assertEqual(state.apply((1, "s"), "a", 1, "nope"), "mode")
        self.assertIsNone(state.apply((1, "s"), "a", 1, "set"))
        self.assertEqual(state.take_dirty(), [((1, "s"), {"a": 1})])
        self.assertEqual(state.take_dirty(), [])


if __name__ == "__main__":
    unittest.main()
