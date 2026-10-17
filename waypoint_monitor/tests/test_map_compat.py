"""Runs without a map step are served exactly as before (specs/014 FR-028, SC-008, tasks T035).

`golden_no_map_runs.json` was produced by the monitor of spec 013 (before the map step existed) from the
scenario below; `/api/runs` must still return it byte for byte as parsed JSON.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import (
    FakeStore,
    declare_metrics,
    make_alive,
    make_failure,
    make_marker,
    make_metrics,
    make_run,
)

GOLDEN = Path(__file__).with_name("golden_no_map_runs.json")
NOW = datetime(2026, 10, 15, 3, 0, 0, tzinfo=timezone.utc)
R1 = "20261015T020000Z"  # complete, exact durations, metrics
R2 = "20261015T015000Z"  # a step running now, with a heartbeat
R3 = "20261014T020000Z"  # a step failed
R4 = "20261013T020000Z"  # written by library 0.3.0 (no step start times)


def scenario() -> FakeStore:
    store = FakeStore()
    r1 = declare_metrics(
        make_run("prod", R1, step_seconds=[5, 7, 3, 4, 6, 9, 11, 2, 2]),
        "merge_calls_clickview",
        [{"name": "rejected", "unit": "rows", "warn_above": 10}],
    )
    store.records += r1
    store.metrics.append(make_metrics("prod", R1, 6, {"rejected": 42, "retries": 1}))
    store.records += make_run("prod", R2, missing_from=3)
    store.markers.append(make_marker("prod", R2, 3, NOW - timedelta(seconds=40)))
    store.alive.append(make_alive("prod", R2, NOW - timedelta(seconds=20)))
    store.records += make_run("prod", R3, missing_from=4)
    store.failures.append(make_failure("prod", R3, 4, NOW - timedelta(days=1, hours=21)))
    store.records += make_run("prod", R4, step_seconds=None, exact=False)
    store.add_event(R1, "warning", 1, "2026-10-15T02:00:09.100Z", "slow", step="read_partners")
    return store


def fetch() -> Any:
    store = scenario()
    settings = Settings(cache_seconds=10)
    client = TestClient(create_app(store, settings, clock=lambda: 0.0, now=lambda: NOW))
    runs = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()
    events = client.get(f"/api/runs/callrail/prod/{R1}/events").json()
    return {"runs": runs, "events": events}


class TestNoMapGolden(unittest.TestCase):
    def test_runs_and_events_match_the_spec_013_output(self) -> None:
        self.assertEqual(fetch(), json.loads(GOLDEN.read_text()))

    def test_no_map_key_anywhere(self) -> None:
        body = fetch()["runs"]
        for run in body["runs"]:
            self.assertEqual(run["unreadable"], 0)
            for s in run["steps"]:
                self.assertNotIn("map", s)
            for s in (run["flow"] or {"steps": []})["steps"]:
                self.assertNotIn("map", s)
        self.assertEqual(body["unreadable_total"], 0)


if __name__ == "__main__":
    unittest.main()
