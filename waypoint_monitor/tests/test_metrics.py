"""Flags, ordering and counts of a step's metrics (specs 013 FR-013 to FR-015)."""

import unittest
from datetime import datetime, timezone

from app.domain.metrics import count_over, metric_flag, step_metrics
from app.domain.models import MetricDecl, StepMetrics

WHEN = datetime(2026, 10, 15, 2, 5, 12, tzinfo=timezone.utc)


def record(values, index: int = 3, step: str = "load", at=WHEN) -> StepMetrics:  # type: ignore[no-untyped-def]
    return StepMetrics("demo", "20261015T020000Z", "prod", step, index, values, at)


class TestFlags(unittest.TestCase):
    def test_strict_comparisons(self) -> None:
        both = MetricDecl("m", warn_above=100, warn_below=10)
        self.assertEqual(metric_flag(101, both), "above")
        self.assertIsNone(metric_flag(100, both))
        self.assertEqual(metric_flag(9, both), "below")
        self.assertIsNone(metric_flag(10, both))
        self.assertIsNone(metric_flag(50, both))
        self.assertEqual(metric_flag(100.5, MetricDecl("m", warn_above=100)), "above")
        self.assertIsNone(metric_flag(5, MetricDecl("m", warn_above=100)))
        self.assertIsNone(metric_flag(5, MetricDecl("m")))

    def test_not_reported_and_undeclared_are_never_flagged(self) -> None:
        self.assertIsNone(metric_flag(None, MetricDecl("m", warn_above=1)))
        self.assertIsNone(metric_flag(1e9, None))


class TestStepMetrics(unittest.TestCase):
    def test_only_the_current_attempt_counts(self) -> None:
        records = [record({"a": 1}, index=2), record({"a": 2}, index=3)]
        self.assertEqual(step_metrics(records, "load", 3)[0]["value"], 2)
        self.assertEqual(step_metrics(records, "load", 4), [])
        self.assertEqual(step_metrics(records, "other", 3), [])

    def test_undeclared_sorted_by_name_with_empty_fields(self) -> None:
        out = step_metrics([record({"zeta": 1, "alpha": 2.5})], "load", 3)
        self.assertEqual([m["name"] for m in out], ["alpha", "zeta"])
        self.assertEqual(
            out[0],
            {
                "name": "alpha",
                "label": None,
                "value": 2.5,
                "unit": None,
                "declared": False,
                "flag": None,
                "updated_at": "2026-10-15T02:05:12Z",
            },
        )

    def test_declared_first_in_declared_order_then_undeclared(self) -> None:
        declared = [MetricDecl("rejected", "Rejected", "rows", warn_above=100), MetricDecl("cov")]
        out = step_metrics([record({"b": 1, "rejected": 150, "a": 2})], "load", 3, declared)
        self.assertEqual([m["name"] for m in out], ["rejected", "cov", "a", "b"])
        self.assertEqual(out[0]["flag"], "above")
        self.assertEqual(out[0]["label"], "Rejected")
        self.assertEqual(out[0]["unit"], "rows")
        self.assertIsNone(out[1]["value"])
        self.assertIsNone(out[1]["updated_at"])
        self.assertTrue(out[1]["declared"])
        self.assertEqual(count_over(out), 1)

    def test_declared_but_no_record_is_not_reported(self) -> None:
        out = step_metrics([], "load", 3, [MetricDecl("m", unit="x", warn_below=5)])
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0]["value"])
        self.assertIsNone(out[0]["flag"])

    def test_no_declarations_and_no_record_is_empty(self) -> None:
        self.assertEqual(step_metrics([], "load", 3), [])


if __name__ == "__main__":
    unittest.main()
