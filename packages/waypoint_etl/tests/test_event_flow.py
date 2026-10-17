"""Events end to end with a recording store: keys, levels, steps, TTL, privacy.

Specs 012 contracts/redis-keys.md and spec SC-010.
"""

import json
import unittest
from typing import Any, Dict, List, Sequence, Tuple

import waypoint_etl
from waypoint_etl import PipelineSpec, StepSpec, audited_step, registry

SPEC = PipelineSpec(
    name="demo",
    steps=(StepSpec("extract"), StepSpec("load", inputs=(("rows", "extract"),))),
)
Item = Tuple[str, Sequence[str], int]
# The marker lives in a variable: a traceback shows source lines (code, not data), so a literal in the
# raising line would appear there by design.
MARKER = "secret-marker"
EMAIL = "jane@example.com"


class Store:
    def __init__(self) -> None:
        self.records: List[Tuple[str, Dict[str, object], int]] = []
        self.pushes: List[Tuple[List[Item], int]] = []

    def write(self, key: str, record: Dict[str, object], ttl_seconds: int) -> None:
        self.records.append((key, record, ttl_seconds))

    def push_events(self, items: Sequence[Item], ttl_seconds: int) -> None:
        self.pushes.append((list(items), ttl_seconds))

    def lists(self) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for items, _ttl in self.pushes:
            for key, values, _cap in items:
                out.setdefault(key, []).extend(json.loads(v) for v in values)
        return out


def start(**kw: Any) -> Store:
    store = Store()
    waypoint_etl.init(
        pipeline=SPEC,
        redis_url=None,
        env="qa",
        run_id="20261017T020000Z",
        store=store,  # type: ignore[arg-type]
        ttl_days=7,
        heartbeat_seconds=None,
        **kw,
    )
    return store


class TestEventFlow(unittest.TestCase):
    def tearDown(self) -> None:
        registry.clear()

    def test_events_land_in_the_list_of_their_level_with_their_step(self) -> None:
        store = start()

        @audited_step("extract")
        def extract() -> list[int]:
            waypoint_etl.log("read 3 rows", rows=3)
            waypoint_etl.warn("slow source", retries=2)
            return [1, 2, 3]

        @audited_step("load")
        def load(rows: list[int]) -> None:
            waypoint_etl.error("one row rejected", row=2)

        load(extract())
        registry.clear()
        lists = store.lists()
        base = "waypoint:demo:qa:20261017T020000Z:events:"
        self.assertEqual(sorted(lists), [base + "error", base + "info", base + "warning"])
        (info,) = lists[base + "info"]
        self.assertEqual(
            (info["message"], info["step"], info["fields"]), ("read 3 rows", "extract", {"rows": 3})
        )
        (warning,) = lists[base + "warning"]
        self.assertEqual((warning["step"], warning["fields"]), ("extract", {"retries": 2}))
        (error,) = lists[base + "error"]
        self.assertEqual((error["step"], error["fields"]), ("load", {"row": 2}))
        self.assertEqual(sorted(e["n"] for ev in lists.values() for e in ev), [1, 2, 3])
        for event in (info, warning, error):
            self.assertEqual(event["v"], 1)
            self.assertRegex(event["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

    def test_ttl_is_the_runs_and_caps_are_per_level(self) -> None:
        store = start()
        waypoint_etl.log("a")
        waypoint_etl.error("b")
        registry.clear()
        for _items, ttl in store.pushes:
            self.assertEqual(ttl, 7 * 86400)
        caps = {k.rsplit(":", 1)[1]: c for items, _ in store.pushes for k, _v, c in items}
        self.assertEqual(caps, {"info": 500, "error": 200})

    def test_events_do_not_change_the_step_records(self) -> None:
        store = start()

        @audited_step("extract")
        def extract() -> list[int]:
            waypoint_etl.log("x")
            return [1]

        extract()
        registry.clear()
        step = [r for k, r, _ in store.records if ":step:" in k]
        self.assertEqual(len(step), 1)
        self.assertEqual(step[0]["output"], 1)

    def test_capture_off_stores_no_marker_text_anywhere(self) -> None:
        store = start(capture_error_message=False)

        @audited_step("extract")
        def extract() -> None:
            waypoint_etl.log(MARKER + " in the message", note=MARKER, rows=5)
            raise ValueError(MARKER + " in the error")

        with self.assertRaises(ValueError):
            extract()
        registry.clear()
        everything = json.dumps([store.lists(), [r for _, r, _ in store.records]])
        self.assertNotIn(MARKER, everything)
        (event,) = store.lists()["waypoint:demo:qa:20261017T020000Z:events:info"]
        self.assertEqual((event["step"], event["fields"]), ("extract", {"rows": 5}))
        self.assertNotIn("message", event)

    def test_redact_cleans_events_and_failures_alike(self) -> None:
        store = start(redact=lambda t: t.replace(EMAIL, "<email>"))

        @audited_step("extract")
        def extract() -> None:
            waypoint_etl.log("mail to " + EMAIL, who=EMAIL)
            raise ValueError("bad " + EMAIL)

        with self.assertRaises(ValueError):
            extract()
        registry.clear()
        failures = [r for k, r, _ in store.records if ":failed:" in k]
        everything = json.dumps([store.lists(), failures])
        self.assertNotIn(EMAIL, everything)
        self.assertIn("<email>", everything)
        failed = next(r for k, r, _ in store.records if ":failed:" in k)
        self.assertEqual(failed["error"]["message"], "bad <email>")  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
