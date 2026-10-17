import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.domain.analysis import build_runs
from app.domain.parsing import (
    parse_alive,
    parse_died,
    parse_failures,
    parse_flows,
    parse_markers,
    parse_records,
)
from tests.fakes import (
    PIPELINE,
    flow_value,
    make_alive,
    make_died,
    make_failure,
    make_flow,
    make_marker,
    make_run,
    split,
)

NOW = datetime(2026, 10, 15, 3, 0, 0, tzinfo=timezone.utc)
R1 = "20261015T020000Z"
R2 = "20261014T020000Z"


def runs_for(
    raw: List[Tuple[str, str]],
    now: datetime = NOW,
    stale_hours: float = 26.0,
    env: str = "prod",
    markers: Optional[List[Tuple[str, str]]] = None,
    stall_seconds: float = 900.0,
    beats: Optional[Dict[str, datetime]] = None,
    verdicts: Optional[Dict[str, Tuple[datetime, datetime]]] = None,
    dead_seconds: float = 90.0,
    failures: Optional[List[Tuple[str, str]]] = None,
) -> List[Dict[str, Any]]:
    raw_flows, raw_records, raw_markers = split(raw)
    alive = parse_alive(env, PIPELINE, [make_alive(env, r, at) for r, at in (beats or {}).items()])
    died = parse_died(
        env, PIPELINE, [make_died(env, r, j, seen) for r, (j, seen) in (verdicts or {}).items()]
    )
    return build_runs(
        parse_records(env, PIPELINE, raw_records),
        env,
        PIPELINE,
        now,
        stale_hours,
        flows=parse_flows(env, PIPELINE, raw_flows),
        markers=parse_markers(env, PIPELINE, (markers or []) + raw_markers),
        stall_seconds=stall_seconds,
        alive=alive,
        verdicts=died,
        dead_seconds=dead_seconds,
        failures=parse_failures(env, PIPELINE, failures or [])[0],
    )


class TestBuildRuns(unittest.TestCase):
    def test_groups_newest_first_with_nine_ordered_steps(self) -> None:
        runs = runs_for(make_run("prod", R2) + make_run("prod", R1))
        self.assertEqual([r["run_id"] for r in runs], [R1, R2])
        names = [s["name"] for s in runs[0]["steps"]]
        self.assertEqual(len(names), 9)
        self.assertEqual(names[0], "read_callrail_account")
        self.assertEqual(names[-1], "save_call_statistics")

    def test_complete_run(self) -> None:
        run = runs_for(make_run("prod", R1))[0]
        self.assertEqual(run["status"], "complete")
        self.assertIsNone(run["first_missing_step"])
        self.assertEqual(run["missing_count"], 0)
        self.assertEqual(run["started_at"], "2026-10-15T02:00:00Z")
        self.assertEqual(run["ended_at"], "2026-10-15T02:01:12Z")
        self.assertEqual(run["duration_seconds"], 72)

    def test_incomplete_run_names_first_missing_step(self) -> None:
        run = runs_for(make_run("prod", R1, missing_from=7))[0]
        self.assertEqual(run["status"], "incomplete")
        self.assertEqual(run["first_missing_step"], "record_call_statistics")
        self.assertEqual(run["missing_count"], 2)
        self.assertEqual(
            run["steps"][7],
            {"name": "record_call_statistics", "state": "missing", "missing": True},
        )

    def test_loss_rule(self) -> None:
        run = runs_for(make_run("prod", R1, overrides={5: 0}))[0]
        self.assertEqual(run["loss_steps"], ["read_gads_clickview"])

    def test_null_output_and_no_input_are_not_loss(self) -> None:
        run = runs_for(make_run("prod", R1, overrides={0: 0, 2: 0}))[0]
        self.assertEqual(run["loss_steps"], [])  # inputs empty / downstream steps unaffected here

    def test_inputs_ordered_per_definition(self) -> None:
        run = runs_for(make_run("prod", R1))[0]
        merge = run["steps"][6]
        self.assertEqual([i["name"] for i in merge["inputs"]], ["calls", "campaigns", "clickview"])
        self.assertEqual(run["steps"][0]["inputs"], [])

    def test_duplicate_step_latest_wins(self) -> None:
        raw = make_run("prod", R1)
        key, value = raw[1]  # raw[0] is the flow
        newer = value.replace('"output": 10', '"output": 99').replace(
            "2026-10-15T02:00:08Z", "2026-10-15T05:00:00Z"
        )
        runs = runs_for(raw + [(key, newer)])
        # same step twice in one run: the later finished_at wins
        self.assertEqual(runs[0]["steps"][0]["output"], 99)

    def test_stale_and_age(self) -> None:
        fresh = runs_for(make_run("prod", R1))[0]
        self.assertFalse(fresh["stale"])
        old_now = NOW + timedelta(hours=30)
        old = runs_for(make_run("prod", R1), now=old_now)[0]
        self.assertTrue(old["stale"])
        # now = 2026-10-16T09:00:00Z, run ended 2026-10-15T02:01:12Z
        self.assertEqual(old["age_seconds"], 30 * 3600 + 58 * 60 + 48)

    def test_stale_threshold_configurable(self) -> None:
        later = NOW + timedelta(hours=2)
        self.assertFalse(runs_for(make_run("prod", R1), now=later, stale_hours=26)[0]["stale"])
        self.assertTrue(runs_for(make_run("prod", R1), now=later, stale_hours=1)[0]["stale"])

    def test_unreadable_counted_and_step_missing(self) -> None:
        run = runs_for(make_run("prod", R1, corrupt=(3,)))[0]
        self.assertEqual(run["unreadable"], 1)
        self.assertEqual(run["status"], "incomplete")
        self.assertEqual(run["first_missing_step"], "read_instances")

    def test_run_with_only_unreadable_records_still_listed(self) -> None:
        runs = runs_for(make_run("prod", R1, corrupt=tuple(range(9))))
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["missing_count"], 9)
        self.assertEqual(runs[0]["unreadable"], 9)


START4 = datetime(2026, 10, 15, 2, 0, 33, tzinfo=timezone.utc)  # step 4 began 33 s into the run


def _states(run: Dict[str, Any]) -> List[str]:
    return [s["state"] for s in run["steps"]]


class TestLiveStates(unittest.TestCase):
    def _running(self, now: datetime = NOW) -> Dict[str, Any]:
        raw = make_run("prod", R1, missing_from=3)  # steps 1-3 finished
        marker = make_marker("prod", R1, 3, START4)
        return runs_for(raw, now=now, markers=[marker])[0]

    def test_running_step_then_waiting_steps(self) -> None:
        run = self._running(START4 + timedelta(seconds=42))
        self.assertEqual(
            _states(run),
            ["done"] * 3 + ["running"] + ["waiting"] * 5,
        )
        step = run["steps"][3]
        self.assertEqual(step["elapsed_seconds"], 42)
        self.assertEqual(step["started_at"], "2026-10-15T02:00:33Z")
        self.assertNotIn("missing", step)
        self.assertNotIn("inputs", step)
        self.assertEqual(run["status"], "running")
        self.assertEqual(run["running_step"], "read_instances")
        self.assertIsNone(run["first_missing_step"])
        self.assertEqual(run["missing_count"], 0)

    def test_running_run_is_never_stale(self) -> None:
        run = self._running(START4 + timedelta(seconds=100))
        self.assertFalse(run["stale"])
        far = runs_for(
            make_run("prod", R1, missing_from=3),
            now=NOW + timedelta(days=3),
            markers=[make_marker("prod", R1, 3, NOW + timedelta(days=3))],
        )[0]
        self.assertTrue(far["status"] == "running" and not far["stale"])

    def test_finish_record_beats_marker(self) -> None:
        raw = make_run("prod", R1, missing_from=5)  # steps 1-5 finished
        run = runs_for(raw, markers=[make_marker("prod", R1, 3, START4)])[0]
        self.assertEqual(run["steps"][3]["state"], "done")
        self.assertNotEqual(run["status"], "running")

    def test_skipped_earlier_step_stays_missing(self) -> None:
        raw = [r for r in make_run("prod", R1, missing_from=3) if ":step:02-" not in r[0]]
        run = runs_for(
            raw, now=START4 + timedelta(seconds=5), markers=[make_marker("prod", R1, 3, START4)]
        )[0]
        self.assertEqual(run["steps"][1]["state"], "missing")
        self.assertTrue(run["steps"][1]["missing"])
        self.assertEqual(run["steps"][3]["state"], "running")
        self.assertEqual(run["steps"][4]["state"], "waiting")
        self.assertEqual(run["first_missing_step"], "read_callrail_call")

    def test_marker_only_run_exists_with_step_one_running(self) -> None:
        run = runs_for(
            [make_flow("prod", R1)],
            now=START4 + timedelta(seconds=5),
            markers=[make_marker("prod", R1, 0, START4)],
        )[0]
        self.assertEqual(_states(run), ["running"] + ["waiting"] * 8)
        self.assertEqual(run["status"], "running")

    def test_only_the_run_with_the_marker_has_a_running_step(self) -> None:
        raw = make_run("prod", R2, missing_from=3) + make_run("prod", R1, missing_from=3)
        runs = runs_for(
            raw, now=START4 + timedelta(seconds=5), markers=[make_marker("prod", R1, 3, START4)]
        )
        self.assertEqual([r["status"] for r in runs], ["running", "incomplete"])
        self.assertNotIn("waiting", _states(runs[1]))

    def test_elapsed_is_never_negative(self) -> None:
        run = self._running(START4 - timedelta(seconds=30))
        self.assertEqual(run["steps"][3]["elapsed_seconds"], 0)

    def test_complete_run_unchanged_apart_from_new_keys(self) -> None:
        run = runs_for(make_run("prod", R1))[0]
        self.assertEqual(_states(run), ["done"] * 9)
        self.assertEqual((run["status"], run["running_step"]), ("complete", None))

    def test_stalled_boundary(self) -> None:
        at_limit = self._running(START4 + timedelta(seconds=900))
        self.assertEqual(at_limit["steps"][3]["state"], "running")
        over = self._running(START4 + timedelta(seconds=901))
        self.assertEqual(over["steps"][3]["state"], "stalled")

    def test_stalled_step_is_the_stop_point(self) -> None:
        run = self._running(START4 + timedelta(seconds=1020))
        self.assertEqual(_states(run), ["done"] * 3 + ["stalled"] + ["missing"] * 5)
        self.assertEqual(run["status"], "incomplete")
        self.assertIsNone(run["running_step"])
        self.assertEqual(run["first_missing_step"], "read_instances")
        self.assertEqual(run["missing_count"], 6)
        self.assertEqual(run["steps"][3]["elapsed_seconds"], 1020)

    def test_late_finish_record_turns_stalled_step_done(self) -> None:
        raw = make_run("prod", R1, missing_from=4)
        run = runs_for(
            raw,
            now=START4 + timedelta(seconds=2000),
            markers=[make_marker("prod", R1, 3, START4)],
        )[0]
        self.assertEqual(run["steps"][3]["state"], "done")

    def test_stall_limit_is_configurable(self) -> None:
        raw = make_run("prod", R1, missing_from=3)
        run = runs_for(
            raw,
            now=START4 + timedelta(seconds=31),
            markers=[make_marker("prod", R1, 3, START4)],
            stall_seconds=30,
        )[0]
        self.assertEqual(run["steps"][3]["state"], "stalled")


def _flow_raw(run_id: str, steps: List[Dict[str, Any]], pipeline: str = "demo", v: int = 1) -> Any:
    return (
        f"waypoint:{pipeline}:prod:{run_id}:flow",
        flow_value(pipeline, "prod", run_id, steps, v=v),
    )


def _record(
    run_id: str,
    index: int,
    step: str,
    output: Any,
    inputs: Optional[Dict[str, int]] = None,
    pipeline: str = "demo",
) -> Any:
    import json

    rec = {
        "pipeline": pipeline,
        "run_id": run_id,
        "env": "prod",
        "step": step,
        "index": index,
        "inputs": inputs or {},
        "output": output,
        "finished_at": f"2026-10-15T02:00:{index * 5:02d}Z",
    }
    return f"waypoint:{pipeline}:prod:{run_id}:step:{index:02d}-{step}", json.dumps(rec)


def _demo(
    raw: List[Any], now: datetime = NOW, markers: Optional[List[Any]] = None
) -> Dict[str, Any]:
    flows, records, raw_markers = split(raw)
    return build_runs(
        parse_records("prod", "demo", records),
        "prod",
        "demo",
        now,
        26.0,
        flows=parse_flows("prod", "demo", flows),
        markers=parse_markers("prod", "demo", (markers or []) + raw_markers),
    )[0]


DEMO_STEPS: List[Dict[str, Any]] = [
    {"name": "a", "label": "Alpha", "inputs": []},
    {"name": "b", "inputs": [{"name": "rows", "from": "a"}]},
    {"name": "c", "inputs": [{"name": "rows", "from": "b"}], "returns_nothing": True},
]


class TestFlowDrivenRuns(unittest.TestCase):
    """The step list comes from the run's own flow, never from a built-in list (US1)."""

    def test_unknown_pipeline_steps_are_drawn_from_the_flow(self) -> None:
        run = _demo(
            [
                _flow_raw(R1, DEMO_STEPS),
                _record(R1, 1, "a", 5),
                _record(R1, 2, "b", 4, {"rows": 5}),
                _record(R1, 3, "c", None, {"rows": 4}),
            ]
        )
        self.assertEqual([s["name"] for s in run["steps"]], ["a", "b", "c"])
        self.assertEqual(_states(run), ["done"] * 3)
        self.assertEqual(run["pipeline"], "demo")
        self.assertEqual(run["flow_status"], "ok")
        self.assertEqual(run["flow"]["steps"][0]["label"], "Alpha")
        self.assertEqual(run["flow"]["steps"][1]["inputs"], [{"name": "rows", "from": "a"}])
        self.assertEqual(run["status"], "complete")

    def test_each_run_uses_its_own_flow(self) -> None:
        longer = DEMO_STEPS + [{"name": "d", "inputs": [{"name": "rows", "from": "c"}]}]
        raw = [_flow_raw(R2, DEMO_STEPS), _flow_raw(R1, longer)]
        flows, records, _ = split(raw)
        runs = build_runs(
            parse_records("prod", "demo", records),
            "prod",
            "demo",
            NOW,
            26.0,
            flows=parse_flows("prod", "demo", flows),
        )
        self.assertEqual([len(r["flow"]["steps"]) for r in runs], [4, 3])  # R1 first (newest)

    def test_renaming_a_step_in_the_flow_changes_the_run(self) -> None:
        renamed = [{**DEMO_STEPS[0], "name": "alpha"}] + DEMO_STEPS[1:]
        run = _demo([_flow_raw(R1, renamed)])
        self.assertEqual(run["steps"][0]["name"], "alpha")


class TestNotReached(unittest.TestCase):
    """US3: a planned step with no record still shows."""

    def test_six_planned_three_finished(self) -> None:
        steps = [
            {"name": f"s{i}", "inputs": ([{"name": "x", "from": f"s{i-1}"}] if i else [])}
            for i in range(6)
        ]
        raw = [_flow_raw(R1, steps)] + [_record(R1, i + 1, f"s{i}", 3) for i in range(3)]
        run = _demo(raw)
        self.assertEqual(_states(run), ["done"] * 3 + ["missing"] * 3)
        self.assertEqual(run["first_missing_step"], "s3")
        self.assertEqual(run["status"], "incomplete")

    def test_every_stopping_point_shows_the_whole_flow(self) -> None:
        for finished in range(0, 3):
            raw = [_flow_raw(R1, DEMO_STEPS)] + [
                _record(R1, i + 1, "abc"[i], 1) for i in range(finished)
            ]
            run = _demo(raw)
            self.assertEqual(len(run["steps"]), 3, finished)
            self.assertEqual(run["first_missing_step"], "abc"[finished], finished)

    def test_flow_only_run_just_started_is_waiting(self) -> None:
        run = _demo(
            [_flow_raw(R1, DEMO_STEPS)], now=datetime(2026, 10, 15, 2, 0, 20, tzinfo=timezone.utc)
        )
        self.assertEqual(_states(run), ["waiting"] * 3)
        self.assertEqual((run["status"], run["running_step"]), ("running", None))

    def test_flow_only_run_long_ago_is_missing(self) -> None:
        run = _demo([_flow_raw(R1, DEMO_STEPS)])
        self.assertEqual(_states(run), ["missing"] * 3)
        self.assertEqual(run["status"], "incomplete")

    def test_unplanned_step_is_shown_and_not_counted_missing(self) -> None:
        raw = (
            [_flow_raw(R1, DEMO_STEPS)]
            + [_record(R1, i + 1, "abc"[i], 1) for i in range(3)]
            + [_record(R1, 4, "surprise", 7)]
        )
        run = _demo(raw)
        self.assertEqual(_states(run), ["done"] * 3 + ["unplanned"])
        self.assertEqual(run["steps"][3]["output"], 7)
        self.assertEqual(run["missing_count"], 0)
        self.assertEqual(run["status"], "complete")
        self.assertNotIn("surprise", run["loss_steps"])

    def test_unplanned_running_step(self) -> None:
        marker = make_marker("prod", R1, 3, START4, pipeline="demo", step="surprise")
        raw = [_flow_raw(R1, DEMO_STEPS)] + [_record(R1, i + 1, "abc"[i], 1) for i in range(3)]
        run = _demo(raw, now=START4 + timedelta(seconds=5), markers=[marker])
        self.assertEqual(run["steps"][3]["state"], "running")
        self.assertEqual(run["running_step"], "surprise")


class TestMissingOrInvalidFlow(unittest.TestCase):
    """US4: no usable flow means a flat list of what reported, in order, and no flow."""

    def test_records_without_a_flow(self) -> None:
        run = _demo([_record(R1, 2, "b", 4), _record(R1, 1, "a", 5)])
        self.assertEqual(run["flow_status"], "missing")
        self.assertIsNone(run["flow"])
        self.assertEqual([s["name"] for s in run["steps"]], ["a", "b"])
        self.assertEqual(_states(run), ["done", "done"])
        self.assertEqual(run["missing_count"], 0)
        self.assertIsNone(run["first_missing_step"])

    def test_invalid_flow_falls_back_the_same_way(self) -> None:
        cases = (
            (_flow_raw(R1, DEMO_STEPS, v=9), "unsupported"),
            ((f"waypoint:demo:prod:{R1}:flow", "{nope"), "invalid"),
        )
        for bad, status in cases:
            with self.subTest(bad[1][:12]):
                run = _demo([bad, _record(R1, 1, "a", 5)])
                self.assertEqual(run["flow_status"], status)
                self.assertIsNone(run["flow"])
                self.assertEqual([s["name"] for s in run["steps"]], ["a"])

    def test_partly_valid_flow_is_drawn_with_problems(self) -> None:
        steps: List[Dict[str, Any]] = [
            {"name": "a", "inputs": []},
            {"name": "b", "inputs": [{"name": "x", "from": "zzz"}]},
        ]
        run = _demo([_flow_raw(R1, steps)])
        self.assertEqual(run["flow_status"], "ok")
        self.assertEqual(len(run["flow_problems"]), 1)
        self.assertEqual(
            run["flow"]["steps"][1]["inputs"], [{"name": "x", "from": "zzz", "dangling": True}]
        )

    def test_marker_only_run_without_flow(self) -> None:
        marker = make_marker("prod", R1, 0, START4, pipeline="demo", step="a")
        run = _demo([], now=START4 + timedelta(seconds=5), markers=[marker])
        self.assertEqual(_states(run), ["running"])
        self.assertIsNone(run["flow"])


if __name__ == "__main__":
    unittest.main()


BEAT = START4 + timedelta(seconds=60)  # the run's last heartbeat: 02:01:33
DEAD = BEAT + timedelta(seconds=91)  # just past the 90 s death-detection time


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestDiedRuns(unittest.TestCase):
    """specs/009-run-liveness-heartbeat: a stale heartbeat on unfinished work means the run died."""

    def _open_step_run(self, now: datetime = DEAD) -> Dict[str, Any]:
        raw = make_run("prod", R1, missing_from=3)  # steps 1-3 finished, step 4 began at START4
        marker = make_marker("prod", R1, 3, START4)
        return runs_for(raw, now=now, markers=[marker], beats={R1: BEAT})[0]

    def test_stale_beat_with_open_step_is_died(self) -> None:
        run = self._open_step_run()
        self.assertEqual(_states(run), ["done"] * 3 + ["died"] + ["missing"] * 5)
        self.assertEqual(
            run["died"],
            {
                "judged_at": _iso(DEAD),
                "last_seen_at": _iso(BEAT),
                "recorded": False,
            },
        )
        step = run["steps"][3]
        self.assertEqual((step["started_at"], step["last_seen_at"]), (_iso(START4), _iso(BEAT)))
        self.assertNotIn("elapsed_seconds", step)

    def test_died_run_is_incomplete_not_running(self) -> None:
        run = self._open_step_run()
        self.assertEqual(run["status"], "incomplete")
        self.assertIsNone(run["running_step"])
        self.assertEqual(run["first_missing_step"], "read_instances")
        self.assertEqual(run["missing_count"], 6)

    def test_later_steps_are_not_reached_never_waiting(self) -> None:
        run = self._open_step_run()
        self.assertNotIn("waiting", _states(run))
        self.assertTrue(all(s.get("missing") for s in run["steps"][4:]))

    def test_threshold_is_exclusive_and_follows_the_setting(self) -> None:
        at_limit = self._open_step_run(BEAT + timedelta(seconds=90))
        self.assertIsNone(at_limit["died"])
        self.assertEqual(at_limit["steps"][3]["state"], "running")
        raw = make_run("prod", R1, missing_from=3)
        run = runs_for(
            raw,
            now=BEAT + timedelta(seconds=31),
            markers=[make_marker("prod", R1, 3, START4)],
            beats={R1: BEAT},
            dead_seconds=30,
        )[0]
        self.assertIsNotNone(run["died"])

    def test_died_between_steps_has_no_open_step(self) -> None:
        raw = make_run("prod", R1, missing_from=3)
        run = runs_for(raw, now=DEAD, beats={R1: BEAT})[0]
        self.assertEqual(_states(run), ["done"] * 3 + ["missing"] * 6)
        self.assertEqual(run["status"], "incomplete")
        self.assertEqual(run["died"]["last_seen_at"], _iso(BEAT))

    def test_died_right_after_start_is_not_just_started(self) -> None:
        start = datetime(2026, 10, 15, 2, 0, 0, tzinfo=timezone.utc)
        run = runs_for(
            [make_flow("prod", R1)], now=start + timedelta(seconds=200), beats={R1: start}
        )[0]
        self.assertEqual(_states(run), ["missing"] * 9)
        self.assertEqual(run["status"], "incomplete")
        self.assertIsNotNone(run["died"])

    def test_fresh_start_with_a_fresh_beat_is_still_just_started(self) -> None:
        start = datetime(2026, 10, 15, 2, 0, 0, tzinfo=timezone.utc)
        run = runs_for(
            [make_flow("prod", R1)], now=start + timedelta(seconds=20), beats={R1: start}
        )[0]
        self.assertEqual((run["status"], run["died"]), ("running", None))

    def test_finished_run_is_never_newly_judged_died(self) -> None:
        run = runs_for(make_run("prod", R1), now=NOW, beats={R1: BEAT})[0]
        self.assertEqual(run["status"], "complete")
        self.assertIsNone(run["died"])

    def test_unplanned_open_step_and_run_without_flow_also_die(self) -> None:
        marker = make_marker("prod", R1, 3, START4, pipeline="demo", step="surprise")
        raw = [_flow_raw(R1, DEMO_STEPS)] + [_record(R1, i + 1, "abc"[i], 1) for i in range(3)]
        flows, records, raw_markers = split(raw)
        run = build_runs(
            parse_records("prod", "demo", records),
            "prod",
            "demo",
            DEAD,
            26.0,
            flows=parse_flows("prod", "demo", flows),
            markers=parse_markers("prod", "demo", [marker]),
            alive=parse_alive("prod", "demo", [make_alive("prod", R1, BEAT, pipeline="demo")]),
        )[0]
        self.assertEqual(run["steps"][3]["state"], "died")
        bare = runs_for(
            make_run("prod", R1, missing_from=3, with_flow=False),
            now=DEAD,
            markers=[make_marker("prod", R1, 3, START4)],
            beats={R1: BEAT},
        )[0]
        self.assertEqual(bare["steps"][3]["state"], "died")
        self.assertIsNotNone(bare["died"])

    def test_a_heartbeat_alone_does_not_create_a_run(self) -> None:
        self.assertEqual(runs_for([], beats={R1: BEAT}), [])

    def test_stored_verdict_stays_died_with_a_fresh_beat(self) -> None:
        raw = make_run("prod", R1, missing_from=3)
        later = DEAD + timedelta(hours=1)
        run = runs_for(
            raw,
            now=later,
            markers=[make_marker("prod", R1, 3, START4)],
            beats={R1: later - timedelta(seconds=5)},  # signals resumed
            verdicts={R1: (DEAD, BEAT)},
        )[0]
        self.assertEqual(run["steps"][3]["state"], "died")
        self.assertEqual(
            run["died"], {"judged_at": _iso(DEAD), "last_seen_at": _iso(BEAT), "recorded": True}
        )
        self.assertEqual(run["status"], "incomplete")
        self.assertIsNone(run["running_step"])

    def test_stored_verdict_never_returns_to_complete(self) -> None:
        run = runs_for(make_run("prod", R1), now=NOW, verdicts={R1: (DEAD, BEAT)})[0]
        self.assertEqual(run["status"], "incomplete")
        self.assertTrue(run["died"]["recorded"])

    def test_verdict_of_another_run_does_not_leak(self) -> None:
        raw = make_run("prod", R2) + make_run("prod", R1)
        runs = runs_for(raw, verdicts={R2: (DEAD, BEAT)})
        self.assertEqual([r["died"] is not None for r in runs], [False, True])


class TestHungVersusDead(unittest.TestCase):
    """The same stuck step is Stalled while the process still beats and Died once it stops."""

    def _run(self, now: datetime, beat: datetime) -> Dict[str, Any]:
        raw = make_run("prod", R1, missing_from=3)
        marker = make_marker("prod", R1, 3, START4)
        return runs_for(raw, now=now, markers=[marker], beats={R1: beat})[0]

    def test_beating_run_within_the_stall_limit_is_running(self) -> None:
        now = START4 + timedelta(seconds=300)
        run = self._run(now, beat=now - timedelta(seconds=5))
        self.assertEqual((run["steps"][3]["state"], run["status"]), ("running", "running"))
        self.assertIsNone(run["died"])

    def test_beating_run_past_the_stall_limit_is_stalled_never_died(self) -> None:
        for minutes in (16, 60, 24 * 60):
            with self.subTest(minutes=minutes):
                now = START4 + timedelta(minutes=minutes)
                run = self._run(now, beat=now - timedelta(seconds=5))
                self.assertEqual(run["steps"][3]["state"], "stalled")
                self.assertIsNone(run["died"])
                self.assertEqual(run["status"], "incomplete")

    def test_the_same_run_turns_died_when_the_beat_stops(self) -> None:
        now = START4 + timedelta(minutes=30)
        self.assertEqual(
            self._run(now, beat=now - timedelta(seconds=60))["steps"][3]["state"], "stalled"
        )
        died = self._run(now, beat=now - timedelta(seconds=91))
        self.assertEqual(died["steps"][3]["state"], "died")
        self.assertIsNotNone(died["died"])

    def test_a_slow_step_with_a_beat_is_never_died(self) -> None:
        now = START4 + timedelta(seconds=800)  # a long step, still inside the stall limit
        run = self._run(now, beat=now - timedelta(seconds=89))
        self.assertEqual(run["steps"][3]["state"], "running")

    def test_progressing_run_keeps_running_as_records_arrive(self) -> None:
        raw = make_run("prod", R1, missing_from=5)  # five steps recorded
        now = datetime(2026, 10, 15, 2, 1, 0, tzinfo=timezone.utc)
        marker = make_marker("prod", R1, 5, now - timedelta(seconds=3))
        run = runs_for(raw, now=now, markers=[marker], beats={R1: now - timedelta(seconds=4)})[0]
        self.assertEqual(run["steps"][5]["state"], "running")
        self.assertEqual(run["running_step"], "read_gads_clickview")


class TestRunsWithoutAHeartbeat(unittest.TestCase):
    """A pipeline that sends no heartbeat is judged exactly as before (FR-010, SC-003)."""

    def test_no_heartbeat_never_died_however_old_the_marker(self) -> None:
        raw = make_run("prod", R1, missing_from=3)
        marker = make_marker("prod", R1, 3, START4)
        for seconds in (30, 899, 901, 86_400 * 3):
            with self.subTest(seconds=seconds):
                run = runs_for(raw, now=START4 + timedelta(seconds=seconds), markers=[marker])[0]
                self.assertIsNone(run["died"])
                self.assertNotIn("died", _states(run))
        stalled = runs_for(raw, now=START4 + timedelta(seconds=1020), markers=[marker])[0]
        self.assertEqual(_states(stalled), ["done"] * 3 + ["stalled"] + ["missing"] * 5)

    def test_flow_only_run_without_a_heartbeat_keeps_the_old_states(self) -> None:
        just_started = runs_for(
            [make_flow("prod", R1)], now=datetime(2026, 10, 15, 2, 0, 20, tzinfo=timezone.utc)
        )[0]
        self.assertEqual((_states(just_started), just_started["died"]), (["waiting"] * 9, None))
        long_ago = runs_for([make_flow("prod", R1)])[0]
        self.assertEqual((_states(long_ago), long_ago["died"]), (["missing"] * 9, None))

    def test_a_heartbeat_of_another_run_does_not_make_this_one_die(self) -> None:
        raw = make_run("prod", R1, missing_from=3)
        marker = make_marker("prod", R1, 3, START4)
        run = runs_for(raw, now=DEAD, markers=[marker], beats={R2: BEAT})[0]
        self.assertIsNone(run["died"])
        self.assertEqual(run["steps"][3]["state"], "running")

    def test_an_unreadable_heartbeat_counts_as_none(self) -> None:
        raw = make_run("prod", R1, missing_from=3)
        marker = make_marker("prod", R1, 3, START4)
        bad = {f"waypoint:{PIPELINE}:prod:{R1}:alive": "{not json"}
        raw_flows, raw_records, raw_markers = split(raw)
        run = build_runs(
            parse_records("prod", PIPELINE, raw_records),
            "prod",
            PIPELINE,
            DEAD,
            26.0,
            flows=parse_flows("prod", PIPELINE, raw_flows),
            markers=parse_markers("prod", PIPELINE, [marker]),
            alive=parse_alive("prod", PIPELINE, list(bad.items())),
        )[0]
        self.assertIsNone(run["died"])

    def test_the_default_build_without_new_arguments_is_unchanged(self) -> None:
        raw_flows, raw_records, raw_markers = split(make_run("prod", R1))
        run = build_runs(
            parse_records("prod", PIPELINE, raw_records),
            "prod",
            PIPELINE,
            NOW,
            26.0,
            flows=parse_flows("prod", PIPELINE, raw_flows),
        )[0]
        self.assertEqual((run["status"], run["died"]), ("complete", None))


FAIL_AT = datetime(2026, 10, 15, 2, 0, 50, tzinfo=timezone.utc)  # step 4 raised 17 s after it began
LATER = FAIL_AT + timedelta(minutes=30)


def _without(raw: List[Tuple[str, str]], number: int) -> List[Tuple[str, str]]:
    return [r for r in raw if f":step:{number:02d}-" not in r[0]]


def _retried_record(raw: List[Tuple[str, str]], number: int, attempt: int) -> List[Tuple[str, str]]:
    """The finish record of step `number` as written by a later attempt `attempt`."""
    import json

    out = []
    for key, value in raw:
        if f":step:{number:02d}-" in key:
            data = json.loads(value)
            data["index"] = attempt
            key = key.replace(f":step:{number:02d}-", f":step:{attempt:02d}-")
            value = json.dumps(data)
        out.append((key, value))
    return out


class TestFailedSteps(unittest.TestCase):
    """specs/011-step-failure-errors/data-model.md: a failure with the highest attempt index wins."""

    def _failed_run(self, now: datetime = LATER, **kw: Any) -> Dict[str, Any]:
        raw = make_run("prod", R1, missing_from=3)  # steps 1-3 finished, step 4 raised
        kw.setdefault("markers", [make_marker("prod", R1, 3, START4)])
        kw.setdefault("failures", [make_failure("prod", R1, 3, FAIL_AT, started_at=START4)])
        return runs_for(raw, now=now, **kw)[0]

    def test_failure_beats_an_old_marker(self) -> None:
        run = (
            self._failed_run()
        )  # the marker is 30 minutes old: would be Stalled without the failure
        self.assertEqual(_states(run), ["done"] * 3 + ["failed"] + ["missing"] * 5)
        step = run["steps"][3]
        self.assertEqual(step["name"], "read_instances")
        self.assertEqual((step["started_at"], step["failed_at"]), (_iso(START4), _iso(FAIL_AT)))
        self.assertEqual(step["error"]["type"], "ValueError")
        self.assertEqual(step["error"]["message"], "boom")
        self.assertIn("ValueError: boom", step["error"]["traceback"])
        self.assertNotIn("elapsed_seconds", step)

    def test_failure_beats_a_fresh_marker_too(self) -> None:
        run = self._failed_run(now=FAIL_AT + timedelta(seconds=2))
        self.assertEqual(run["steps"][3]["state"], "failed")
        self.assertIsNone(run["running_step"])

    def test_stopping_failure_makes_the_run_failed(self) -> None:
        run = self._failed_run()
        self.assertEqual(
            run["failed"], {"step": "read_instances", "index": 4, "failed_at": _iso(FAIL_AT)}
        )
        self.assertEqual(run["status"], "incomplete")
        self.assertIsNone(run["running_step"])
        self.assertEqual(run["first_missing_step"], "read_instances")
        self.assertEqual(run["missing_count"], 6)
        self.assertEqual(run["ended_at"], _iso(FAIL_AT))
        self.assertIsNone(run["died"])

    def test_later_steps_are_not_reached_never_waiting(self) -> None:
        run = self._failed_run(now=FAIL_AT + timedelta(seconds=2))
        self.assertNotIn("waiting", _states(run))
        self.assertTrue(all(s.get("missing") for s in run["steps"][4:]))

    def test_failed_beats_died_even_with_a_stale_heartbeat(self) -> None:
        run = self._failed_run(beats={R1: BEAT})  # beat is 28 minutes old: would be Died
        self.assertIsNone(run["died"])
        self.assertEqual(run["steps"][3]["state"], "failed")
        self.assertIsNotNone(run["failed"])

    def test_stored_died_verdict_does_not_override_a_stopping_failure(self) -> None:
        run = self._failed_run(verdicts={R1: (DEAD, BEAT)})
        self.assertIsNone(run["died"])
        self.assertIsNotNone(run["failed"])

    def test_failure_item_without_a_marker_still_fails_the_step(self) -> None:
        run = self._failed_run(markers=[])
        self.assertEqual(run["steps"][3]["state"], "failed")
        self.assertIsNotNone(run["failed"])

    def test_a_failure_alone_creates_the_run(self) -> None:
        run = runs_for([], failures=[make_failure("prod", R1, 0, FAIL_AT)])[0]
        self.assertEqual(run["run_id"], R1)
        self.assertEqual(run["steps"][0]["state"], "failed")
        self.assertEqual(run["failed"]["step"], "read_callrail_account")

    def test_flow_run_failing_in_its_first_step(self) -> None:
        run = runs_for([make_flow("prod", R1)], failures=[make_failure("prod", R1, 0, FAIL_AT)])[0]
        self.assertEqual(_states(run), ["failed"] + ["missing"] * 8)
        self.assertEqual(run["status"], "incomplete")

    def test_handled_error_marks_the_step_but_not_the_run(self) -> None:
        # step 4 raised and was caught; steps 5-9 still ran (their attempt indexes are higher)
        raw = _without(make_run("prod", R1), 4)
        run = runs_for(
            raw,
            now=NOW,
            markers=[make_marker("prod", R1, 3, START4)],
            failures=[make_failure("prod", R1, 3, FAIL_AT)],
        )[0]
        self.assertEqual(run["steps"][3]["state"], "failed")
        self.assertIsNone(run["failed"])
        self.assertIsNone(run["died"])
        self.assertEqual(run["status"], "incomplete")  # a failed planned step is never "complete"
        self.assertEqual((run["first_missing_step"], run["missing_count"]), ("read_instances", 1))

    def test_handled_error_in_a_run_still_running(self) -> None:
        raw = _without(make_run("prod", R1, missing_from=6), 4)  # steps 5-6 ran after the failure
        run = runs_for(
            raw,
            now=START4 + timedelta(seconds=60),
            markers=[make_marker("prod", R1, 6, START4 + timedelta(seconds=50))],
            failures=[make_failure("prod", R1, 3, FAIL_AT)],
        )[0]
        self.assertEqual(run["status"], "running")
        self.assertEqual(run["steps"][3]["state"], "failed")
        self.assertEqual(run["steps"][6]["state"], "running")
        self.assertIsNone(run["failed"])

    def test_successful_retry_replaces_the_failure(self) -> None:
        raw = _retried_record(make_run("prod", R1), 4, 20)
        run = runs_for(raw, now=NOW, failures=[make_failure("prod", R1, 3, FAIL_AT)])[0]
        self.assertEqual(run["steps"][3]["state"], "done")
        self.assertIsNone(run["failed"])
        self.assertEqual(run["status"], "complete")

    def test_retry_in_progress_is_running_not_failed(self) -> None:
        retry = make_marker("prod", R1, 9, FAIL_AT + timedelta(seconds=2), step="read_instances")
        run = self._failed_run(
            now=FAIL_AT + timedelta(seconds=10),
            markers=[make_marker("prod", R1, 3, START4), retry],
        )
        self.assertEqual(run["steps"][3]["state"], "running")
        self.assertEqual(run["status"], "running")
        self.assertIsNone(run["failed"])

    def test_retry_that_fails_again_shows_the_latest_failure(self) -> None:
        second = FAIL_AT + timedelta(minutes=1)
        run = self._failed_run(
            failures=[
                make_failure("prod", R1, 3, FAIL_AT),
                make_failure(
                    "prod",
                    R1,
                    3,
                    second,
                    index=10,
                    error={"type": "KeyError", "traceback": "KeyError\n"},
                ),
            ]
        )
        step = run["steps"][3]
        self.assertEqual(step["failed_at"], _iso(second))
        self.assertEqual(step["error"], {"type": "KeyError", "traceback": "KeyError\n"})
        self.assertEqual(run["failed"]["index"], 10)

    def test_failure_of_a_step_outside_the_flow_is_shown(self) -> None:
        run = self._failed_run(
            markers=[], failures=[make_failure("prod", R1, 3, FAIL_AT, step="mystery")]
        )
        by_name = {s["name"]: s for s in run["steps"]}
        self.assertEqual(by_name["mystery"]["state"], "failed")
        self.assertEqual(run["failed"]["step"], "mystery")
        self.assertEqual(run["missing_count"], 6)  # planned steps 4-9 were never reached

    def test_run_without_a_flow_lists_the_failed_step_in_order(self) -> None:
        raw = make_run("prod", R1, missing_from=3, with_flow=False)
        run = runs_for(raw, now=LATER, failures=[make_failure("prod", R1, 3, FAIL_AT)])[0]
        self.assertEqual(_states(run), ["done"] * 3 + ["failed"])
        self.assertEqual([s["name"] for s in run["steps"]][-1], "read_instances")
        self.assertEqual(run["steps"][-1]["state"], "failed")
        self.assertEqual(run["failed"]["step"], "read_instances")

    def test_failed_run_age_counts_from_the_failure(self) -> None:
        run = self._failed_run(now=FAIL_AT + timedelta(hours=27))
        self.assertEqual(run["age_seconds"], 27 * 3600)
        self.assertTrue(run["stale"])
        young = self._failed_run(now=FAIL_AT + timedelta(hours=1))
        self.assertFalse(young["stale"])


class TestRunsWithoutFailureItems(unittest.TestCase):
    """specs/011 FR-015: a run with no failure item is exactly what it was; `failed` is the only new key."""

    def test_every_older_state_has_no_failed_and_unchanged_status(self) -> None:
        start4 = [make_marker("prod", R1, 3, START4)]
        cases = {
            "complete": (runs_for(make_run("prod", R1)), "complete"),
            "running": (
                runs_for(make_run("prod", R1, missing_from=3), now=START4, markers=start4),
                "running",
            ),
            "stalled": (
                runs_for(make_run("prod", R1, missing_from=3), now=LATER, markers=start4),
                "incomplete",
            ),
            "died": (
                runs_for(
                    make_run("prod", R1, missing_from=3), now=DEAD, markers=start4, beats={R1: BEAT}
                ),
                "incomplete",
            ),
            "incomplete": (runs_for(make_run("prod", R1, missing_from=5)), "incomplete"),
            "no flow": (runs_for(make_run("prod", R1, with_flow=False)), "complete"),
        }
        for label, (runs, status) in cases.items():
            with self.subTest(label):
                (run,) = runs
                self.assertEqual(run["status"], status)
                self.assertIsNone(run["failed"])
                self.assertNotIn("failed", [s["state"] for s in run["steps"]])
                self.assertTrue(all("error" not in s for s in run["steps"]))
