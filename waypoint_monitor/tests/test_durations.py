import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.domain.durations import (
    StepTiming,
    failed_timing,
    finished_timing,
    flag_slow,
    run_duration,
    typical,
)
from app.domain.models import ErrorInfo, StartMarker, StepFailure, StepRecord

T0 = datetime(2026, 10, 17, 2, 0, 0, tzinfo=timezone.utc)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def record(
    finished: float,
    started: Optional[float] = None,
    duration_ms: Optional[int] = None,
    index: int = 1,
) -> StepRecord:
    return StepRecord(
        "p",
        "R",
        "prod",
        "s",
        index,
        {},
        1,
        at(finished),
        started_at=None if started is None else at(started),
        duration_ms=duration_ms,
    )


def marker(started: float, index: int = 1) -> StartMarker:
    return StartMarker("p", "R", "prod", "s", index, at(started))


class TestFinishedTiming(unittest.TestCase):
    """Specs 012 data-model.md "Step duration" and research R1."""

    def test_duration_ms_wins_over_everything(self) -> None:
        timing = finished_timing(
            record(100, started=10, duration_ms=2600), marker(50), previous_end=at(0)
        )
        self.assertEqual(timing, StepTiming(at(10), 3, False))

    def test_started_at_in_the_record(self) -> None:
        timing = finished_timing(record(100, started=40), marker(50), previous_end=at(0))
        self.assertEqual(timing, StepTiming(at(40), 60, False))

    def test_start_marker_of_the_same_attempt(self) -> None:
        timing = finished_timing(record(100), marker(70), previous_end=at(0))
        self.assertEqual(timing, StepTiming(at(70), 30, False))

    def test_marker_of_another_attempt_is_not_used(self) -> None:
        timing = finished_timing(record(100, index=2), marker(70, index=1), previous_end=at(30))
        self.assertEqual(timing, StepTiming(at(30), 70, True))

    def test_approximate_from_the_previous_step_end(self) -> None:
        timing = finished_timing(record(100), None, previous_end=at(40))
        self.assertEqual(timing, StepTiming(at(40), 60, True))

    def test_no_source_gives_unavailable(self) -> None:
        self.assertEqual(
            finished_timing(record(100), None, previous_end=None), StepTiming(None, None, False)
        )

    def test_negative_results_are_unavailable(self) -> None:
        self.assertEqual(finished_timing(record(100, started=130), None, None).seconds, None)
        self.assertEqual(finished_timing(record(100), None, previous_end=at(140)).seconds, None)
        self.assertEqual(finished_timing(record(100), marker(120), None).seconds, None)

    def test_zero_is_zero_not_unavailable(self) -> None:
        self.assertEqual(finished_timing(record(100, duration_ms=0), None, None).seconds, 0)
        self.assertEqual(finished_timing(record(100, duration_ms=400), None, None).seconds, 0)


class TestFailedTiming(unittest.TestCase):
    def test_start_to_failure(self) -> None:
        failure = StepFailure("p", "R", "prod", "s", 1, at(10), at(41), ErrorInfo("E", None, ""))
        self.assertEqual(failed_timing(failure), StepTiming(at(10), 31, False))

    def test_failure_before_start_is_unavailable(self) -> None:
        failure = StepFailure("p", "R", "prod", "s", 1, at(50), at(41), ErrorInfo("E", None, ""))
        self.assertIsNone(failed_timing(failure).seconds)


class TestRunDuration(unittest.TestCase):
    def test_finished_run_runs_to_its_last_activity(self) -> None:
        self.assertEqual(
            run_duration(at(0), at(655), at(9999), running=False, complete=True),
            {"seconds": 655, "running": False, "complete": True, "slow": False},
        )

    def test_running_run_counts_to_now(self) -> None:
        d = run_duration(at(0), at(100), at(400), running=True, complete=False)
        self.assertEqual((d["seconds"], d["running"], d["complete"]), (400, True, False))

    def test_incomplete_run_is_not_complete(self) -> None:
        d = run_duration(at(0), at(100), at(400), running=False, complete=False)
        self.assertEqual((d["seconds"], d["complete"]), (100, False))

    def test_never_negative(self) -> None:
        d = run_duration(at(100), at(50), at(60), running=False, complete=True)
        self.assertIsNone(d["seconds"])
        d = run_duration(at(100), at(100), at(60), running=True, complete=False)
        self.assertEqual(d["seconds"], None)



def run_of(
    seconds: Optional[int], status: str = "complete", running: bool = False
) -> Dict[str, Any]:
    return {
        "status": status,
        "duration": {
            "seconds": seconds,
            "running": running,
            "complete": status == "complete",
            "slow": False,
        },
    }


def completes(*seconds: int) -> List[Dict[str, Any]]:
    return [run_of(s) for s in seconds]


class TestTypical(unittest.TestCase):
    """Specs 012 data-model.md "Typical duration" and research R9."""

    def test_median_p95_and_threshold(self) -> None:
        runs = completes(*([600] * 5 + [610, 620, 630, 640, 650]))
        t = typical(runs, window=30, min_runs=5, multiple=2.0)
        assert t is not None
        self.assertEqual((t["median_seconds"], t["p95_seconds"], t["sample"]), (605, 650, 10))
        self.assertEqual((t["window"], t["multiple"], t["slow_after_seconds"]), (30, 2.0, 1210))

    def test_even_count_median_is_the_mean_of_the_middle_two(self) -> None:
        t = typical(completes(100, 200, 300, 400, 500, 700), 30, 5, 2.0)
        assert t is not None
        self.assertEqual(t["median_seconds"], 350)

    def test_p95_is_nearest_rank(self) -> None:
        # 20 values: ceil(0.95 * 20) = 19th smallest
        t = typical(completes(*range(1, 21)), 30, 5, 2.0)
        assert t is not None
        self.assertEqual(t["p95_seconds"], 19)
        t = typical(completes(*range(1, 6)), 30, 5, 2.0)
        assert t is not None
        self.assertEqual(t["p95_seconds"], 5)

    def test_none_below_the_minimum(self) -> None:
        self.assertIsNone(typical(completes(1, 2, 3, 4), 30, 5, 2.0))
        self.assertIsNotNone(typical(completes(1, 2, 3, 4, 5), 30, 5, 2.0))

    def test_only_finished_runs_count(self) -> None:
        runs = completes(600, 600, 600, 600, 600)
        runs += [
            run_of(5, "incomplete"),  # failed, died, stalled and incomplete runs are not typical
            run_of(99999, "running", running=True),
            run_of(None),  # unknown duration
        ]
        t = typical(runs, 30, 5, 2.0)
        assert t is not None
        self.assertEqual((t["median_seconds"], t["sample"]), (600, 5))

    def test_window_takes_the_newest_runs(self) -> None:
        newest_first = completes(100, 100, 100, 100, 100, 900, 900, 900)
        t = typical(newest_first, window=5, min_runs=5, multiple=2.0)
        assert t is not None
        self.assertEqual((t["median_seconds"], t["sample"]), (100, 5))


class TestFlagSlow(unittest.TestCase):
    def setUp(self) -> None:
        self.typ = typical(completes(*([600] * 6)), 30, 5, 2.0)

    def test_above_the_threshold_is_slow(self) -> None:
        runs = [run_of(2100), run_of(1201), run_of(1200), run_of(10)]
        flag_slow(runs, self.typ)
        self.assertEqual([r["duration"]["slow"] for r in runs], [True, True, False, False])

    def test_a_running_run_past_the_threshold_is_flagged_while_running(self) -> None:
        runs = [run_of(1500, "running", running=True), run_of(300, "running", running=True)]
        flag_slow(runs, self.typ)
        self.assertEqual([r["duration"]["slow"] for r in runs], [True, False])

    def test_failed_and_incomplete_runs_can_be_slow_too(self) -> None:
        runs = [run_of(5000, "incomplete")]
        flag_slow(runs, self.typ)
        self.assertTrue(runs[0]["duration"]["slow"])

    def test_nothing_is_flagged_without_typical_values(self) -> None:
        runs = [run_of(99999)]
        flag_slow(runs, None)
        self.assertFalse(runs[0]["duration"]["slow"])

    def test_unknown_duration_is_never_slow_and_status_is_untouched(self) -> None:
        runs = [run_of(None), run_of(5000)]
        flag_slow(runs, self.typ)
        self.assertEqual([r["status"] for r in runs], ["complete", "complete"])
        self.assertFalse(runs[0]["duration"]["slow"])


if __name__ == "__main__":
    unittest.main()
