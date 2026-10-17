"""Author-sent events: building one (limits, privacy) and which step it belongs to.

Contract: specs/012-duration-and-run-events/contracts/library-api.md
"""

import asyncio
import json
import threading
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import waypoint_etl
from waypoint_etl import PipelineSpec, StepSpec, audited_step, registry
from waypoint_etl.auditor import StepAuditor
from waypoint_etl.events import build_event

NOW = datetime(2026, 10, 17, 2, 3, 41, 482000, tzinfo=timezone.utc)
SPEC = PipelineSpec(
    name="demo",
    steps=(StepSpec("extract"), StepSpec("load", inputs=(("rows", "extract"),))),
)


def build(message: str = "hello", **kw: Any) -> Dict[str, object]:
    kw.setdefault("n", 1)
    kw.setdefault("now", NOW)
    return build_event(message, **kw)


class TestBuildEvent(unittest.TestCase):
    def test_shape(self) -> None:
        event = build("Loaded batch 3", level="warning", step="load", fields={"rows": 1200})
        self.assertEqual(
            event,
            {
                "v": 1,
                "n": 1,
                "ts": "2026-10-17T02:03:41.482Z",
                "level": "warning",
                "step": "load",
                "message": "Loaded batch 3",
                "fields": {"rows": 1200},
            },
        )

    def test_optional_parts_are_absent_not_null(self) -> None:
        event = build()
        self.assertEqual(set(event), {"v", "n", "ts", "level", "message"})

    def test_unknown_levels_become_info(self) -> None:
        for level in ("debug", "", "ERROR", "warn"):
            with self.subTest(level=level):
                self.assertEqual(build(level=level)["level"], "info")
        for level in ("info", "warning", "error"):
            self.assertEqual(build(level=level)["level"], level)

    def test_message_is_cut_to_300_characters(self) -> None:
        self.assertEqual(len(str(build("x" * 900)["message"])), 300)

    def test_at_most_ten_fields(self) -> None:
        fields = {f"f{i}": i for i in range(15)}
        self.assertEqual(len(build(fields=fields)["fields"]), 10)  # type: ignore[arg-type]

    def test_field_names_must_match_the_pattern(self) -> None:
        fields = {"ok_1.x-y": 1, "bad name": 2, "": 3, "x" * 41: 4, "ünï": 5, 7: 6}  # type: ignore[dict-item]
        self.assertEqual(build(fields=fields)["fields"], {"ok_1.x-y": 1})

    def test_value_types(self) -> None:
        fields = {
            "int": 3,
            "float": 2.5,
            "text": "short",
            "long": "y" * 250,
            "flag": True,
            "none": None,
            "list": [1],
            "dict": {"a": 1},
            "nan": float("nan"),
            "inf": float("inf"),
        }
        got = build(fields=fields)["fields"]
        self.assertEqual(got, {"int": 3, "float": 2.5, "text": "short", "long": "y" * 100})

    def test_no_usable_field_means_no_fields_key(self) -> None:
        self.assertNotIn("fields", build(fields={"bad name": 1, "flag": True}))

    def test_numbers_increase_with_n(self) -> None:
        self.assertEqual([build(n=n)["n"] for n in (1, 2, 3)], [1, 2, 3])

    def test_timestamp_is_utc_with_milliseconds(self) -> None:
        local = datetime.fromisoformat("2026-10-17T09:03:41.005+07:00")
        self.assertEqual(build(now=local)["ts"], "2026-10-17T02:03:41.005Z")

    def test_a_step_name_must_be_a_reasonable_string(self) -> None:
        self.assertNotIn("step", build(step=""))
        self.assertNotIn("step", build(step="s" * 201))
        self.assertEqual(build(step="s" * 200)["step"], "s" * 200)


class TestPrivacy(unittest.TestCase):
    """One setting covers every free text the library stores (spec FR-022, SC-010)."""

    def test_capture_off_leaves_out_the_message_and_text_values_but_keeps_numbers(self) -> None:
        event = build(
            "secret-marker 123",
            capture_message=False,
            fields={"note": "secret-marker", "rows": 42, "ratio": 0.5},
            step="load",
        )
        self.assertNotIn("message", event)
        self.assertEqual(event["fields"], {"rows": 42, "ratio": 0.5})
        self.assertEqual((event["step"], event["level"]), ("load", "info"))
        self.assertNotIn("secret-marker", json.dumps(event))

    def test_capture_off_with_only_text_fields_has_no_fields(self) -> None:
        event = build("m", capture_message=False, fields={"note": "secret"})
        self.assertNotIn("fields", event)
        self.assertNotIn("secret", json.dumps(event))

    def test_redact_cleans_the_message_and_each_text_value(self) -> None:
        def clean(text: str) -> str:
            return text.replace("jane@example.com", "<email>")

        event = build(
            "mail to jane@example.com failed",
            redact=clean,
            fields={"who": "jane@example.com", "n": 1},
        )
        self.assertEqual(event["message"], "mail to <email> failed")
        self.assertEqual(event["fields"], {"who": "<email>", "n": 1})

    def test_redact_runs_before_the_cut(self) -> None:
        event = build("a" * 290, redact=lambda t: t + "b" * 100)
        self.assertEqual(len(str(event["message"])), 300)
        event = build("m", fields={"x": "a"}, redact=lambda t: t + "b" * 500)
        self.assertEqual(len(str(event["fields"]["x"])), 100)  # type: ignore[index]

    def test_a_redact_that_raises_or_returns_junk_drops_that_text(self) -> None:
        def boom(text: str) -> str:
            raise ValueError(text)

        event = build("secret", redact=boom, fields={"a": "secret", "n": 5})
        self.assertNotIn("message", event)
        self.assertEqual(event["fields"], {"n": 5})
        event = build("secret", redact=lambda t: 5, fields={"a": "secret"})  # type: ignore[arg-type,return-value]
        self.assertNotIn("message", event)
        self.assertNotIn("fields", event)
        self.assertNotIn("secret", json.dumps(event))

    def test_an_empty_message_after_cleaning_is_dropped(self) -> None:
        self.assertNotIn("message", build("x", redact=lambda t: ""))
        self.assertNotIn("message", build(""))


class Store:
    """Records events synchronously so a test can read them right after ``flush_events``."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pushes: List[Tuple[Any, int]] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        return None

    def push_events(self, items: Any, ttl_seconds: int) -> None:
        with self.lock:
            self.pushes.append((list(items), ttl_seconds))

    def events(self, level: str = "") -> List[Dict[str, Any]]:
        out = []
        for items, _ in self.pushes:
            for key, values, _cap in items:
                if key.endswith(":events:" + level) or not level:
                    out += [json.loads(v) for v in values]
        return sorted(out, key=lambda e: e["n"])


class TestStepAttachment(unittest.TestCase):
    """Specs 012 research R8: which step an event belongs to."""

    def setUp(self) -> None:
        registry.clear()
        self.store = Store()
        self.auditor = StepAuditor(self.store, SPEC, env="qa", ttl_seconds=60, run_id="R1")  # type: ignore[arg-type]
        registry.set_active(self.auditor)

    def tearDown(self) -> None:
        registry.clear()

    def sent(self) -> List[Dict[str, Any]]:
        self.auditor.flush_events(5)
        return self.store.events()

    def test_an_event_inside_a_step_belongs_to_it(self) -> None:
        @audited_step("extract")
        def fetch() -> None:
            waypoint_etl.log("inside")

        fetch()
        self.assertEqual(
            [(e["message"], e.get("step")) for e in self.sent()], [("inside", "extract")]
        )

    def test_a_nested_call_inside_a_step_belongs_to_it(self) -> None:
        def helper() -> None:
            waypoint_etl.warn("deep")

        @audited_step("load")
        def load() -> None:
            helper()

        load()
        (event,) = self.sent()
        self.assertEqual((event["level"], event["step"]), ("warning", "load"))

    def test_an_explicit_step_wins(self) -> None:
        @audited_step("extract")
        def fetch() -> None:
            waypoint_etl.log("x", step="load")

        fetch()
        self.assertEqual(self.sent()[0]["step"], "load")

    def test_outside_any_step_there_is_no_step(self) -> None:
        waypoint_etl.log("outside")
        self.assertNotIn("step", self.sent()[0])

    def test_the_step_ends_with_the_call(self) -> None:
        @audited_step("extract")
        def fetch() -> None:
            return None

        fetch()
        waypoint_etl.log("after")
        self.assertNotIn("step", self.sent()[0])

    def test_a_worker_thread_uses_the_single_open_step(self) -> None:
        @audited_step("extract")
        def fetch() -> None:
            worker = threading.Thread(target=lambda: waypoint_etl.log("from a worker"))
            worker.start()
            worker.join()

        fetch()
        self.assertEqual(self.sent()[0]["step"], "extract")

    def test_a_worker_thread_with_no_open_step_has_none(self) -> None:
        worker = threading.Thread(target=lambda: waypoint_etl.log("lonely"))
        worker.start()
        worker.join()
        self.assertNotIn("step", self.sent()[0])

    def test_concurrent_async_steps_keep_their_own_names(self) -> None:
        @audited_step("extract")
        async def first() -> None:
            await asyncio.sleep(0.01)
            waypoint_etl.log("one")

        @audited_step("load")
        async def second() -> None:
            waypoint_etl.log("two")
            await asyncio.sleep(0.02)
            waypoint_etl.log("three")

        async def both() -> None:
            await asyncio.gather(first(), second())

        asyncio.run(both())
        steps = {e["message"]: e["step"] for e in self.sent()}
        self.assertEqual(steps, {"one": "extract", "two": "load", "three": "load"})

    def test_auditor_run_sets_the_step_too(self) -> None:
        self.auditor.run("extract", lambda: waypoint_etl.log("via run"))
        self.assertEqual(self.sent()[0]["step"], "extract")

    def test_a_failing_step_still_resets_the_step(self) -> None:
        @audited_step("extract")
        def boom() -> None:
            raise ValueError("x")

        with self.assertRaises(ValueError):
            boom()
        waypoint_etl.log("after the failure")
        self.assertNotIn("step", self.sent()[0])

    def test_numbers_increase_across_levels(self) -> None:
        waypoint_etl.log("a")
        waypoint_etl.warn("b")
        waypoint_etl.error("c")
        self.assertEqual([e["n"] for e in self.sent()], [1, 2, 3])
        self.assertEqual([e["level"] for e in self.sent()], ["info", "warning", "error"])


class TestEventItem(unittest.TestCase):
    """Specs 014: an event sent inside a map step item carries the item's key."""

    def test_the_item_field_follows_the_step(self) -> None:
        event = build("hi", step="transform", item="acct-7")
        self.assertEqual((event["step"], event["item"]), ("transform", "acct-7"))
        self.assertEqual(list(event).index("item"), list(event).index("step") + 1)

    def test_without_an_item_the_event_is_unchanged(self) -> None:
        self.assertEqual(build("hi", step="load"), build("hi", step="load", item=None))
        self.assertNotIn("item", build("hi", step="load"))

    def test_an_empty_or_non_text_item_is_left_out(self) -> None:
        self.assertNotIn("item", build("hi", item=""))
        self.assertNotIn("item", build("hi", item=7))  # type: ignore[arg-type]


class EventStore:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        return None

    def push_events(self, items: Any, ttl_seconds: int) -> None:
        for _key, values, _cap in items:
            self.events.extend(json.loads(v) for v in values)


class TestEventsInItems(unittest.TestCase):
    def tearDown(self) -> None:
        registry.clear()

    def test_events_carry_the_item_and_inner_step_only_inside_an_item(self) -> None:
        from waypoint_etl import MapStepSpec

        spec = PipelineSpec(
            name="demo",
            steps=(MapStepSpec("accounts", steps=(StepSpec("fetch"),)),),
        )
        store = EventStore()
        waypoint_etl.init(
            pipeline=spec, redis_url=None, env="qa", store=store, heartbeat_seconds=None  # type: ignore[arg-type]
        )

        @audited_step("fetch")
        def fetch() -> None:
            waypoint_etl.log("inside a step")

        with waypoint_etl.map_step("accounts"):
            waypoint_etl.log("in the block")
            with waypoint_etl.item("acct-7"):
                waypoint_etl.log("in the item")
                fetch()
                waypoint_etl.warn("a warning", rows=3)
            waypoint_etl.log("after the item")
        registry.clear()
        found = {e["message"]: e for e in store.events}
        self.assertNotIn("item", found["in the block"])
        self.assertEqual(found["in the block"]["step"], "accounts")
        self.assertEqual(found["in the item"]["item"], "acct-7")
        self.assertEqual(found["in the item"]["step"], "accounts")
        self.assertEqual(
            (found["inside a step"]["item"], found["inside a step"]["step"]), ("acct-7", "fetch")
        )
        self.assertEqual(found["a warning"]["fields"], {"rows": 3})
        self.assertEqual(found["a warning"]["level"], "warning")
        self.assertNotIn("item", found["after the item"])


if __name__ == "__main__":
    unittest.main()
