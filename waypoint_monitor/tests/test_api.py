import json
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import (
    FakeStore,
    declare_metrics,
    flow_value,
    make_alive,
    make_died,
    make_failure,
    make_marker,
    make_metrics,
    make_run,
)

NOW = datetime(2026, 10, 15, 3, 0, 0, tzinfo=timezone.utc)
R1 = "20261015T020000Z"
R2 = "20261014T020000Z"
R3 = "20261013T020000Z"


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def client_for(
    store: FakeStore, now: datetime = NOW, clock: Optional[Clock] = None, **kw: object
) -> TestClient:
    clock = clock or Clock()
    settings = Settings(**{"cache_seconds": 10, **kw})  # type: ignore[arg-type]
    return TestClient(create_app(store, settings, clock=clock, now=lambda: now))


class TestConfigAndHealth(unittest.TestCase):
    def test_config_shape(self) -> None:
        body = (
            client_for(FakeStore(), refresh_seconds=5, retry_seconds=7, stale_hours=3)
            .get("/api/config")
            .json()
        )
        self.assertEqual(body["environments"], ["prod", "qa"])
        self.assertEqual(
            (body["refresh_seconds"], body["retry_seconds"], body["stale_hours"]), (5, 7, 3)
        )
        self.assertNotIn("expected_steps", body)

    def test_health(self) -> None:
        store = FakeStore()
        client = client_for(store)
        self.assertEqual(client.get("/api/health").json(), {"redis": "ok"})
        store.fail = True
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["redis"], "unavailable")


class TestRuns(unittest.TestCase):
    def test_runs_shape_and_order(self) -> None:
        store = FakeStore(make_run("prod", R2) + make_run("prod", R1) + make_run("qa", R3))
        body = (
            client_for(store)
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        self.assertEqual(body["env"], "prod")
        self.assertEqual(body["generated_at"], "2026-10-15T03:00:00Z")
        self.assertEqual(body["unreadable_total"], 0)
        self.assertEqual([r["run_id"] for r in body["runs"]], [R1, R2])
        first = body["runs"][0]
        self.assertEqual(first["status"], "complete")
        self.assertEqual(len(first["steps"]), 9)
        self.assertEqual(first["steps"][0]["output"], 10)
        self.assertEqual(
            set(first),
            {
                "run_id",
                "pipeline",
                "flow_status",
                "flow_problems",
                "flow",
                "env",
                "started_at",
                "ended_at",
                "duration_seconds",
                "age_seconds",
                "stale",
                "status",
                "first_missing_step",
                "missing_count",
                "loss_steps",
                "unreadable",
                "steps",
                "running_step",
                "died",
                "failed",  # specs/011
                "duration",  # specs/012
                "bottleneck",
                "event_counts",
                "metrics_over",
            },
        )

    def test_empty(self) -> None:
        response = client_for(FakeStore()).get(
            "/api/runs", params={"env": "qa", "pipeline": "callrail"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["runs"], [])

    def test_unknown_env_400(self) -> None:
        self.assertEqual(
            client_for(FakeStore())
            .get("/api/runs", params={"env": "dev", "pipeline": "callrail"})
            .status_code,
            400,
        )

    def test_store_down_503(self) -> None:
        store = FakeStore()
        store.fail = True
        response = client_for(store).get(
            "/api/runs", params={"env": "prod", "pipeline": "callrail"}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "Data store unavailable"})

    def test_limit_default_and_cap(self) -> None:
        raw = []
        for d in range(40):
            raw += make_run(
                "prod",
                (datetime(2026, 9, 1, 2, tzinfo=timezone.utc) + timedelta(days=d)).strftime(
                    "%Y%m%dT%H%M%SZ"
                ),
            )
        client = client_for(FakeStore(raw))
        self.assertEqual(
            len(
                client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()[
                    "runs"
                ]
            ),
            30,
        )
        self.assertEqual(
            len(
                client.get(
                    "/api/runs", params={"env": "prod", "pipeline": "callrail", "limit": 5}
                ).json()["runs"]
            ),
            5,
        )
        self.assertEqual(
            client.get(
                "/api/runs", params={"env": "prod", "pipeline": "callrail", "limit": 101}
            ).status_code,
            422,
        )
        self.assertEqual(
            len(
                client.get(
                    "/api/runs", params={"env": "prod", "pipeline": "callrail", "limit": 100}
                ).json()["runs"]
            ),
            40,
        )

    def test_flags_and_unreadable(self) -> None:
        raw = make_run("prod", R1, overrides={5: 0}, corrupt=(8,)) + make_run(
            "prod", R2, missing_from=7
        )
        raw.append(("waypoint:callrail:prod:junk:step:01-x", "{}"))
        body = (
            client_for(FakeStore(raw))
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        self.assertEqual(body["unreadable_total"], 2)
        newest, older = body["runs"]
        self.assertEqual(newest["unreadable"], 1)
        self.assertIn("read_gads_clickview", newest["loss_steps"])
        self.assertEqual(older["first_missing_step"], "record_call_statistics")

    def test_stale_flag(self) -> None:
        store = FakeStore(make_run("prod", R1))
        body = (
            client_for(store, now=NOW + timedelta(hours=30))
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        self.assertTrue(body["runs"][0]["stale"])
        self.assertGreater(body["runs"][0]["age_seconds"], 26 * 3600)

    def test_no_free_form_record_content_is_returned(self) -> None:
        raw = make_run("prod", R1)
        key, value = raw[1]  # raw[0] is the flow
        raw[1] = (key, value.replace('"step"', '"caller_name": "Jane Doe", "step"'))
        text = (
            client_for(FakeStore(raw))
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .text
        )
        self.assertNotIn("Jane", text)


class TestLive(unittest.TestCase):
    def _store(self) -> FakeStore:
        store = FakeStore(make_run("prod", R1, missing_from=3))
        store.markers = [make_marker("prod", R1, 3, NOW - timedelta(seconds=42))]
        return store

    def test_running_run_shape(self) -> None:
        body = (
            client_for(self._store())
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        run = body["runs"][0]
        self.assertEqual((run["status"], run["running_step"]), ("running", "read_instances"))
        self.assertFalse(run["stale"])
        states = [s["state"] for s in run["steps"]]
        self.assertEqual(states, ["done"] * 3 + ["running"] + ["waiting"] * 5)
        self.assertEqual(run["steps"][3]["elapsed_seconds"], 42)

    def test_stall_seconds_in_config_and_applied(self) -> None:
        client = client_for(self._store(), stall_seconds=30)
        self.assertEqual(client.get("/api/config").json()["stall_seconds"], 30)
        run = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()[
            "runs"
        ][0]
        self.assertEqual(run["steps"][3]["state"], "stalled")
        self.assertEqual(run["status"], "incomplete")

    def test_marker_read_failure_is_503(self) -> None:
        class MarkersDown(FakeStore):
            def list_markers(self, env: str, pipeline: str):  # type: ignore[no-untyped-def]
                from app.infrastructure.store import StoreUnavailable

                raise StoreUnavailable("down")

        response = client_for(MarkersDown(make_run("prod", R1))).get(
            "/api/runs", params={"env": "prod", "pipeline": "callrail"}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "Data store unavailable"})

    def test_markers_for_other_env_ignored(self) -> None:
        store = self._store()
        run = (
            client_for(store)
            .get("/api/runs", params={"env": "qa", "pipeline": "callrail"})
            .json()["runs"]
        )
        self.assertEqual(run, [])

    def test_complete_run_has_no_running_step(self) -> None:
        run = (
            client_for(FakeStore(make_run("prod", R1)))
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()["runs"][0]
        )
        self.assertEqual((run["status"], run["running_step"]), ("complete", None))


class TestCache(unittest.TestCase):
    def test_cache_hits_then_expires(self) -> None:
        store = FakeStore(make_run("prod", R1))
        clock = Clock()
        client = client_for(store, clock=clock)
        client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        self.assertEqual(store.calls, 1)
        clock.t = 11
        client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        self.assertEqual(store.calls, 2)

    def test_unreachable_store_is_not_served_from_cache(self) -> None:
        store = FakeStore(make_run("prod", R1))
        clock = Clock()
        client = client_for(store, clock=clock)
        self.assertEqual(
            client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).status_code, 200
        )
        store.fail = True
        clock.t = 11
        self.assertEqual(
            client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).status_code, 503
        )
        clock.t = 12  # even within the cache window of an earlier success
        self.assertEqual(
            client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).status_code, 503
        )


DEMO_STEPS: List[Dict[str, Any]] = [
    {"name": "a", "label": "Alpha", "inputs": []},
    {"name": "b", "inputs": [{"name": "rows", "from": "a"}]},
    {"name": "c", "inputs": [{"name": "rows", "from": "b"}]},
]


def demo_run(run_id: str, pipeline: str = "demo", with_flow: bool = True) -> List[Tuple[str, str]]:
    """A complete three-step run of a pipeline the monitor has never heard of."""
    import json

    out: List[Tuple[str, str]] = []
    if with_flow:
        out.append(
            (
                f"waypoint:{pipeline}:prod:{run_id}:flow",
                flow_value(pipeline, "prod", run_id, DEMO_STEPS, label="Demo pipeline"),
            )
        )
    for i, name in enumerate("abc", start=1):
        record = {
            "pipeline": pipeline,
            "run_id": run_id,
            "env": "prod",
            "step": name,
            "index": i,
            "inputs": {} if i == 1 else {"rows": 9},
            "output": 9,
            "finished_at": f"2026-10-15T02:00:{i * 5:02d}Z",
        }
        out.append((f"waypoint:{pipeline}:prod:{run_id}:step:{i:02d}-{name}", json.dumps(record)))
    return out


class TestPipelines(unittest.TestCase):
    def runs(self, store: FakeStore, pipeline: str, env: str = "prod") -> Dict[str, Any]:
        response = client_for(store).get("/api/runs", params={"env": env, "pipeline": pipeline})
        body: Dict[str, Any] = response.json()
        return body

    def test_two_pipelines_are_listed_and_stay_separate(self) -> None:
        store = FakeStore(make_run("prod", R2) + demo_run(R1))
        client = client_for(store)
        body = client.get("/api/pipelines", params={"env": "prod"}).json()
        self.assertEqual(
            body["pipelines"],
            [
                {"name": "demo", "label": "Demo pipeline", "last_run_id": R1},
                {"name": "callrail", "label": "CallRail", "last_run_id": R2},
            ],
        )
        demo = self.runs(store, "demo")["runs"]
        self.assertEqual([r["run_id"] for r in demo], [R1])
        self.assertEqual([s["name"] for s in demo[0]["steps"]], ["a", "b", "c"])
        self.assertEqual(demo[0]["steps"][0]["output"], 9)
        callrail = self.runs(store, "callrail")["runs"]
        self.assertEqual([r["run_id"] for r in callrail], [R2])
        self.assertEqual(len(callrail[0]["steps"]), 9)

    def test_same_step_names_in_two_pipelines_never_mix(self) -> None:
        store = FakeStore(demo_run(R1, "one") + demo_run(R1, "two"))
        one = self.runs(store, "one")["runs"][0]
        two = self.runs(store, "two")["runs"][0]
        self.assertEqual((one["pipeline"], two["pipeline"]), ("one", "two"))
        self.assertEqual(len(one["steps"]), 3)
        self.assertEqual(len(two["steps"]), 3)

    def test_old_layout_keys_add_no_pipeline_and_no_error(self) -> None:
        store = FakeStore([(f"callrail:audit:prod:{R1}:01-read_callrail_account", "{}")])
        client = client_for(store)
        self.assertEqual(
            client.get("/api/pipelines", params={"env": "prod"}).json()["pipelines"], []
        )
        body = self.runs(store, "callrail")
        self.assertEqual((body["runs"], body["unreadable_total"]), ([], 0))

    def test_pipeline_without_a_flow_is_still_listed(self) -> None:
        store = FakeStore(demo_run(R1, with_flow=False))
        body = client_for(store).get("/api/pipelines", params={"env": "prod"}).json()
        self.assertEqual(body["pipelines"], [{"name": "demo", "label": "demo", "last_run_id": R1}])
        run = self.runs(store, "demo")["runs"][0]
        self.assertEqual((run["flow_status"], run["flow"]), ("missing", None))
        self.assertEqual([s["name"] for s in run["steps"]], ["a", "b", "c"])

    def test_other_env_not_listed(self) -> None:
        store = FakeStore(demo_run(R1))
        body = client_for(store).get("/api/pipelines", params={"env": "qa"}).json()
        self.assertEqual(body["pipelines"], [])

    def test_errors(self) -> None:
        client = client_for(FakeStore())
        self.assertEqual(client.get("/api/pipelines", params={"env": "dev"}).status_code, 400)
        self.assertEqual(client.get("/api/runs", params={"env": "prod"}).status_code, 422)
        for bad in ("Bad", "a:b", "", "x" * 41):
            response = client.get("/api/runs", params={"env": "prod", "pipeline": bad})
            self.assertIn(response.status_code, (400, 422), bad)
        store = FakeStore()
        store.fail = True
        self.assertEqual(
            client_for(store).get("/api/pipelines", params={"env": "prod"}).status_code, 503
        )

    def test_flow_json_carries_labels_groups_and_dangling_flag(self) -> None:
        steps: List[Dict[str, Any]] = [
            {"name": "a", "inputs": [{"name": "x", "from": "zzz"}], "col": 2}
        ]
        raw = [
            (
                f"waypoint:demo:prod:{R1}:flow",
                flow_value("demo", "prod", R1, steps, groups=[{"key": "g", "label": "G"}]),
            )
        ]
        run = self.runs(FakeStore(raw), "demo")["runs"][0]
        self.assertEqual(run["flow"]["groups"], [{"key": "g", "label": "G"}])
        self.assertEqual(
            run["flow"]["steps"][0]["inputs"], [{"name": "x", "from": "zzz", "dangling": True}]
        )
        self.assertEqual(run["flow"]["steps"][0]["col"], 2.0)
        self.assertEqual(len(run["flow_problems"]), 1)


class TestOverview(unittest.TestCase):
    CARD_KEYS = {"name", "label", "environments", "card_status", "needs_attention", "latest"}
    LATEST_KEYS = {
        "run_id",
        "env",
        "status",
        "stale",
        "started_at",
        "ended_at",
        "age_seconds",
        "loss_steps",
        "first_missing_step",
        "stalled_step",
        "stalled_seconds",
        "unreadable",
        "headline",
        "died_step",
        "last_seen_at",
        "failed_step",
        "failed_at",
        "error",
        "duration_seconds",  # specs/012
        "duration_running",
        "slow",
        "warnings",
        "errors",
    }

    def overview(self, store: FakeStore, **kw: Any) -> Dict[str, Any]:
        response = client_for(store, **kw).get("/api/overview")
        self.assertEqual(response.status_code, 200)
        body: Dict[str, Any] = response.json()
        return body

    def test_shape_has_exactly_the_documented_fields(self) -> None:
        body = self.overview(FakeStore(make_run("prod", R1)))
        self.assertEqual(set(body), {"generated_at", "unreadable_total", "pipelines"})
        card = body["pipelines"][0]
        self.assertEqual(set(card), self.CARD_KEYS)
        self.assertEqual(set(card["latest"]), self.LATEST_KEYS)
        self.assertEqual(card["name"], "callrail")
        self.assertEqual(card["label"], "CallRail")
        self.assertEqual(card["card_status"], "ok")
        self.assertEqual([h["key"] for h in card["latest"]["headline"]], ["first", "peak", "last"])

    def test_newest_run_across_environments_labels_its_environment(self) -> None:
        store = FakeStore(make_run("prod", R2) + make_run("qa", R1))
        card = self.overview(store)["pipelines"][0]
        self.assertEqual(card["latest"]["env"], "qa")
        self.assertEqual(card["environments"], ["prod", "qa"])

    def test_pipeline_only_in_qa_still_appears(self) -> None:
        card = self.overview(FakeStore(make_run("qa", R1)))["pipelines"][0]
        self.assertEqual(card["environments"], ["qa"])

    def test_two_pipelines_become_two_cards(self) -> None:
        body = self.overview(FakeStore(make_run("prod", R1) + demo_run(R1)))
        self.assertEqual(sorted(c["name"] for c in body["pipelines"]), ["callrail", "demo"])

    def test_empty_store_is_an_empty_list_with_200(self) -> None:
        body = self.overview(FakeStore())
        self.assertEqual(body["pipelines"], [])
        self.assertEqual(body["unreadable_total"], 0)

    def test_unreadable_records_are_summed(self) -> None:
        body = self.overview(
            FakeStore(make_run("prod", R1, corrupt=[2]) + make_run("qa", R1, corrupt=[3]))
        )
        self.assertEqual(body["unreadable_total"], 2)

    def test_store_down_is_503(self) -> None:
        store = FakeStore()
        store.fail = True
        response = client_for(store).get("/api/overview")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "Data store unavailable"})

    def test_incomplete_and_lost_data_status(self) -> None:
        incomplete = self.overview(FakeStore(make_run("prod", R1, missing_from=5)), stale_hours=48)
        card = incomplete["pipelines"][0]
        self.assertEqual(card["card_status"], "incomplete")
        self.assertTrue(card["needs_attention"])
        self.assertEqual(card["latest"]["first_missing_step"], "read_gads_clickview")
        lost = self.overview(FakeStore(make_run("prod", R1, overrides={1: 0})), stale_hours=48)
        self.assertEqual(lost["pipelines"][0]["card_status"], "lost")

    def test_run_older_than_stale_hours_is_stale_and_a_fresh_one_is_ok(self) -> None:
        store = FakeStore(make_run("prod", R1))
        self.assertEqual(self.overview(store, stale_hours=48)["pipelines"][0]["card_status"], "ok")
        stale = self.overview(store, stale_hours=0.001)["pipelines"][0]
        self.assertEqual(stale["card_status"], "stale")
        self.assertTrue(stale["latest"]["stale"])

    def test_new_pipeline_appears_on_the_next_call_after_the_cache_window(self) -> None:
        clock = Clock()
        store = FakeStore(make_run("prod", R1))
        client = client_for(store, clock=clock, cache_seconds=2)
        self.assertEqual(len(client.get("/api/overview").json()["pipelines"]), 1)
        store.records += demo_run(R1)
        clock.t = 3.0
        names = [c["name"] for c in client.get("/api/overview").json()["pipelines"]]
        self.assertEqual(sorted(names), ["callrail", "demo"])

    def test_other_endpoints_keep_their_shape(self) -> None:
        store = FakeStore(make_run("prod", R1))
        client = client_for(store)
        pipelines = client.get("/api/pipelines", params={"env": "prod"}).json()
        self.assertEqual(set(pipelines["pipelines"][0]), {"name", "label", "last_run_id"})
        runs = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()
        self.assertIn("runs", runs)
        self.assertNotIn("card_status", runs["runs"][0])


BEAT = NOW - timedelta(seconds=100)  # older than the 90 s death-detection time
RUNS = {"env": "prod", "pipeline": "callrail"}


def _died_store(beat: datetime = BEAT, store: Optional[FakeStore] = None) -> FakeStore:
    store = store or FakeStore(make_run("prod", R1, missing_from=3))
    store.markers = [
        make_marker("prod", R1, 3, datetime(2026, 10, 15, 2, 0, 33, tzinfo=timezone.utc))
    ]
    store.alive = [make_alive("prod", R1, beat)]
    return store


def _first_run(client: TestClient) -> Dict[str, Any]:
    response = client.get("/api/runs", params=RUNS)
    assert response.status_code == 200, response.text
    run: Dict[str, Any] = response.json()["runs"][0]
    return run


class RacingStore(FakeStore):
    """Another monitor instance stores its verdict just before ours."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.theirs = make_died("prod", R1, NOW - timedelta(seconds=5), BEAT)
        self.raced = False

    def record_died(self, key: str, value: str, alive_key: str) -> bool:
        if not self.raced:
            self.raced = True
            self.died.append(self.theirs)
        return super().record_died(key, value, alive_key)


class TestDied(unittest.TestCase):
    """specs/009-run-liveness-heartbeat: Died judgement, the one verdict write, permanence."""

    def test_stale_heartbeat_gives_a_died_run(self) -> None:
        run = _first_run(client_for(_died_store()))
        self.assertEqual(run["status"], "incomplete")
        self.assertEqual([s["state"] for s in run["steps"]][:5], ["done"] * 3 + ["died", "missing"])
        self.assertEqual(run["died"]["last_seen_at"], "2026-10-15T02:58:20Z")
        self.assertIsNone(run["running_step"])

    def test_fresh_heartbeat_is_not_died_and_nothing_is_written(self) -> None:
        store = _died_store(beat=NOW - timedelta(seconds=20))
        run = _first_run(client_for(store))
        self.assertIsNone(run["died"])
        self.assertEqual(run["steps"][3]["state"], "stalled")  # alive, but stuck for 59 minutes
        self.assertEqual(store.write_calls, [])

    def test_first_judgement_records_one_verdict_with_ids_and_times_only(self) -> None:
        store = _died_store()
        _first_run(client_for(store))
        self.assertEqual(len(store.write_calls), 1)
        key, value, alive_key = store.write_calls[0]
        self.assertEqual(key, f"waypoint:callrail:prod:{R1}:died")
        self.assertEqual(alive_key, f"waypoint:callrail:prod:{R1}:alive")
        self.assertEqual(
            json.loads(value),
            {
                "v": 1,
                "pipeline": "callrail",
                "env": "prod",
                "run_id": R1,
                "judged_at": "2026-10-15T03:00:00Z",
                "last_seen_at": "2026-10-15T02:58:20Z",
            },
        )

    def test_a_successful_write_is_reported_and_read_back_inside_the_cache_window(self) -> None:
        store = _died_store()
        client = client_for(store)
        first = _first_run(client)["died"]
        second = _first_run(client)["died"]
        self.assertTrue(first["recorded"] and second["recorded"])
        self.assertEqual(first["judged_at"], second["judged_at"])
        self.assertEqual(len(store.write_calls), 1)

    def test_the_verdict_is_read_not_rewritten_and_shared_between_instances(self) -> None:
        store = _died_store()
        _first_run(client_for(store))
        later = NOW + timedelta(hours=2)
        other_instance = client_for(store, now=later)
        run = _first_run(other_instance)
        self.assertEqual(len(store.write_calls), 1)
        self.assertEqual(run["died"]["judged_at"], "2026-10-15T03:00:00Z")  # not re-judged
        self.assertTrue(run["died"]["recorded"])

    def test_it_stays_died_after_the_heartbeat_resumes(self) -> None:
        store = _died_store()
        _first_run(client_for(store))
        store.alive = [make_alive("prod", R1, NOW + timedelta(seconds=30))]
        run = _first_run(client_for(store, now=NOW + timedelta(seconds=40)))
        self.assertEqual(run["steps"][3]["state"], "died")
        self.assertEqual(run["status"], "incomplete")

    def test_a_failed_write_still_shows_died_and_is_retried(self) -> None:
        store = _died_store()
        store.fail_write = True
        client = client_for(store)
        first = client.get("/api/runs", params=RUNS)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["runs"][0]["died"]["recorded"])
        self.assertEqual(first.json()["runs"][0]["steps"][3]["state"], "died")
        self.assertFalse(_first_run(client)["died"]["recorded"])
        self.assertEqual(len(store.write_calls), 2)  # retried on the next view
        store.fail_write = False
        self.assertTrue(_first_run(client)["died"]["recorded"])
        self.assertTrue(_first_run(client)["died"]["recorded"])
        self.assertEqual(len(store.write_calls), 3)  # no write once it is stored

    def test_two_monitors_judging_at_once_leave_one_consistent_verdict(self) -> None:
        store = _died_store(store=RacingStore(make_run("prod", R1, missing_from=3)))
        client = client_for(store)
        run = _first_run(client)
        self.assertEqual(run["steps"][3]["state"], "died")
        self.assertEqual(len(store.died), 1)
        again = _first_run(client)
        self.assertTrue(again["died"]["recorded"])
        self.assertEqual(again["died"]["judged_at"], "2026-10-15T02:59:55Z")  # the first writer's
        self.assertEqual(len(store.write_calls), 1)

    def test_a_finished_run_with_an_old_heartbeat_is_not_judged(self) -> None:
        store = FakeStore(make_run("prod", R1))
        store.alive = [make_alive("prod", R1, BEAT)]
        run = _first_run(client_for(store))
        self.assertEqual((run["status"], run["died"]), ("complete", None))
        self.assertEqual(store.write_calls, [])

    def test_overview_card_is_died(self) -> None:
        store = _died_store()
        body = client_for(store).get("/api/overview").json()
        card = body["pipelines"][0]
        self.assertEqual((card["card_status"], card["needs_attention"]), ("died", True))
        self.assertEqual(card["latest"]["died_step"], "read_instances")
        self.assertEqual(card["latest"]["last_seen_at"], "2026-10-15T02:58:20Z")

    def test_unreachable_store_is_still_503(self) -> None:
        store = _died_store()
        store.fail = True
        self.assertEqual(client_for(store).get("/api/runs", params=RUNS).status_code, 503)


class TestDeathDetectionTime(unittest.TestCase):
    """User Story 5: HEARTBEAT_DEAD_SECONDS decides how old a heartbeat may be (default 90 s)."""

    def _state(self, beat_age: float, dead: float = 90.0) -> str:
        store = _died_store(beat=NOW - timedelta(seconds=beat_age))
        run = _first_run(client_for(store, heartbeat_dead_seconds=dead))
        return str(run["steps"][3]["state"])

    def test_config_exposes_the_setting_with_its_default(self) -> None:
        self.assertEqual(
            client_for(FakeStore()).get("/api/config").json()["heartbeat_dead_seconds"], 90
        )
        configured = client_for(FakeStore(), heartbeat_dead_seconds=30)
        self.assertEqual(configured.get("/api/config").json()["heartbeat_dead_seconds"], 30)

    def test_default_threshold_is_ninety_seconds(self) -> None:
        self.assertEqual(self._state(80), "stalled")
        self.assertEqual(self._state(100), "died")

    def test_a_lower_setting_declares_death_sooner(self) -> None:
        self.assertEqual(self._state(20, dead=30), "stalled")
        self.assertEqual(self._state(40, dead=30), "died")

    def test_a_higher_setting_waits_longer(self) -> None:
        self.assertEqual(self._state(100, dead=300), "stalled")
        self.assertEqual(self._state(400, dead=300), "died")


class TestWithoutHeartbeat(unittest.TestCase):
    """Pipelines that send no heartbeat look exactly as before (User Story 3)."""

    def test_old_marker_without_a_heartbeat_is_stalled_not_died_and_nothing_is_written(
        self,
    ) -> None:
        store = FakeStore(make_run("prod", R1, missing_from=3))
        store.markers = [make_marker("prod", R1, 3, NOW - timedelta(hours=5))]
        run = _first_run(client_for(store))
        self.assertEqual(run["steps"][3]["state"], "stalled")
        self.assertIsNone(run["died"])
        self.assertEqual(store.write_calls, [])

    def test_extra_keys_add_no_unreadable_records_no_runs_and_no_pipelines(self) -> None:
        store = FakeStore(make_run("prod", R1))
        store.alive = [make_alive("prod", R1, NOW), make_alive("prod", R2, NOW, pipeline="ghost")]
        store.died = [make_died("prod", R2, NOW, NOW)]
        client = client_for(store)
        body = client.get("/api/runs", params=RUNS).json()
        self.assertEqual(body["unreadable_total"], 0)
        self.assertEqual([r["run_id"] for r in body["runs"]], [R1])
        pipelines = client.get("/api/overview").json()["pipelines"]
        self.assertEqual([p["name"] for p in pipelines], ["callrail"])  # no card for "ghost"
        self.assertEqual(client.get("/api/overview").json()["unreadable_total"], 0)

    def test_a_verdict_without_a_run_creates_no_run(self) -> None:
        store = FakeStore()
        store.died = [make_died("prod", R1, NOW, NOW)]
        self.assertEqual(client_for(store).get("/api/runs", params=RUNS).json()["runs"], [])


FAIL_AT = datetime(2026, 10, 15, 2, 0, 50, tzinfo=timezone.utc)


def _failed_store(beat: Optional[datetime] = BEAT) -> FakeStore:
    """Steps 1-3 finished; step 4 began at 02:00:33 and raised at 02:00:50."""
    store = FakeStore(make_run("prod", R1, missing_from=3))
    store.markers = [
        make_marker("prod", R1, 3, datetime(2026, 10, 15, 2, 0, 33, tzinfo=timezone.utc))
    ]
    store.failures = [make_failure("prod", R1, 3, FAIL_AT)]
    if beat is not None:
        store.alive = [make_alive("prod", R1, beat)]
    return store


class TestFailed(unittest.TestCase):
    """specs/011-step-failure-errors/contracts/api.md"""

    def test_runs_show_the_failed_step_and_the_failed_run(self) -> None:
        run = _first_run(client_for(_failed_store()))
        self.assertEqual(
            [s["state"] for s in run["steps"]], ["done"] * 3 + ["failed"] + ["missing"] * 5
        )
        step = run["steps"][3]
        self.assertEqual(step["error"]["type"], "ValueError")
        self.assertEqual(step["error"]["message"], "boom")
        self.assertIn("traceback", step["error"])
        self.assertEqual(
            run["failed"],
            {"step": "read_instances", "index": 4, "failed_at": "2026-10-15T02:00:50Z"},
        )
        self.assertEqual((run["status"], run["died"]), ("incomplete", None))

    def test_message_is_omitted_when_it_was_not_stored(self) -> None:
        store = _failed_store()
        store.failures = [
            make_failure(
                "prod", R1, 3, FAIL_AT, error={"type": "KeyError", "traceback": "KeyError\n"}
            )
        ]
        step = _first_run(client_for(store))["steps"][3]
        self.assertEqual(step["error"], {"type": "KeyError", "traceback": "KeyError\n"})

    def test_overview_card_is_failed_without_the_traceback(self) -> None:
        body = client_for(_failed_store()).get("/api/overview").json()
        (card,) = body["pipelines"]
        self.assertEqual((card["card_status"], card["needs_attention"]), ("failed", True))
        latest = card["latest"]
        self.assertEqual(latest["failed_step"], "read_instances")
        self.assertEqual(latest["failed_at"], "2026-10-15T02:00:50Z")
        self.assertEqual(latest["error"], {"type": "ValueError", "message": "boom"})

    def test_a_failed_run_with_an_old_heartbeat_is_never_judged_died(self) -> None:
        store = _failed_store()
        run = _first_run(client_for(store))
        self.assertIsNone(run["died"])
        self.assertEqual(store.write_calls, [])  # the monitor wrote no died verdict

    def test_the_monitor_never_writes_failure_data(self) -> None:
        store = _failed_store()
        client = client_for(store)
        client.get("/api/runs", params=RUNS)
        client.get("/api/overview")
        self.assertEqual(store.write_calls, [])

    def test_damaged_failure_item_counts_as_unreadable_and_the_run_still_shows(self) -> None:
        store = _failed_store()
        store.failures.append((store.failures[0][0].replace(":failed:04-", ":failed:05-"), "{nope"))
        body = client_for(store).get("/api/runs", params=RUNS).json()
        self.assertEqual(body["unreadable_total"], 1)
        self.assertEqual(body["runs"][0]["unreadable"], 1)
        self.assertEqual(body["runs"][0]["steps"][3]["state"], "failed")
        overview = client_for(store).get("/api/overview").json()
        self.assertEqual(overview["unreadable_total"], 1)

    def test_a_store_without_failure_items_gives_null_fields(self) -> None:
        store = FakeStore(make_run("prod", R1))
        run = _first_run(client_for(store))
        self.assertIsNone(run["failed"])
        (card,) = client_for(store).get("/api/overview").json()["pipelines"]
        self.assertEqual((card["latest"]["failed_step"], card["latest"]["error"]), (None, None))


class TestRunsDurations(unittest.TestCase):
    """Specs 012: /api/runs durations; /api/overview latest duration."""

    def test_runs_carry_step_and_run_durations(self) -> None:
        raw = make_run("prod", R1, step_seconds=[10, 20, 5, 5, 5, 60, 10, 4, 6])
        body = (
            client_for(FakeStore(raw))
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        run = body["runs"][0]
        self.assertEqual(
            run["duration"], {"seconds": 125, "running": False, "complete": True, "slow": False}
        )
        self.assertEqual(run["bottleneck"], "read_gads_clickview")
        step = run["steps"][1]
        self.assertEqual((step["duration_seconds"], step["duration_approx"]), (20, False))

    def test_old_library_runs_are_approximate(self) -> None:
        raw = make_run("prod", R1, step_seconds=[10] * 9, exact=False)
        body = (
            client_for(FakeStore(raw))
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        self.assertTrue(all(s["duration_approx"] for s in body["runs"][0]["steps"]))

    def test_overview_latest_duration(self) -> None:
        raw = make_run("prod", R1, step_seconds=[10] * 9)
        card = client_for(FakeStore(raw)).get("/api/overview").json()["pipelines"][0]
        self.assertEqual(card["latest"]["duration_seconds"], 90)
        self.assertFalse(card["latest"]["duration_running"])
        self.assertEqual(card["card_status"], "ok")


def history(durations: List[int], env: str = "prod", day: int = 1) -> List[Tuple[str, str]]:
    """One finished run per entry (oldest first, one hour apart) whose nine steps add up to it."""
    raw: List[Tuple[str, str]] = []
    for i, total in enumerate(durations):
        run_id = f"202610{day:02d}T{i:02d}0000Z"
        steps = [total // 9] * 9
        steps[-1] += total - sum(steps)
        raw += make_run(env, run_id, step_seconds=steps)
    return raw


class TestSlowRuns(unittest.TestCase):
    """Specs 012: typical durations and the Slower than usual flag."""

    def runs(self, raw: List[Tuple[str, str]], **kw: object) -> Dict[str, Any]:
        client = client_for(
            FakeStore(raw), now=datetime(2026, 10, 2, 12, tzinfo=timezone.utc), **kw
        )
        return client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()

    def test_typical_values_and_the_one_slow_run(self) -> None:
        body = self.runs(history([600] * 7 + [2100]))
        self.assertEqual(body["typical"]["median_seconds"], 600)
        self.assertEqual(body["typical"]["sample"], 8)
        self.assertEqual(body["typical"]["slow_after_seconds"], 1200)
        slow = [r["run_id"] for r in body["runs"] if r["duration"]["slow"]]
        self.assertEqual(slow, ["20261001T070000Z"])

    def test_typical_covers_every_run_read_not_only_the_limit(self) -> None:
        raw = history([600] * 7 + [2100])
        client = client_for(FakeStore(raw), now=datetime(2026, 10, 2, 12, tzinfo=timezone.utc))
        body = client.get(
            "/api/runs", params={"env": "prod", "pipeline": "callrail", "limit": 1}
        ).json()
        self.assertEqual(len(body["runs"]), 1)
        self.assertEqual(body["typical"]["sample"], 8)
        self.assertTrue(body["runs"][0]["duration"]["slow"])

    def test_typical_is_null_below_the_minimum_and_nothing_is_flagged(self) -> None:
        body = self.runs(history([600, 600, 600, 5000]))
        self.assertIsNone(body["typical"])
        self.assertFalse(any(r["duration"]["slow"] for r in body["runs"]))

    def test_settings_change_the_result(self) -> None:
        raw = history([600] * 7 + [1000])
        self.assertFalse(self.runs(raw)["runs"][0]["duration"]["slow"])
        tight = self.runs(raw, slow_run_multiple=1.5)
        self.assertTrue(tight["runs"][0]["duration"]["slow"])
        few = self.runs(raw, duration_min_runs=20)
        self.assertIsNone(few["typical"])

    def test_overview_marks_the_latest_run_but_not_its_status_or_order(self) -> None:
        raw = history([600] * 7 + [2100]) + make_run("prod", "20261001T000000Z", pipeline="other")
        client = client_for(FakeStore(raw), now=datetime(2026, 10, 1, 9, tzinfo=timezone.utc))
        cards = {c["name"]: c for c in client.get("/api/overview").json()["pipelines"]}
        self.assertTrue(cards["callrail"]["latest"]["slow"])
        self.assertEqual(cards["callrail"]["card_status"], "ok")
        self.assertFalse(cards["callrail"]["needs_attention"])
        self.assertFalse(cards["other"]["latest"]["slow"])


class TestEventsEndpoint(unittest.TestCase):
    """Specs 012 contracts/api.md: GET /api/runs/{pipeline}/{env}/{run_id}/events."""

    URL = f"/api/runs/callrail/prod/{R1}/events"

    def store(self) -> FakeStore:
        store = FakeStore(make_run("prod", R1, step_seconds=[10] * 9))
        store.add_event(
            R1,
            "info",
            1,
            "2026-10-15T02:00:20.250Z",
            "Loaded batch 3",
            "read_partners",
            {"rows": 1200},
        )
        store.add_event(
            R1, "warning", 2, "2026-10-15T02:00:25.100Z", "slow source", "read_partners"
        )
        store.add_event(R1, "error", 3, "2026-10-15T02:00:26.000Z", "one batch skipped")
        return store

    def get(self, store: Optional[FakeStore] = None, **params: object) -> Any:
        return client_for(store or self.store()).get(self.URL, params=params)  # type: ignore[arg-type]

    def test_shape_and_merge_of_derived_and_recorded_events(self) -> None:
        body = self.get().json()
        self.assertEqual(
            set(body),
            {
                "env",
                "pipeline",
                "run_id",
                "generated_at",
                "total",
                "matched",
                "offset",
                "has_more",
                "recorded",
                "dropped",
                "unreadable",
                "events",
            },
        )
        self.assertEqual((body["env"], body["pipeline"], body["run_id"]), ("prod", "callrail", R1))
        self.assertEqual((body["recorded"], body["dropped"], body["unreadable"]), (3, 0, 0))
        self.assertEqual(body["total"], body["matched"])
        self.assertEqual((body["offset"], body["has_more"]), (0, False))
        events = body["events"]
        self.assertEqual(events[0]["kind"], "run_started")
        self.assertEqual(
            set(events[0]), {"id", "ts", "level", "step", "message", "fields", "source", "kind"}
        )
        custom = [e for e in events if e["source"] == "pipeline"]
        self.assertEqual([e["id"] for e in custom], ["r:info:1", "r:warning:2", "r:error:3"])
        self.assertEqual(custom[0]["fields"], {"rows": 1200})
        self.assertEqual([e["ts"] for e in events], sorted(e["ts"] for e in events))

    def test_defaults_and_paging(self) -> None:
        full = self.get().json()["events"]
        first = self.get(limit=5).json()
        self.assertEqual((len(first["events"]), first["has_more"]), (5, True))
        second = self.get(limit=5, offset=5).json()
        self.assertEqual(first["events"] + second["events"], full[:10])
        last = self.get(offset=len(full) - 1).json()
        self.assertEqual((len(last["events"]), last["has_more"]), (1, False))

    def test_level_and_step_filters(self) -> None:
        body = self.get(level="warning,error").json()
        self.assertEqual({e["level"] for e in body["events"]}, {"warning", "error"})
        self.assertEqual(body["matched"], 2)
        self.assertGreater(body["total"], 2)
        body = self.get(step="read_partners").json()
        self.assertEqual({e["step"] for e in body["events"]}, {"read_partners"})
        self.assertEqual(self.get(step="nope").json()["matched"], 0)

    def test_bad_parameters_are_400(self) -> None:
        for params in ({"level": "debug"}, {"limit": 0}, {"limit": 501}, {"offset": -1}):
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 400)
        client = client_for(self.store())
        self.assertEqual(client.get(f"/api/runs/callrail/nope/{R1}/events").status_code, 400)
        self.assertEqual(client.get(f"/api/runs/Bad Name/prod/{R1}/events").status_code, 400)
        self.assertEqual(client.get("/api/runs/callrail/prod/notarun/events").status_code, 400)

    def test_an_unknown_run_is_an_empty_timeline_not_404(self) -> None:
        response = client_for(self.store()).get("/api/runs/callrail/prod/20200101T000000Z/events")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["total"], body["matched"], body["events"]), (0, 0, []))

    def test_a_run_without_author_events_is_the_derived_timeline(self) -> None:
        store = FakeStore(make_run("prod", R1, step_seconds=[10] * 9, exact=False))
        body = self.get(store).json()
        self.assertEqual((body["recorded"], body["dropped"]), (0, 0))
        self.assertGreater(body["total"], 0)
        self.assertTrue(all(e["source"] == "monitor" for e in body["events"]))

    def test_a_damaged_element_is_counted_and_the_rest_is_shown(self) -> None:
        store = self.store()
        store.add_event(R1, "info", 4, "x", raw="{nope")
        body = self.get(store).json()
        self.assertEqual((body["recorded"], body["unreadable"]), (3, 1))

    def test_dropped_events_are_reported(self) -> None:
        store = self.store()
        store.add_event(R1, "info", 40, "2026-10-15T02:00:30.000Z")
        body = self.get(store).json()
        self.assertEqual(body["recorded"], 4)
        self.assertEqual(body["dropped"], 36)

    def test_a_failure_is_an_error_entry_without_a_traceback(self) -> None:
        start = datetime(2026, 10, 15, 2, 0, 16, tzinfo=timezone.utc)
        store = FakeStore(make_run("prod", R1, missing_from=2))
        store.failures.append(
            make_failure("prod", R1, 2, start + timedelta(seconds=31), started_at=start)
        )
        body = self.get(store, level="error").json()
        kinds = [e["kind"] for e in body["events"]]
        self.assertEqual(kinds, ["step_failed", "run_stopped"])
        self.assertNotIn("File", json.dumps(body))

    def test_store_down_is_503(self) -> None:
        store = self.store()
        store.fail = True
        self.assertEqual(self.get(store).status_code, 503)

    def test_a_refused_event_read_still_gives_the_derived_timeline(self) -> None:
        store = self.store()
        store.events_denied = True
        body = self.get(store).json()
        self.assertEqual(body["recorded"], 0)
        self.assertGreater(body["total"], 0)

    def test_the_endpoint_never_writes(self) -> None:
        store = self.store()
        self.get(store)
        self.assertEqual(store.write_calls, [])


class TestEventCounts(unittest.TestCase):
    """Specs 012 US5: warning and error counts come from list lengths, never from event bodies."""

    def store(self) -> FakeStore:
        store = FakeStore(make_run("prod", R1) + make_run("prod", R2))
        store.add_event(R1, "info", 1, "2026-10-15T02:00:20.000Z")
        for n in (2, 3):
            store.add_event(R1, "warning", n, "2026-10-15T02:00:21.000Z")
        store.add_event(R1, "error", 4, "2026-10-15T02:00:22.000Z")
        return store

    def test_runs_carry_counts_zero_when_none(self) -> None:
        body = (
            client_for(self.store())
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        by_id = {r["run_id"]: r for r in body["runs"]}
        self.assertEqual(by_id[R1]["event_counts"], {"warning": 2, "error": 1})
        self.assertEqual(by_id[R2]["event_counts"], {"warning": 0, "error": 0})

    def test_overview_card_has_the_latest_runs_counts(self) -> None:
        card = client_for(self.store()).get("/api/overview").json()["pipelines"][0]
        self.assertEqual((card["latest"]["warnings"], card["latest"]["errors"]), (2, 1))

    def test_runs_and_overview_never_read_event_bodies(self) -> None:
        store = self.store()
        client = client_for(store)
        client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        client.get("/api/overview")
        self.assertEqual(store.read_events_calls, 0)

    def test_a_step_failure_is_not_counted_again(self) -> None:
        start = datetime(2026, 10, 15, 2, 0, 16, tzinfo=timezone.utc)
        store = FakeStore(make_run("prod", R1, missing_from=2))
        store.failures.append(
            make_failure("prod", R1, 2, start + timedelta(seconds=5), started_at=start)
        )
        run = (
            client_for(store)
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()["runs"][0]
        )
        self.assertIsNotNone(run["failed"])
        self.assertEqual(run["event_counts"], {"warning": 0, "error": 0})

    def test_a_refused_count_read_gives_zeros_and_pages_still_load(self) -> None:
        store = self.store()
        store.events_denied = True
        client = client_for(store)
        run = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()[
            "runs"
        ][0]
        self.assertEqual(run["event_counts"], {"warning": 0, "error": 0})
        self.assertEqual(client.get("/api/overview").status_code, 200)

    def test_event_counts_cached_with_the_window(self) -> None:
        store = self.store()
        clock = Clock()
        client = client_for(store, clock=clock)
        first = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()
        store.add_event(R1, "error", 9, "2026-10-15T02:00:30.000Z")
        cached = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()
        self.assertEqual(first["runs"][0]["event_counts"], cached["runs"][0]["event_counts"])
        clock.t = 60
        fresh = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()
        self.assertEqual(fresh["runs"][0]["event_counts"]["error"], 2)


class TestOlderPipelinesAndMonitors(unittest.TestCase):
    """Specs 012 US7: data from library 0.2.0/0.3.0 shows fully, without banners or errors."""

    def old_store(self) -> FakeStore:
        return FakeStore(make_run("prod", R1, step_seconds=[10] * 9, exact=False))

    def test_every_endpoint_answers_for_a_run_without_the_new_data(self) -> None:
        client = client_for(self.old_store())
        runs = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        overview = client.get("/api/overview")
        events = client.get(f"/api/runs/callrail/prod/{R1}/events")
        for response in (runs, overview, events):
            self.assertEqual(response.status_code, 200)
        run = runs.json()["runs"][0]
        self.assertTrue(all(s["duration_approx"] for s in run["steps"]))
        self.assertEqual(run["duration"]["seconds"], 90)
        self.assertEqual(runs.json()["unreadable_total"], 0)
        self.assertEqual(overview.json()["unreadable_total"], 0)
        body = events.json()
        self.assertEqual((body["recorded"], body["dropped"], body["unreadable"]), (0, 0, 0))

    def test_inconsistent_times_give_no_duration_and_nothing_negative(self) -> None:
        raw = make_run("prod", R1, step_seconds=[10] * 9)
        key, value = raw[1]
        record = json.loads(value)
        record["started_at"] = "2026-10-15T02:30:00Z"  # after its own finish
        record.pop("duration_ms")
        raw[1] = (key, json.dumps(record))
        body = (
            client_for(FakeStore(raw))
            .get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
            .json()
        )
        first = body["runs"][0]["steps"][0]
        self.assertIsNone(first["duration_seconds"])
        self.assertNotIn(
            "-",
            json.dumps([s.get("duration_seconds") for s in body["runs"][0]["steps"]]).replace(
                "null", ""
            ),
        )

    def test_the_monitor_makes_no_write_but_the_died_verdict(self) -> None:
        start = datetime(2026, 10, 15, 2, 0, 16, tzinfo=timezone.utc)
        store = FakeStore(make_run("prod", R1, missing_from=2, step_seconds=[10] * 9))
        store.markers.append(make_marker("prod", R1, 2, NOW - timedelta(seconds=400)))
        store.alive.append(make_alive("prod", R1, NOW - timedelta(seconds=300)))
        store.add_event(R1, "warning", 1, "2026-10-15T02:00:20.000Z")
        client = client_for(store)
        client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        client.get("/api/overview")
        client.get(f"/api/runs/callrail/prod/{R1}/events")
        self.assertTrue(store.write_calls)
        self.assertTrue(all(call[0].endswith(":died") for call in store.write_calls))
        self.assertEqual(start.year, 2026)


if __name__ == "__main__":
    unittest.main()


class TestMetricsApi(unittest.TestCase):
    """Specs 013 contracts/api.md."""

    def test_metrics_served_on_the_step_with_flags_and_counts(self) -> None:
        store = FakeStore(
            declare_metrics(
                make_run("prod", R1),
                "read_callrail_call",
                [{"name": "rejected", "label": "Rejected", "unit": "rows", "warn_above": 100}],
            )
        )
        store.metrics = [make_metrics("prod", R1, 1, {"rejected": 150, "retries": 3})]
        run = _first_run(client_for(store))
        step = [s for s in run["steps"] if s["name"] == "read_callrail_call"][0]
        self.assertEqual(
            step["metrics"][0],
            {
                "name": "rejected",
                "label": "Rejected",
                "value": 150,
                "unit": "rows",
                "declared": True,
                "flag": "above",
                "updated_at": None,
            },
        )
        self.assertEqual(step["metrics"][1]["name"], "retries")
        self.assertEqual((step["metrics_over"], run["metrics_over"]), (1, 1))
        self.assertEqual(run["status"], "complete")

    def test_runs_without_metrics_have_no_metric_keys_on_steps(self) -> None:
        run = _first_run(client_for(FakeStore(make_run("prod", R1))))
        self.assertEqual(run["metrics_over"], 0)
        self.assertTrue(all("metrics" not in s and "metrics_over" not in s for s in run["steps"]))

    def test_a_damaged_record_adds_to_unreadable_and_the_rest_is_served(self) -> None:
        store = FakeStore(make_run("prod", R1))
        good = make_metrics("prod", R1, 1, {"rows": 2})
        bad_key, _ = make_metrics("prod", R1, 2, {"rows": 2})
        store.metrics = [good, (bad_key, "{nope")]
        client = client_for(store)
        body = client.get("/api/runs", params={"env": "prod", "pipeline": "callrail"}).json()
        run = body["runs"][0]
        self.assertEqual(run["unreadable"], 1)
        self.assertEqual(body["unreadable_total"], 1)
        step = [s for s in run["steps"] if s["name"] == "read_callrail_call"][0]
        self.assertEqual(step["metrics"][0]["value"], 2)

    def test_store_down_is_still_503_and_the_window_includes_metrics(self) -> None:
        store = FakeStore(make_run("prod", R1))
        store.fail = True
        response = client_for(store).get(
            "/api/runs", params={"env": "prod", "pipeline": "callrail"}
        )
        self.assertEqual(response.status_code, 503)
        store.fail = False
        store.metrics = [make_metrics("prod", R1, 0, {"x": 1})]
        again = client_for(store).get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        self.assertEqual(again.json()["runs"][0]["steps"][0]["metrics"][0]["value"], 1)

    def test_the_monitor_makes_no_write_for_metrics(self) -> None:
        store = FakeStore(make_run("prod", R1))
        store.metrics = [make_metrics("prod", R1, 0, {"x": 1})]
        client_for(store).get("/api/runs", params={"env": "prod", "pipeline": "callrail"})
        self.assertEqual(store.write_calls, [])
