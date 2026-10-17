"""``map_step()`` and ``item()``: attribution in threads and asyncio, no-op cases. Specs 014 library-api.md."""

import asyncio
import io
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional, Sequence, Tuple

import waypoint_etl
from waypoint_etl import MapStepSpec, PipelineSpec, StepSpec, audited_step, registry
from waypoint_etl.auditor import StepAuditor
from waypoint_etl.keys import failed_key, item_key, map_key, marker_key, step_key

RUN = "20261017T020000Z"

SPEC = PipelineSpec(
    name="demo",
    steps=(
        StepSpec("list_accounts"),
        MapStepSpec(
            "accounts",
            over="list_accounts",
            max_concurrency=5,
            steps=(
                StepSpec("fetch", inputs=(("rows", "list_accounts"),)),
                StepSpec("transform", inputs=(("rows", "fetch"),)),
                StepSpec("load", inputs=(("rows", "transform"),)),
            ),
        ),
        StepSpec("publish", inputs=(("done", "accounts"),)),
    ),
)


class Store:
    def __init__(self) -> None:
        self.records: List[Tuple[str, Dict[str, Any], int]] = []
        self.fail = False

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.records.append((key, dict(record), ttl_seconds))

    def write_many(self, items: Sequence[Tuple[str, Dict[str, object]]], ttl_seconds: int) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        for key, record in items:
            self.records.append((key, dict(record), ttl_seconds))

    def latest(self, key: str) -> Optional[Dict[str, Any]]:
        found = [r for k, r, _ in self.records if k == key]
        return found[-1] if found else None

    def keys(self, part: str) -> List[str]:
        return sorted({k for k, _, _ in self.records if f":{part}:" in k})

    def item(self, key: str) -> Dict[str, Any]:
        record = self.latest(item_key("demo", "qa", RUN, "accounts", key))
        assert record is not None, key
        return record

    def aggregate(self) -> Dict[str, Any]:
        record = self.latest(map_key("demo", "qa", RUN, "accounts"))
        assert record is not None
        return record


@audited_step("list_accounts")
def list_accounts(n: int) -> List[int]:
    return list(range(n))


@audited_step("fetch")
def fetch(rows: List[int]) -> List[int]:
    return rows


@audited_step("transform")
def transform(rows: List[int]) -> List[int]:
    return rows


@audited_step("load")
def load(rows: List[int]) -> List[int]:
    return rows


def process(n: int, key: Optional[str] = None) -> None:
    """One pass: ``n`` rows through fetch, transform and load."""
    with waypoint_etl.item(key if key is not None else f"k{n}"):
        load(transform(fetch([0] * n)))


def start() -> Tuple[Store, StepAuditor]:
    store = Store()
    waypoint_etl.init(
        pipeline=SPEC, redis_url=None, env="qa", run_id=RUN, store=store, heartbeat_seconds=None
    )
    auditor = registry.get_active()
    assert auditor is not None
    return store, auditor


class TestSequentialLoop(unittest.TestCase):
    def tearDown(self) -> None:
        registry.clear()

    def test_a_plain_loop(self) -> None:
        store, _ = start()
        accounts = list_accounts(10)
        with waypoint_etl.map_step("accounts"):
            for n in accounts:
                process(n + 1)
        registry.clear()
        for n in range(10):
            record = store.item(f"k{n + 1}")
            self.assertEqual(record["state"], "done")
            self.assertEqual([s["step"] for s in record["steps"]], ["fetch", "transform", "load"])
            self.assertEqual(record["steps"][0]["inputs"], {"rows": n + 1})
            self.assertEqual(record["steps"][2]["output"], n + 1)
        aggregate = store.aggregate()
        self.assertEqual(
            aggregate["counts"], {"started": 10, "running": 0, "done": 10, "failed": 0}
        )
        self.assertIsNotNone(aggregate["ended_at"])
        self.assertEqual(aggregate["index"], 2)  # list_accounts was step 1
        self.assertEqual(aggregate["inner"]["fetch"]["done"], 10)

    def test_the_map_step_is_an_ordinary_step_at_run_level(self) -> None:
        store, _ = start()
        list_accounts(4)
        with waypoint_etl.map_step("accounts"):
            for n in range(4):
                process(n + 1)
        registry.clear()
        self.assertEqual(
            store.latest(marker_key("demo", "qa", RUN, 2, "accounts"))["step"], "accounts"  # type: ignore[index]
        )
        record = store.latest(step_key("demo", "qa", RUN, 2, "accounts"))
        assert record is not None
        self.assertEqual(record["output"], 4)  # items started
        self.assertEqual(record["inputs"], {"list_accounts": 4})  # the `over` source's count
        self.assertIn("duration_ms", record)
        self.assertEqual(store.keys("failed"), [])
        # the inner steps wrote no run-level records
        self.assertEqual(
            sorted(k.rsplit(":", 1)[1] for k in store.keys("step")),
            ["01-list_accounts", "02-accounts"],
        )
        self.assertEqual(
            sorted(k.rsplit(":", 1)[1] for k in store.keys("running")),
            ["01-list_accounts", "02-accounts"],
        )

    def test_a_later_step_gets_the_next_index(self) -> None:
        store, auditor = start()
        with waypoint_etl.map_step("accounts"):
            process(2)
        index = auditor.begin("publish")
        self.assertEqual(index, 2)

    def test_an_item_that_fails_is_recorded_and_the_loop_goes_on(self) -> None:
        store, _ = start()

        def boom(rows: List[int]) -> List[int]:
            raise ValueError("bad date")

        failing = audited_step("transform")(boom)
        with waypoint_etl.map_step("accounts"):
            for n in range(1, 4):
                try:
                    with waypoint_etl.item(f"acct-{n}"):
                        rows = fetch([0] * n)
                        (failing if n == 2 else transform)(rows)
                except ValueError:
                    pass
        registry.clear()
        record = store.item("acct-2")
        self.assertEqual(record["state"], "failed")
        self.assertEqual([s["state"] for s in record["steps"]], ["done", "failed"])
        self.assertEqual(record["steps"][1]["error"]["type"], "ValueError")
        self.assertEqual(store.item("acct-1")["state"], "done")
        aggregate = store.aggregate()
        self.assertEqual(aggregate["counts"], {"started": 3, "running": 0, "done": 2, "failed": 1})
        self.assertEqual(
            aggregate["failed_items"],
            [{"key": "acct-2", "step": "transform", "error_type": "ValueError"}],
        )
        # the block ended normally: an ordinary finish record, no failure item
        self.assertIsNotNone(store.latest(step_key("demo", "qa", RUN, 1, "accounts")))
        self.assertEqual(store.keys("failed"), [])

    def test_an_exception_through_map_step_writes_the_failure_item_and_propagates(self) -> None:
        store, _ = start()
        with self.assertRaises(RuntimeError) as caught:
            with waypoint_etl.map_step("accounts"):
                process(2)
                raise RuntimeError("the loop broke")
        self.assertEqual(str(caught.exception), "the loop broke")
        registry.clear()
        failure = store.latest(failed_key("demo", "qa", RUN, 1, "accounts"))
        assert failure is not None
        self.assertEqual(failure["error"]["type"], "RuntimeError")
        self.assertIsNone(store.latest(step_key("demo", "qa", RUN, 1, "accounts")))
        self.assertIsNotNone(store.latest(map_key("demo", "qa", RUN, "accounts")))  # still written
        self.assertIsNotNone(store.aggregate()["ended_at"])

    def test_an_exception_through_item_propagates_and_fails_the_item(self) -> None:
        store, _ = start()
        with waypoint_etl.map_step("accounts"):
            with self.assertRaises(KeyError):
                with waypoint_etl.item("a"):
                    fetch([1])
                    raise KeyError("x")
        registry.clear()
        record = store.item("a")
        self.assertEqual(record["state"], "failed")
        self.assertEqual(
            record["error"]["type"], "KeyError"
        )  # no inner step failed: an item-level error
        self.assertEqual(store.aggregate()["failed_items"][0]["step"], "fetch")

    def test_zero_items_is_a_finished_map_step(self) -> None:
        store, _ = start()
        with waypoint_etl.map_step("accounts"):
            pass
        registry.clear()
        self.assertEqual(store.aggregate()["counts"]["started"], 0)
        record = store.latest(step_key("demo", "qa", RUN, 1, "accounts"))
        assert record is not None
        self.assertEqual(record["output"], 0)

    def test_the_aggregate_is_written_while_the_block_is_open(self) -> None:
        store, auditor = start()
        with waypoint_etl.map_step("accounts"):
            with waypoint_etl.item("a"):
                fetch([1])
                auditor.flush_events()
                aggregate = store.aggregate()
                self.assertEqual(aggregate["counts"]["running"], 1)
                self.assertIsNone(aggregate["ended_at"])
                self.assertEqual(store.item("a")["state"], "running")


class TestParallelItems(unittest.TestCase):
    def tearDown(self) -> None:
        registry.clear()

    def check(self, store: Store, count: int) -> None:
        for n in range(1, count + 1):
            record = store.item(f"k{n}")
            self.assertEqual(record["state"], "done", n)
            self.assertEqual([s["step"] for s in record["steps"]], ["fetch", "transform", "load"])
            for step in record["steps"]:
                self.assertEqual(step["inputs"], {"rows": n}, (n, step["step"]))
                self.assertEqual(step["output"], n)

    def test_a_thread_pool_never_mixes_items_up(self) -> None:
        for _ in range(20):
            store, _auditor = start()
            with waypoint_etl.map_step("accounts"):
                with ThreadPoolExecutor(5) as pool:
                    list(pool.map(process, range(1, 51)))
            registry.clear()
            self.check(store, 50)
            self.assertEqual(
                store.aggregate()["counts"], {"started": 50, "running": 0, "done": 50, "failed": 0}
            )

    def test_asyncio_tasks_never_mix_items_up(self) -> None:
        async def process_async(n: int) -> None:
            async with waypoint_etl.item(f"k{n}"):
                await asyncio.sleep(0)
                rows = fetch([0] * n)
                await asyncio.sleep(0)
                load(transform(rows))

        async def main() -> None:
            async with waypoint_etl.map_step("accounts"):
                await asyncio.gather(*(process_async(n) for n in range(1, 21)))

        for _ in range(10):
            store, _auditor = start()
            asyncio.run(main())
            registry.clear()
            self.check(store, 20)

    def test_sync_with_in_coroutines(self) -> None:
        async def process_sync_with(n: int) -> None:
            with waypoint_etl.item(f"k{n}"):
                await asyncio.sleep(0)
                load(transform(fetch([0] * n)))

        async def main() -> None:
            with waypoint_etl.map_step("accounts"):
                await asyncio.gather(*(process_sync_with(n) for n in range(1, 11)))

        store, _auditor = start()
        asyncio.run(main())
        registry.clear()
        self.check(store, 10)

    def test_the_item_finds_the_one_open_block_from_a_worker_thread(self) -> None:
        store, _ = start()
        with waypoint_etl.map_step("accounts"):
            worker = threading.Thread(target=process, args=(3,))
            worker.start()
            worker.join()
        registry.clear()
        self.assertEqual(store.item("k3")["steps"][0]["inputs"], {"rows": 3})

    def test_an_explicit_map_name(self) -> None:
        store, _ = start()
        with waypoint_etl.map_step("accounts"):
            worker = threading.Thread(target=lambda: self._named("k7"))
            worker.start()
            worker.join()
        registry.clear()
        self.assertEqual(store.item("k7")["state"], "done")

    def _named(self, key: str) -> None:
        with waypoint_etl.item(key, map="accounts"):
            fetch([1])

    def test_items_in_one_thread_do_not_see_each_other(self) -> None:
        store, _ = start()
        with waypoint_etl.map_step("accounts"):
            with waypoint_etl.item("outer"):
                fetch([1])
                with waypoint_etl.item(
                    "inner"
                ):  # a new item replaces the context, then restores it
                    fetch([1, 2])
                transform([1])
        registry.clear()
        self.assertEqual([s["step"] for s in store.item("outer")["steps"]], ["fetch", "transform"])
        self.assertEqual([s["step"] for s in store.item("inner")["steps"]], ["fetch"])


class TestNothingRecorded(unittest.TestCase):
    def tearDown(self) -> None:
        registry.clear()

    def test_item_with_no_open_block_records_nothing_and_warns_once(self) -> None:
        store, _ = start()
        out = io.StringIO()
        with redirect_stdout(out):
            for _ in range(3):
                with waypoint_etl.item("x"):
                    pass
        registry.clear()
        self.assertEqual(store.keys("item"), [])
        self.assertEqual(out.getvalue().count("found no open map step"), 1)

    def test_an_unknown_map_name_records_nothing(self) -> None:
        store, _ = start()
        out = io.StringIO()
        with redirect_stdout(out):
            with waypoint_etl.map_step("nope"):
                with waypoint_etl.item("x"):
                    pass
            with waypoint_etl.map_step("list_accounts"):  # a step, but not a map step
                pass
        registry.clear()
        self.assertEqual(store.keys("map"), [])
        self.assertEqual(store.keys("item"), [])
        self.assertEqual(store.keys("running"), [])
        self.assertIn("is not a map step", out.getvalue())

    def test_an_explicit_name_that_is_not_open_records_nothing(self) -> None:
        store, _ = start()
        out = io.StringIO()
        with redirect_stdout(out):
            with waypoint_etl.map_step("accounts"):
                with waypoint_etl.item("x", map="other"):
                    pass
        registry.clear()
        self.assertEqual(store.keys("item"), [])

    def test_a_map_step_opened_twice_records_the_inner_one_as_nothing(self) -> None:
        store, _ = start()
        out = io.StringIO()
        with redirect_stdout(out):
            with waypoint_etl.map_step("accounts"):
                with waypoint_etl.map_step("accounts"):
                    process(2)
        registry.clear()
        self.assertEqual(len(store.keys("running")), 1)
        self.assertIn("already open", out.getvalue())

    def test_a_duplicate_key_runs_its_steps_but_records_nothing_at_run_level(self) -> None:
        store, _ = start()
        out = io.StringIO()
        calls: List[int] = []
        with redirect_stdout(out):
            with waypoint_etl.map_step("accounts"):
                process(2, "dup")
                with waypoint_etl.item("dup"):
                    calls.append(len(transform(fetch([0, 0, 0]))))  # runs, returns what it should
                    waypoint_etl.log("ignored")
                    waypoint_etl.metric("n", 1, step="fetch")
        registry.clear()
        self.assertEqual(calls, [3])
        self.assertEqual(
            sorted(k.rsplit(":", 1)[1] for k in store.keys("running")), ["01-accounts"]
        )
        self.assertEqual(store.keys("failed"), [])
        self.assertEqual(store.aggregate()["counts"]["started"], 1)
        self.assertEqual(
            store.item("dup")["steps"][0]["inputs"], {"rows": 2}
        )  # the first pass stays
        self.assertEqual(out.getvalue().count("started twice"), 1)

    def test_an_exception_in_a_duplicate_pass_propagates(self) -> None:
        start()
        with redirect_stdout(io.StringIO()):
            with waypoint_etl.map_step("accounts"):
                process(1, "dup")
                with self.assertRaises(ZeroDivisionError):
                    with waypoint_etl.item("dup"):
                        1 / 0  # noqa: B018

    def test_without_init_everything_is_a_no_op(self) -> None:
        registry.clear()
        results: List[int] = []
        with waypoint_etl.map_step("accounts"):
            with waypoint_etl.item("a"):
                results.append(len(fetch([1, 2])))
        self.assertEqual(results, [2])

    def test_a_store_that_is_down_changes_nothing_for_the_pipeline(self) -> None:
        store, _ = start()
        store.fail = True
        store.records.clear()  # the flow record was written before the store went down
        out = io.StringIO()
        results: List[int] = []
        with redirect_stdout(out):
            with waypoint_etl.map_step("accounts"):
                for n in range(1, 6):
                    with waypoint_etl.item(f"k{n}"):
                        results.append(len(load(transform(fetch([0] * n)))))
        self.assertEqual(results, [1, 2, 3, 4, 5])
        with redirect_stdout(out):
            registry.clear()
        self.assertEqual(store.records, [])

    def test_a_failed_init_leaves_the_scopes_inert(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertFalse(
                waypoint_etl.init(pipeline=SPEC, redis_url=None, env="qa")
            )  # no Redis URL
            with waypoint_etl.map_step("accounts"):
                with waypoint_etl.item("a"):
                    fetch([1])


class TestScopeObjects(unittest.TestCase):
    def tearDown(self) -> None:
        registry.clear()

    def test_a_scope_is_reusable_state_free_after_exit(self) -> None:
        store, _ = start()
        scope = waypoint_etl.map_step("accounts")
        with scope:
            process(1)
        with scope:  # entering again opens a new block
            process(2)
        registry.clear()
        self.assertEqual(len(store.keys("running")), 2)  # two ordinary steps: attempts 1 and 2

    def test_context_variables_are_restored_after_the_blocks(self) -> None:
        from waypoint_etl.events import current_step
        from waypoint_etl.maps import current_item, current_map

        start()
        with waypoint_etl.map_step("accounts"):
            self.assertEqual(current_map.get(), "accounts")
            self.assertEqual(current_step.get(), "accounts")
            with waypoint_etl.item("a"):
                self.assertIsNotNone(current_item.get())
            self.assertIsNone(current_item.get())
        self.assertIsNone(current_map.get())
        self.assertIsNone(current_step.get())


if __name__ == "__main__":
    unittest.main()
