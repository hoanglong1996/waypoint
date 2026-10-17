import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.domain.models import RunEvent
from app.domain.timeline import derive_events, dropped, merge, public, recorded_entries, select
from tests.fakes import make_failure, make_marker, make_run
from tests.test_analysis import NOW, R1, runs_for

STALL = 900.0


def kinds(entries: List[Dict[str, Any]]) -> List[str]:
    return [e["kind"] for e in entries]


def event(
    n: int,
    ts: str = "2026-10-15T02:00:20.250Z",
    level: str = "info",
    step: Optional[str] = None,
    message: Optional[str] = "hello",
    fields: Optional[Dict[str, Any]] = None,
) -> RunEvent:
    return RunEvent(
        R1,
        level,
        n,
        datetime.fromisoformat(ts.replace("Z", "+00:00")),
        step,
        message,
        fields,
    )


def complete_run() -> Dict[str, Any]:
    return runs_for(make_run("prod", R1, step_seconds=[10] * 9))[0]


class TestDeriveEvents(unittest.TestCase):
    """Specs 012 data-model.md "Timeline entry" (derived kinds) and research R3, R4."""

    def test_a_complete_run_has_start_finish_and_per_step_events(self) -> None:
        entries = derive_events(complete_run(), STALL)
        self.assertEqual(entries[0]["kind"], "run_started")
        self.assertEqual(entries[0]["ts"], "2026-10-15T02:00:00.000Z")
        self.assertEqual(entries[0]["message"], "Run started")
        self.assertEqual(kinds(entries).count("step_started"), 9)
        self.assertEqual(kinds(entries).count("step_finished"), 9)
        last = entries[-1]
        self.assertEqual((last["kind"], last["level"]), ("run_finished", "info"))
        self.assertEqual(last["ts"], "2026-10-15T02:01:30.999Z")  # end of the second
        self.assertEqual(last["fields"], {"duration_seconds": 90})
        self.assertTrue(all(e["source"] == "monitor" for e in entries))

    def test_step_events_have_the_documented_times_and_fields(self) -> None:
        entries = derive_events(complete_run(), STALL)
        first_started = next(e for e in entries if e["kind"] == "step_started")
        first_finished = next(e for e in entries if e["kind"] == "step_finished")
        self.assertEqual(first_started["ts"], "2026-10-15T02:00:00.000Z")
        self.assertEqual(first_finished["ts"], "2026-10-15T02:00:10.999Z")
        self.assertEqual(first_finished["step"], "read_callrail_account")
        self.assertEqual(first_finished["fields"], {"output": 10, "duration_seconds": 10})

    def test_a_failed_step_is_an_error_event_without_the_traceback(self) -> None:
        raw = make_run("prod", R1, missing_from=2)
        start = datetime(2026, 10, 15, 2, 0, 16, tzinfo=timezone.utc)
        failure = make_failure("prod", R1, 2, start + timedelta(seconds=31), started_at=start)
        run = runs_for(raw, failures=[failure])[0]
        entries = derive_events(run, STALL)
        failed = next(e for e in entries if e["kind"] == "step_failed")
        self.assertEqual((failed["level"], failed["step"]), ("error", "read_partners"))
        self.assertEqual(failed["message"], "Step read_partners failed: ValueError: boom")
        self.assertEqual(failed["fields"], {"error_type": "ValueError"})
        self.assertEqual(failed["ts"], "2026-10-15T02:00:47.999Z")
        self.assertNotIn("traceback", repr(failed).lower())
        stopped = next(e for e in entries if e["kind"] == "run_stopped")
        self.assertEqual(
            (stopped["level"], stopped["message"]), ("error", "Run stopped at step read_partners")
        )
        self.assertNotIn("run_finished", kinds(entries))

    def test_a_failure_without_a_stored_message(self) -> None:
        raw = make_run("prod", R1, missing_from=2)
        start = datetime(2026, 10, 15, 2, 0, 16, tzinfo=timezone.utc)
        failure = make_failure(
            "prod",
            R1,
            2,
            start + timedelta(seconds=3),
            started_at=start,
            error={"type": "KeyError", "traceback": "x"},
        )
        entries = derive_events(runs_for(raw, failures=[failure])[0], STALL)
        failed = next(e for e in entries if e["kind"] == "step_failed")
        self.assertEqual(failed["message"], "Step read_partners failed: KeyError")

    def test_a_stalled_step_is_a_warning_at_start_plus_the_stall_time(self) -> None:
        raw = make_run("prod", R1, missing_from=2)
        began = NOW - timedelta(seconds=2000)
        run = runs_for(raw, markers=[make_marker("prod", R1, 2, began)])[0]
        entries = derive_events(run, STALL)
        stalled = next(e for e in entries if e["kind"] == "step_stalled")
        self.assertEqual(stalled["level"], "warning")
        self.assertEqual(
            stalled["ts"], (began + timedelta(seconds=STALL)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        )
        self.assertIn("read_partners", stalled["message"])

    def test_a_died_run_has_an_error_event_at_the_judgement(self) -> None:
        raw = make_run("prod", R1, missing_from=2)
        beat = NOW - timedelta(seconds=300)
        run = runs_for(
            raw,
            markers=[make_marker("prod", R1, 2, NOW - timedelta(seconds=400))],
            beats={R1: beat},
        )[0]
        entries = derive_events(run, STALL)
        died = next(e for e in entries if e["kind"] == "run_died")
        self.assertEqual((died["level"], died["source"]), ("error", "monitor"))
        self.assertTrue(died["message"].startswith("Run died"))
        self.assertEqual(died["ts"], NOW.strftime("%Y-%m-%dT%H:%M:%S.999Z"))

    def test_a_running_run_has_no_end_event(self) -> None:
        raw = make_run("prod", R1, missing_from=2)
        run = runs_for(raw, markers=[make_marker("prod", R1, 2, NOW - timedelta(seconds=30))])[0]
        entries = derive_events(run, STALL)
        self.assertEqual(kinds(entries).count("step_started"), 3)
        self.assertNotIn("run_finished", kinds(entries))
        self.assertNotIn("run_stopped", kinds(entries))

    def test_a_run_without_a_flow_still_gets_its_events_in_index_order(self) -> None:
        raw = make_run("prod", R1, with_flow=False, step_seconds=[5] * 9)
        entries = merge(derive_events(runs_for(raw)[0], STALL), [])
        started = [e["step"] for e in entries if e["kind"] == "step_started"]
        self.assertEqual(started[0], "read_callrail_account")
        self.assertEqual(len(started), 9)

    def test_an_old_library_run_gets_the_same_kinds(self) -> None:
        raw = make_run("prod", R1, step_seconds=[10] * 9, exact=False)
        self.assertEqual(
            sorted(set(kinds(derive_events(runs_for(raw)[0], STALL)))),
            ["run_finished", "run_started", "step_finished", "step_started"],
        )

    def test_a_step_outside_the_flow_keeps_its_events(self) -> None:
        raw = make_run("prod", R1, step_seconds=[10] * 9)
        extra = make_marker("prod", R1, 9, NOW - timedelta(seconds=20), step="surprise")
        run = runs_for(raw, markers=[extra])[0]
        entries = derive_events(run, STALL)
        self.assertIn("surprise", [e["step"] for e in entries])

    def test_ids_are_unique_within_a_run(self) -> None:
        entries = derive_events(complete_run(), STALL)
        ids = [e["id"] for e in entries]
        self.assertEqual(len(ids), len(set(ids)))


class TestSequentialSteps(unittest.TestCase):
    def test_a_step_starting_in_the_second_the_previous_one_finished_is_listed_after_it(
        self,
    ) -> None:
        # steps of 0.4 s each leave the records with equal whole seconds: the order must still be logical
        run = runs_for(make_run("prod", R1, step_seconds=[0.4] * 9))[0]
        listed = [(e["kind"], e["step"]) for e in merge(derive_events(run, STALL), []) if e["step"]]
        order = [name for kind, name in listed if kind == "step_started"]
        for earlier, later in zip(order, order[1:], strict=False):
            self.assertLess(
                listed.index(("step_finished", earlier)), listed.index(("step_started", later))
            )
        for kind_name in order:
            self.assertLess(
                listed.index(("step_started", kind_name)),
                listed.index(("step_finished", kind_name)),
            )

    def test_normal_steps_keep_the_documented_times(self) -> None:
        entries = derive_events(complete_run(), STALL)
        second = next(e for e in entries if e["id"] == "d:step_started:read_callrail_call:1")
        self.assertEqual(
            second["ts"], "2026-10-15T02:00:10.999Z"
        )  # the previous step ended in that second
        third = next(e for e in entries if e["id"] == "d:step_started:read_partners:2")
        self.assertEqual(third["ts"], "2026-10-15T02:00:20.999Z")


class TestMerge(unittest.TestCase):
    def test_recorded_events_sort_between_their_steps_start_and_end(self) -> None:
        # step 1 ran 02:00:00 to 02:00:10; an event sent 0.6 s into its last second
        merged = merge(
            derive_events(complete_run(), STALL),
            recorded_entries([event(1, "2026-10-15T02:00:10.600Z", step="read_callrail_account")]),
        )
        order = [(e["kind"], e["step"]) for e in merged[:4]]
        self.assertEqual(order[0], ("run_started", None))
        self.assertLess(
            [e["id"] for e in merged].index("r:info:1"),
            [e["id"] for e in merged].index("d:step_finished:read_callrail_account:0"),
        )

    def test_derived_before_recorded_at_the_same_instant(self) -> None:
        merged = merge(
            derive_events(complete_run(), STALL),
            recorded_entries([event(1, "2026-10-15T02:00:00.000Z")]),
        )
        self.assertEqual(merged[0]["kind"], "run_started")
        self.assertEqual(merged[1]["id"], "d:step_started:read_callrail_account:0")
        self.assertEqual(merged[2]["id"], "r:info:1")

    def test_equal_timestamps_keep_the_senders_order(self) -> None:
        same = "2026-10-15T02:00:05.500Z"
        merged = merge([], recorded_entries([event(3, same), event(1, same), event(2, same)]))
        self.assertEqual([e["id"] for e in merged], ["r:info:1", "r:info:2", "r:info:3"])

    def test_derived_events_keep_their_derivation_order(self) -> None:
        derived = derive_events(complete_run(), STALL)
        merged = merge(derived, [])
        same_time = [e for e in merged if e["ts"] == "2026-10-15T02:00:10.999Z"]
        self.assertEqual([e["kind"] for e in same_time], ["step_finished", "step_started"])
        self.assertEqual(
            [e["id"] for e in merged if e["kind"] == "step_started"][:2],
            ["d:step_started:read_callrail_account:0", "d:step_started:read_callrail_call:1"],
        )


class TestSelect(unittest.TestCase):
    def setUp(self) -> None:
        recorded = [
            event(1, "2026-10-15T02:00:02.000Z", "info", "load"),
            event(2, "2026-10-15T02:00:03.000Z", "warning", "load"),
            event(3, "2026-10-15T02:00:04.000Z", "error", "extract"),
            event(4, "2026-10-15T02:00:05.000Z", "warning", None),
        ]
        self.entries = merge(derive_events(complete_run(), STALL), recorded_entries(recorded))

    def test_level_filter_takes_one_or_several(self) -> None:
        page, matched = select(self.entries, ["error"], None, 0, 100)
        self.assertEqual({e["level"] for e in page}, {"error"})
        self.assertEqual(matched, len(page))
        page, _ = select(self.entries, ["warning", "error"], None, 0, 100)
        self.assertEqual({e["level"] for e in page}, {"warning", "error"})

    def test_step_filter_is_an_exact_match(self) -> None:
        page, matched = select(self.entries, None, "load", 0, 100)
        self.assertEqual([e["id"] for e in page], ["r:info:1", "r:warning:2"])
        self.assertEqual(matched, 2)
        self.assertEqual(select(self.entries, None, "loa", 0, 100), ([], 0))

    def test_paging(self) -> None:
        total = len(self.entries)
        first, matched = select(self.entries, None, None, 0, 10)
        self.assertEqual((len(first), matched), (10, total))
        second, _ = select(self.entries, None, None, 10, 10)
        self.assertEqual(first + second, self.entries[:20])
        tail, _ = select(self.entries, None, None, total - 3, 10)
        self.assertEqual(len(tail), 3)
        self.assertEqual(select(self.entries, None, None, total + 5, 10)[0], [])

    def test_level_and_step_combine(self) -> None:
        page, matched = select(self.entries, ["warning"], "load", 0, 100)
        self.assertEqual([e["id"] for e in page], ["r:warning:2"])
        self.assertEqual(matched, 1)


class TestDropped(unittest.TestCase):
    def test_gap_between_the_highest_number_and_what_is_stored(self) -> None:
        self.assertEqual(dropped([event(1), event(2), event(5)]), 2)
        self.assertEqual(dropped([event(1), event(2), event(3)]), 0)

    def test_nothing_recorded_means_nothing_dropped(self) -> None:
        self.assertEqual(dropped([]), 0)

    def test_never_negative_when_numbers_restart_in_another_process(self) -> None:
        self.assertEqual(dropped([event(1), event(1), event(2)]), 0)


class TestPublic(unittest.TestCase):
    def test_sort_helpers_are_not_returned(self) -> None:
        entry = merge(derive_events(complete_run(), STALL), [])[0]
        self.assertEqual(
            set(public(entry)),
            {"id", "ts", "level", "step", "message", "fields", "source", "kind"},
        )

    def test_recorded_entry_shape(self) -> None:
        (entry,) = recorded_entries(
            [event(7, "2026-10-15T02:00:20.250Z", "warning", "load", None, {"rows": 3})]
        )
        self.assertEqual(
            public(entry),
            {
                "id": "r:warning:7",
                "ts": "2026-10-15T02:00:20.250Z",
                "level": "warning",
                "step": "load",
                "message": None,
                "fields": {"rows": 3},
                "source": "pipeline",
                "kind": "custom",
            },
        )


if __name__ == "__main__":
    unittest.main()
