import json
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import (
    FakeStore,
    flow_value,
    make_alive,
    make_died,
    make_failure,
    make_marker,
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
                "failed",  # specs/011: the only new key on a run
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


if __name__ == "__main__":
    unittest.main()
