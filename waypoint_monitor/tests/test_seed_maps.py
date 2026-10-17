"""The map step demo data (tests/seed_demo.py `maps`) shows every state of specs/014 HANDOFF.md."""

import re
import unittest
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import FakeStore
from tests.seed_demo import seed_maps

KEY = re.compile(
    r"^waypoint:(?P<p>[^:]+):(?P<env>[^:]+):(?P<run>[^:]+):(?P<kind>[a-z]+)(?::(?P<rest>.*))?$"
)


class FakeClient:
    """Just enough of redis.Redis for the seed: the values written, as a FakeStore would list them."""

    def __init__(self) -> None:
        self.values: Dict[str, str] = {}
        self.lists: Dict[str, List[str]] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    def rpush(self, key: str, *values: str) -> None:
        self.lists.setdefault(key, []).extend(values)

    def expire(self, key: str, ttl: int) -> None:
        return None


def load() -> TestClient:
    client = FakeClient()
    seed_maps(client, "prod", "maps", "Map step demo")  # type: ignore[arg-type]
    store = FakeStore()
    for key, value in client.values.items():
        kind = KEY.match(key)["kind"]  # type: ignore[index]
        target = {
            "flow": store.records,
            "step": store.records,
            "running": store.markers,
            "alive": store.alive,
            "map": store.maps,
            "item": store.items,
        }[kind]
        target.append((key, value))
    for key, values in client.lists.items():
        match = KEY.match(key)
        assert match and match["kind"] == "events"
        store.events.setdefault(match["run"], {})[match["rest"]] = values  # type: ignore[index]
    return TestClient(create_app(store, Settings(cache_seconds=0)))


class TestSeededMapStates(unittest.TestCase):
    client: TestClient
    runs: List[Dict[str, Any]]
    by_case: Dict[str, Dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = load()
        body = cls.client.get("/api/runs", params={"env": "prod", "pipeline": "maps"}).json()
        cls.runs = body["runs"]
        # newest first: zero_started, running_ok, running_fail, failed, done, done_lost, zero_items,
        # died, premap, large, stalled
        names = [
            "zero_started", "running_ok", "running_fail", "failed", "done", "done_lost",
            "zero_items", "died", "premap", "large", "stalled",
        ]  # fmt: skip
        cls.by_case = dict(zip(names, cls.runs, strict=True))

    def map(self, case: str) -> Dict[str, Any]:
        step = next(s for s in self.by_case[case]["steps"] if s["name"] == "accounts")
        return step  # type: ignore[no-any-return]

    def test_eleven_runs_all_readable(self) -> None:
        self.assertEqual(len(self.runs), 11)
        self.assertTrue(all(r["unreadable"] == 0 for r in self.runs))
        self.assertTrue(all(r["flow_status"] == "ok" and not r["flow_problems"] for r in self.runs))

    def test_running_with_no_failure(self) -> None:
        step = self.map("running_ok")
        self.assertEqual((step["state"], step["map"]["state"]), ("running", "running"))
        self.assertEqual(
            step["map"]["counts"], {"started": 10, "running": 4, "done": 6, "failed": 0}
        )

    def test_running_with_one_failed_item_a_slow_running_item_and_data_lost(self) -> None:
        step = self.map("running_fail")
        self.assertEqual((step["state"], step["map"]["state"]), ("running", "running"))
        self.assertEqual(step["map"]["counts"]["failed"], 1)
        self.assertEqual(step["map"]["lost_items"], 1)
        path = f"/api/runs/maps/prod/{self.by_case['running_fail']['run_id']}/maps/accounts/items"
        items = {i["key"]: i for i in self.client.get(path).json()["items"]}
        self.assertTrue(items["acct-9"]["slow"])
        self.assertEqual(items["acct-9"]["state"], "running")
        self.assertTrue(items["acct-3"]["loss"])
        self.assertEqual(items["acct-4"]["failed_step"], "transform")

    def test_failed(self) -> None:
        run = self.by_case["failed"]
        step = self.map("failed")
        self.assertEqual((step["state"], step["map"]["state"]), ("failed", "failed"))
        self.assertEqual(step["error"]["type"], "ItemsFailed")
        self.assertEqual(step["map"]["failed_items"][0]["key"], "acct-7")
        self.assertEqual(run["status"], "incomplete")
        path = f"/api/runs/maps/prod/{run['run_id']}/maps/accounts/items/acct-7"
        detail = self.client.get(path).json()
        self.assertEqual([s["state"] for s in detail["steps"]], ["done", "failed", "not_run"])
        events = self.client.get(
            f"/api/runs/maps/prod/{run['run_id']}/events", params={"item": "acct-7"}
        ).json()
        self.assertEqual(len(events["events"]), 3)

    def test_done_and_done_with_data_lost(self) -> None:
        self.assertEqual(self.map("done")["map"]["state"], "done")
        self.assertEqual(self.map("done")["map"]["lost_items"], 0)
        self.assertEqual(self.map("done_lost")["map"]["state"], "done")
        self.assertEqual(self.map("done_lost")["map"]["lost_items"], 1)

    def test_zero_started_and_zero_items(self) -> None:
        open_ = self.map("zero_started")
        self.assertEqual((open_["state"], open_["map"]["counts"]["started"]), ("running", 0))
        done = self.map("zero_items")
        self.assertEqual((done["state"], done["map"]["state"]), ("done", "done"))
        self.assertEqual(done["map"]["counts"]["started"], 0)

    def test_stalled_and_died(self) -> None:
        self.assertEqual(self.map("stalled")["map"]["state"], "stalled")
        self.assertEqual(self.map("died")["map"]["state"], "died")
        path = f"/api/runs/maps/prod/{self.by_case['died']['run_id']}/maps/accounts/items"
        states = {i["state"] for i in self.client.get(path).json()["items"]}
        self.assertEqual(states, {"done", "died"})

    def test_large_loop_with_partial_detail(self) -> None:
        step = self.map("large")
        self.assertEqual(
            step["map"]["counts"], {"started": 10000, "running": 0, "done": 9812, "failed": 188}
        )
        self.assertEqual(
            step["map"]["detail"], {"partial": True, "kept": 1050, "failed_without_record": 37}
        )
        path = f"/api/runs/maps/prod/{self.by_case['large']['run_id']}/maps/accounts/items"
        first = self.client.get(path).json()
        self.assertEqual(
            (first["total"], first["with_record"], first["has_more"]), (10000, 1050, True)
        )
        self.assertEqual(len(first["items"]), 50)
        failed = self.client.get(path, params={"state": "failed", "limit": 200}).json()
        self.assertEqual(failed["matched"], 151)
        self.assertGreater(len([i for i in first["items"] if i["key"]]), 0)

    def test_run_without_map_steps_is_an_ordinary_run(self) -> None:
        run = self.by_case["premap"]
        self.assertTrue(all("map" not in s for s in run["steps"]))
        self.assertEqual(run["status"], "complete")


if __name__ == "__main__":
    unittest.main()
