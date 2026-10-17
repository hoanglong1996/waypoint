import unittest
from typing import Any, Dict, List, Optional

from app.domain.overview import build_overview

ORDER = ["prod", "qa"]


def step(
    name: str, state: str = "done", output: Optional[int] = 1, inputs: int = 0
) -> Dict[str, Any]:
    if state in ("done", "unplanned"):
        ins = [{"name": "rows", "value": inputs}] if inputs else []
        return {"name": name, "state": state, "inputs": ins, "output": output}
    return {"name": name, "state": state}


def run(
    env: str,
    run_id: str,
    steps: Optional[List[Dict[str, Any]]] = None,
    status: str = "complete",
    stale: bool = False,
    loss: Optional[List[str]] = None,
    missing: Optional[str] = None,
    label: Optional[str] = None,
    flow_steps: Optional[List[Dict[str, Any]]] = None,
    died: Optional[Dict[str, Any]] = None,
    failed: Optional[Dict[str, Any]] = None,
    duration: Optional[Dict[str, Any]] = None,
    event_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    steps = steps if steps is not None else [step("a", output=5), step("b", output=9, inputs=5)]
    flow = None
    if label is not None or flow_steps is not None:
        flow = {
            "label": label,
            "groups": [],
            "steps": flow_steps or [{"name": s["name"], "label": s["name"].upper()} for s in steps],
        }
    return {
        "run_id": run_id,
        "env": env,
        "status": status,
        "stale": stale,
        "started_at": "2026-10-16T02:00:00Z",
        "ended_at": "2026-10-16T02:01:00Z",
        "age_seconds": 100,
        "loss_steps": loss or [],
        "first_missing_step": missing,
        "unreadable": 0,
        "died": died,
        "failed": failed,
        "flow": flow,
        "steps": steps,
        **({"duration": duration} if duration is not None else {}),
        **({"event_counts": event_counts} if event_counts is not None else {}),
    }


def one(runs_by_env: Dict[str, List[Dict[str, Any]]], name: str = "p") -> Dict[str, Any]:
    result = build_overview({env: {name: runs} for env, runs in runs_by_env.items()}, ORDER)
    return result[0]


class TestNewestAcrossEnvironments(unittest.TestCase):
    def test_greatest_run_id_wins_and_carries_its_env(self) -> None:
        card = one(
            {"prod": [run("prod", "20261015T020000Z")], "qa": [run("qa", "20261016T020000Z")]}
        )
        self.assertEqual(card["latest"]["env"], "qa")
        self.assertEqual(card["latest"]["run_id"], "20261016T020000Z")

    def test_equal_run_ids_go_to_the_first_environment_in_order(self) -> None:
        same = "20261016T020000Z"
        card = one({"qa": [run("qa", same)], "prod": [run("prod", same)]})
        self.assertEqual(card["latest"]["env"], "prod")

    def test_environments_list_only_those_with_runs_in_configured_order(self) -> None:
        card = one({"prod": [], "qa": [run("qa", "20261016T020000Z")]})
        self.assertEqual(card["environments"], ["qa"])
        both = one(
            {"qa": [run("qa", "20261016T020000Z")], "prod": [run("prod", "20261015T020000Z")]}
        )
        self.assertEqual(both["environments"], ["prod", "qa"])

    def test_pipeline_without_any_run_is_left_out(self) -> None:
        self.assertEqual(build_overview({"prod": {"p": []}, "qa": {}}, ORDER), [])

    def test_label_comes_from_the_flow_else_the_name(self) -> None:
        self.assertEqual(
            one({"prod": [run("prod", "20261016T020000Z", label="CallRail")]})["label"], "CallRail"
        )
        self.assertEqual(one({"prod": [run("prod", "20261016T020000Z")]})["label"], "p")


class TestCardStatus(unittest.TestCase):
    def status(self, **kw: Any) -> Dict[str, Any]:
        return one({"prod": [run("prod", "20261016T020000Z", **kw)]})

    def test_first_match_wins_running_stale_incomplete_lost_ok(self) -> None:
        self.assertEqual(
            self.status(status="running", stale=True, loss=["b"])["card_status"], "running"
        )
        self.assertEqual(
            self.status(stale=True, status="incomplete", loss=["b"])["card_status"], "stale"
        )
        self.assertEqual(
            self.status(status="incomplete", loss=["b"], missing="c")["card_status"], "incomplete"
        )
        self.assertEqual(self.status(loss=["b"])["card_status"], "lost")
        self.assertEqual(self.status()["card_status"], "ok")

    def test_only_stale_incomplete_and_lost_need_attention(self) -> None:
        self.assertTrue(self.status(stale=True)["needs_attention"])
        self.assertTrue(self.status(status="incomplete", missing="c")["needs_attention"])
        self.assertTrue(self.status(loss=["b"])["needs_attention"])
        self.assertFalse(self.status(status="running")["needs_attention"])
        self.assertFalse(self.status()["needs_attention"])

    def test_reason_fields(self) -> None:
        stalled = self.status(
            status="incomplete",
            missing="b",
            steps=[step("a"), {"name": "b", "state": "stalled", "elapsed_seconds": 1800}],
        )
        self.assertEqual(stalled["latest"]["stalled_step"], "b")
        self.assertEqual(stalled["latest"]["stalled_seconds"], 1800)
        self.assertEqual(stalled["latest"]["first_missing_step"], "b")
        self.assertEqual(self.status(loss=["b", "c"])["latest"]["loss_steps"], ["b", "c"])


class TestOrder(unittest.TestCase):
    def test_attention_first_then_the_rest_each_by_label(self) -> None:
        by_env = {
            "prod": {
                "zeta": [run("prod", "20261016T020000Z", label="Zeta", stale=True)],
                "alpha": [run("prod", "20261016T020000Z", label="Alpha")],
                "mid": [run("prod", "20261016T020000Z", label="mid", loss=["b"])],
                "beta": [run("prod", "20261016T020000Z", label="Beta", status="running")],
            }
        }
        names = [c["name"] for c in build_overview(by_env, ORDER)]
        self.assertEqual(names, ["mid", "zeta", "alpha", "beta"])


class TestHeadline(unittest.TestCase):
    def numbers(self, steps: List[Dict[str, Any]], **kw: Any) -> List[Dict[str, Any]]:
        card = one({"prod": [run("prod", "20261016T020000Z", steps=steps, **kw)]})
        headline: List[Dict[str, Any]] = card["latest"]["headline"]
        return headline

    def test_first_largest_middle_last(self) -> None:
        h = self.numbers(
            [
                step("a", output=10),
                step("b", output=50, inputs=10),
                step("c", output=30, inputs=50),
                step("d", output=None, inputs=30),
            ]
        )
        self.assertEqual([x["key"] for x in h], ["first", "peak", "last"])
        self.assertEqual([x["step"] for x in h], ["a", "b", "d"])
        self.assertEqual(
            [x["value"] for x in h], [10, 50, 30]
        )  # a step that returns nothing uses its input

    def test_unreported_step_has_null_value_and_two_steps_have_no_middle(self) -> None:
        h = self.numbers(
            [step("a", output=4), step("b", state="missing")], status="incomplete", missing="b"
        )
        self.assertEqual([x["value"] for x in h], [4, None, None])
        self.assertIsNone(h[1]["step"])

    def test_no_peak_among_unreported_middle_steps_falls_back_to_the_second_step(self) -> None:
        h = self.numbers(
            [
                step("a", output=4),
                step("b", state="waiting"),
                step("c", state="waiting"),
                step("d", state="waiting"),
            ],
            status="running",
        )
        self.assertEqual(h[1]["step"], "b")
        self.assertIsNone(h[1]["value"])

    def test_steps_outside_the_flow_are_not_headline_steps(self) -> None:
        h = self.numbers(
            [step("a", output=1), step("b", output=2), step("x", state="unplanned", output=999)]
        )
        self.assertEqual([x["step"] for x in h], ["a", None, "b"])

    def test_label_is_the_flow_label_else_the_name(self) -> None:
        h = self.numbers(
            [step("a", output=1), step("b", output=2)],
            flow_steps=[{"name": "a", "label": "Accounts"}, {"name": "b", "label": None}],
            label="X",
        )
        self.assertEqual([h[0]["label"], h[2]["label"]], ["Accounts", "b"])


SEEN = "2026-10-16T02:07:45Z"
DIED = {"judged_at": "2026-10-16T02:09:20Z", "last_seen_at": SEEN, "recorded": True}


def died_run(env: str = "prod", run_id: str = "20261016T020000Z", **over: Any) -> Dict[str, Any]:
    steps = [
        step("a", output=5),
        {"name": "b", "state": "died", "started_at": "2026-10-16T02:03:00Z", "last_seen_at": SEEN},
        {"name": "c", "state": "missing", "missing": True},
    ]
    return run(env, run_id, steps, status="incomplete", missing="b", died=DIED, **over)


class TestDiedCard(unittest.TestCase):
    """specs/009-run-liveness-heartbeat/contracts/api.md"""

    def test_died_run_gives_a_died_card_that_needs_attention(self) -> None:
        card = one({"prod": [died_run()]})
        self.assertEqual(card["card_status"], "died")
        self.assertTrue(card["needs_attention"])
        self.assertEqual(card["latest"]["died_step"], "b")
        self.assertEqual(card["latest"]["last_seen_at"], SEEN)

    def test_died_wins_over_stale_and_incomplete(self) -> None:
        card = one({"prod": [died_run(stale=True)]})
        self.assertEqual(card["card_status"], "died")

    def test_running_still_wins_over_everything(self) -> None:
        live = run("prod", "20261016T020000Z", [step("a", state="running")], status="running")
        self.assertEqual(one({"prod": [live]})["card_status"], "running")

    def test_other_cards_have_no_died_fields_set(self) -> None:
        card = one({"prod": [run("prod", "20261016T020000Z")]})
        self.assertEqual(card["card_status"], "ok")
        self.assertIsNone(card["latest"]["died_step"])
        self.assertIsNone(card["latest"]["last_seen_at"])

    def test_died_card_is_listed_with_the_problem_cards_first(self) -> None:
        cards = build_overview(
            {
                "prod": {
                    "alpha": [run("prod", "20261016T020000Z")],
                    "bravo": [died_run()],
                    "charlie": [run("prod", "20261016T020000Z", stale=True)],
                    "delta": [run("prod", "20261016T020000Z")],
                }
            },
            ORDER,
        )
        self.assertEqual([c["name"] for c in cards], ["bravo", "charlie", "alpha", "delta"])
        self.assertEqual([c["card_status"] for c in cards], ["died", "stale", "ok", "ok"])

    def test_a_died_run_of_an_old_recorder_without_the_key_is_not_died(self) -> None:
        legacy = run("prod", "20261016T020000Z", status="incomplete", missing="b")
        del legacy["died"]
        self.assertEqual(one({"prod": [legacy]})["card_status"], "incomplete")


FAILED_AT = "2026-10-16T02:03:41Z"
ERROR = {"type": "ValueError", "message": "boom", "traceback": "Traceback...\nValueError: boom\n"}


def failed_run(env: str = "prod", run_id: str = "20261016T020000Z", **over: Any) -> Dict[str, Any]:
    steps = [
        step("a", output=5),
        {
            "name": "b",
            "state": "failed",
            "started_at": "2026-10-16T02:03:00Z",
            "failed_at": FAILED_AT,
            "error": ERROR,
        },
        {"name": "c", "state": "missing", "missing": True},
    ]
    failed = {"step": "b", "index": 2, "failed_at": FAILED_AT}
    return run(env, run_id, steps, status="incomplete", missing="b", failed=failed, **over)


class TestFailedCard(unittest.TestCase):
    """specs/011-step-failure-errors/contracts/api.md"""

    def test_failed_run_gives_a_failed_card_that_needs_attention(self) -> None:
        card = one({"prod": [failed_run()]})
        self.assertEqual(card["card_status"], "failed")
        self.assertTrue(card["needs_attention"])
        latest = card["latest"]
        self.assertEqual((latest["failed_step"], latest["failed_at"]), ("b", FAILED_AT))
        self.assertEqual(latest["error"], {"type": "ValueError", "message": "boom"})
        self.assertNotIn("traceback", latest["error"])

    def test_message_is_left_out_when_it_was_not_stored(self) -> None:
        bare = failed_run()
        bare["steps"][1]["error"] = {"type": "KeyError", "traceback": "KeyError\n"}
        self.assertEqual(one({"prod": [bare]})["latest"]["error"], {"type": "KeyError"})

    def test_priority_running_failed_died_stale_incomplete_lost_ok(self) -> None:
        live = run("prod", "20261016T020000Z", [step("a", state="running")], status="running")
        live["failed"] = {"step": "a", "index": 1, "failed_at": FAILED_AT}
        self.assertEqual(one({"prod": [live]})["card_status"], "running")
        both = failed_run(stale=True)
        both["died"] = DIED
        self.assertEqual(one({"prod": [both]})["card_status"], "failed")
        self.assertEqual(one({"prod": [died_run(stale=True)]})["card_status"], "died")

    def test_other_cards_have_no_failed_fields_set(self) -> None:
        latest = one({"prod": [run("prod", "20261016T020000Z")]})["latest"]
        self.assertEqual(
            (latest["failed_step"], latest["failed_at"], latest["error"]), (None, None, None)
        )

    def test_a_run_of_an_old_recorder_without_the_key_is_not_failed(self) -> None:
        legacy = run("prod", "20261016T020000Z", status="incomplete", missing="b")
        del legacy["failed"]
        card = one({"prod": [legacy]})
        self.assertEqual(card["card_status"], "incomplete")
        self.assertIsNone(card["latest"]["failed_step"])

    def test_failed_cards_lead_the_attention_group_the_rest_stay_by_label(self) -> None:
        inc = run("prod", "20261016T020000Z", status="incomplete", missing="b")
        lost = run("prod", "20261016T020000Z", loss=["b"])
        cards = build_overview(
            {
                "prod": {
                    "a_ok": [run("prod", "20261016T020000Z")],
                    "b_lost": [lost],
                    "c_inc": [inc],
                    "d_stale": [run("prod", "20261016T020000Z", stale=True)],
                    "e_died": [died_run()],
                    "f_failed": [failed_run()],
                    "g_failed": [failed_run()],
                }
            },
            ORDER,
        )
        self.assertEqual(
            [c["name"] for c in cards],
            ["f_failed", "g_failed", "b_lost", "c_inc", "d_stale", "e_died", "a_ok"],
        )


class TestDurationFields(unittest.TestCase):
    """Specs 012: the card carries the latest run's duration, slow flag and event counts."""

    def test_duration_fields_come_from_the_latest_run(self) -> None:
        d = {"seconds": 655, "running": False, "complete": True, "slow": False}
        card = one({"prod": [run("prod", "20261016T020000Z", duration=d)]})
        self.assertEqual(card["latest"]["duration_seconds"], 655)
        self.assertFalse(card["latest"]["duration_running"])
        self.assertFalse(card["latest"]["slow"])

    def test_running_and_slow_flags(self) -> None:
        d = {"seconds": 4000, "running": True, "complete": False, "slow": True}
        latest = one({"prod": [run("prod", "20261016T020000Z", status="running", duration=d)]})[
            "latest"
        ]
        self.assertTrue(latest["duration_running"])
        self.assertTrue(latest["slow"])

    def test_a_run_without_the_keys_has_empty_values(self) -> None:
        latest = one({"prod": [run("prod", "20261016T020000Z")]})["latest"]
        self.assertIsNone(latest["duration_seconds"])
        self.assertEqual((latest["duration_running"], latest["slow"]), (False, False))
        self.assertEqual((latest["warnings"], latest["errors"]), (0, 0))

    def test_event_counts(self) -> None:
        card = one(
            {"prod": [run("prod", "20261016T020000Z", event_counts={"warning": 2, "error": 1})]}
        )
        self.assertEqual((card["latest"]["warnings"], card["latest"]["errors"]), (2, 1))

    def test_duration_never_changes_status_or_order(self) -> None:
        slow = {"seconds": 9999, "running": False, "complete": True, "slow": True}
        fast = {"seconds": 5, "running": False, "complete": True, "slow": False}
        cards = build_overview(
            {
                "prod": {
                    "a": [run("prod", "20261016T020000Z", duration=slow)],
                    "b": [run("prod", "20261016T020000Z", duration=fast)],
                }
            },
            ORDER,
        )
        self.assertEqual([c["name"] for c in cards], ["a", "b"])
        self.assertEqual({c["card_status"] for c in cards}, {"ok"})
        self.assertFalse(any(c["needs_attention"] for c in cards))


if __name__ == "__main__":
    unittest.main()
