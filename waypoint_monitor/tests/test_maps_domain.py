"""Map step state, summary, item list and item detail (specs/014: US1, US3, US4, US5)."""

import math
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.domain.flow import parse_flow
from app.domain.maps import (
    ItemQueryError,
    item_detail,
    map_state,
    percentile_ms,
    select_items,
    summarize,
    synthetic_failure,
)
from app.domain.parsing import parse_items, parse_maps
from tests.fakes import (
    bucket_of,
    flow_value,
    item_steps,
    make_aggregate,
    make_item,
    map_flow_steps,
)

R1 = "20261015T020000Z"
NOW = datetime(2026, 10, 15, 2, 5, 0, tzinfo=timezone.utc)


def aggregate(**kw: Any) -> Any:
    return parse_maps("prod", "callrail", [make_aggregate("prod", R1, **kw)])[0][0]


def decl() -> Any:
    _, flow = parse_flow(
        "callrail", "prod", R1, flow_value("callrail", "prod", R1, map_flow_steps())
    )
    assert flow is not None and flow.steps[1].map is not None
    return flow.steps[1].map


def items(*pairs: Tuple[str, str]) -> List[Any]:
    return parse_items("prod", "callrail", R1, "accounts", list(pairs))[0]


def summary_for(agg: Any, state: str = "done", min_items: int = 5) -> Dict[str, Any]:
    return summarize(agg, decl(), {"state": state, "duration_seconds": 41}, min_items)


class TestMapState(unittest.TestCase):
    def test_block_open_is_running_even_with_failed_items(self) -> None:
        self.assertEqual(map_state(aggregate(running=4, done=6, ended=False), "running"), "running")
        self.assertEqual(
            map_state(aggregate(running=4, done=5, failed=1, ended=False), "running"), "running"
        )

    def test_block_ended_is_failed_with_a_failed_item_else_done(self) -> None:
        self.assertEqual(map_state(aggregate(done=9, failed=1), "done"), "failed")
        self.assertEqual(map_state(aggregate(done=10), "done"), "done")
        self.assertEqual(map_state(aggregate(), "done"), "done")  # zero items

    def test_a_zero_started_open_block_is_running(self) -> None:
        self.assertEqual(map_state(aggregate(ended=False), "running"), "running")

    def test_stalled_died_and_failed_come_from_the_step(self) -> None:
        for state in ("stalled", "died", "failed"):
            self.assertEqual(map_state(aggregate(running=2, ended=False), state), state)


class TestSummarize(unittest.TestCase):
    def test_numbers_and_declaration(self) -> None:
        agg = aggregate(
            running=0,
            done=9,
            failed=1,
            durations_ms=[3000, 3500, 3900, 4000, 4200, 3800, 3600, 3900, 4100, 9120],
            slowest=[("acct-7", 9120)],
            inner={"transform": {"running": 0, "done": 9, "failed": 1, "in": 480, "out": 455}},
            failed_items=[("acct-7", "transform", "ValueError")],
            in_total=480,
            out_total=455,
            lost_items=1,
        )
        s = summary_for(agg)
        self.assertEqual(s["state"], "failed")
        self.assertEqual(s["counts"], {"started": 10, "running": 0, "done": 9, "failed": 1})
        self.assertEqual((s["in_total"], s["out_total"], s["lost_items"]), (480, 455, 1))
        self.assertEqual(
            (s["concurrency_limit"], s["over"], s["loop_seconds"]), (5, "list_accounts", 41)
        )
        self.assertEqual(s["slowest"], [{"key": "acct-7", "ms": 9120}])
        self.assertEqual(
            s["failed_items"], [{"key": "acct-7", "step": "transform", "error_type": "ValueError"}]
        )
        # one entry per declared inner step, in order, even those no item reached
        self.assertEqual([i["name"] for i in s["inner"]], ["fetch", "transform", "load"])
        self.assertEqual(
            s["inner"][0],
            {"name": "fetch", "running": 0, "done": 0, "failed": 0, "in": 0, "out": 0},
        )
        self.assertEqual(s["inner"][1]["failed"], 1)
        self.assertEqual(s["detail"], {"partial": False, "kept": 10, "failed_without_record": 0})
        self.assertEqual(s["unreadable"], 0)
        self.assertTrue(s["duration"]["enough"])
        self.assertTrue(s["duration"]["approx"])

    def test_percentiles_are_within_five_percent_of_the_true_values(self) -> None:
        values = [int(2000 * 1.07**i) for i in range(40)]
        s = summary_for(aggregate(done=40, durations_ms=values))
        ordered = sorted(values)
        true_median = ordered[math.ceil(0.5 * 40) - 1]
        true_p95 = ordered[math.ceil(0.95 * 40) - 1]
        self.assertLess(abs(s["duration"]["median_ms"] - true_median) / true_median, 0.05)
        self.assertLess(abs(s["duration"]["p95_ms"] - true_p95) / true_p95, 0.05)

    def test_percentiles_need_the_minimum_number_of_finished_items(self) -> None:
        s = summary_for(aggregate(done=4, durations_ms=[1000, 2000, 3000, 4000]))
        self.assertFalse(s["duration"]["enough"])
        self.assertIsNone(s["duration"]["median_ms"])
        self.assertIsNone(s["duration"]["p95_ms"])
        s = summary_for(aggregate(done=4, durations_ms=[1000, 2000, 3000, 4000]), min_items=4)
        self.assertTrue(s["duration"]["enough"])

    def test_percentile_of_nothing_and_of_one_bucket(self) -> None:
        self.assertIsNone(percentile_ms({}, 0.5))
        bucket = bucket_of(5000)
        value = percentile_ms({bucket: 3}, 0.95)
        assert value is not None
        self.assertLess(abs(value - 5000) / 5000, 0.05)

    def test_partial_detail(self) -> None:
        s = summary_for(aggregate(done=9812, failed=188, kept=1050, failed_without_record=37))
        self.assertEqual(s["detail"], {"partial": True, "kept": 1050, "failed_without_record": 37})
        self.assertFalse(summary_for(aggregate(done=10))["detail"]["partial"])

    def test_the_summary_without_a_declaration_uses_the_aggregates_inner_steps(self) -> None:
        agg = aggregate(
            done=1, inner={"zeta": {"running": 0, "done": 1, "failed": 0, "in": 1, "out": 1}}
        )
        s = summarize(agg, None, {"state": "done"}, 5)
        self.assertEqual([i["name"] for i in s["inner"]], ["zeta"])
        self.assertIsNone(s["concurrency_limit"])

    def test_inner_steps_the_flow_does_not_declare_are_kept_after_the_declared_ones(self) -> None:
        agg = aggregate(
            done=1, inner={"extra": {"running": 0, "done": 1, "failed": 0, "in": 0, "out": 0}}
        )
        names = [i["name"] for i in summary_for(agg)["inner"]]
        self.assertEqual(names, ["fetch", "transform", "load", "extra"])


class TestSyntheticFailure(unittest.TestCase):
    def test_it_carries_numbers_only(self) -> None:
        agg = aggregate(done=9, failed=1)
        end = NOW
        failure = synthetic_failure(agg, end)
        self.assertEqual(failure.error.type, "ItemsFailed")
        self.assertEqual(failure.error.message, "1 of 10 items failed")
        self.assertEqual(failure.error.traceback, "")
        self.assertEqual((failure.step, failure.index, failure.failed_at), ("accounts", 2, end))
        self.assertEqual(failure.started_at, agg.started_at)


class TestSelectItems(unittest.TestCase):
    def pile(self, n: int = 12) -> List[Any]:
        pairs = []
        for i in range(1, n + 1):
            state = "failed" if i in (3, 7) else "done"
            ms = 9000 if i == 7 else 3000 + i * 100
            pairs.append(make_item("prod", R1, f"acct-{i}", i, state, duration_ms=ms))
        return items(*pairs)

    def summary(self, **kw: Any) -> Dict[str, Any]:
        done = kw.pop("done", 10)
        return summary_for(
            aggregate(done=done, failed=2, durations_ms=[3000 + i * 100 for i in range(done)], **kw)
        )

    def select(self, pile: Optional[List[Any]] = None, **kw: Any) -> Dict[str, Any]:
        return select_items(
            pile if pile is not None else self.pile(),
            kw.pop("summary", None) or self.summary(),
            now=NOW,
            multiple=2.0,
            **kw,
        )

    def keys(self, result: Dict[str, Any]) -> List[str]:
        return [r["key"] for r in result["items"]]

    def test_default_order_is_arrival_and_the_row_shape(self) -> None:
        result = self.select()
        self.assertEqual(self.keys(result)[:3], ["acct-1", "acct-2", "acct-3"])
        self.assertEqual(result["counts"], {"failed": 2, "running": 0, "done": 10})
        self.assertEqual(result["matched"], 12)
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next"])
        failed = result["items"][2]
        self.assertEqual(
            (failed["state"], failed["failed_step"], failed["error_type"]),
            ("failed", "transform", "ValueError"),
        )
        self.assertIsNone(failed["out"])
        self.assertEqual(failed["in"], 1)
        self.assertFalse(failed["loss"])
        ok = result["items"][0]
        self.assertEqual((ok["in"], ok["out"], ok["duration_ms"]), (1, 48, 3100))

    def test_state_filter_uses_the_stored_state_and_counts_ignore_filters(self) -> None:
        result = self.select(state="failed")
        self.assertEqual(self.keys(result), ["acct-3", "acct-7"])
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["counts"], {"failed": 2, "running": 0, "done": 10})

    def test_search_is_a_case_insensitive_substring(self) -> None:
        self.assertEqual(
            self.keys(self.select(q="ACCT-1")), ["acct-1", "acct-10", "acct-11", "acct-12"]
        )
        self.assertEqual(self.select(q="zzz")["items"], [])

    def test_slow_uses_the_multiple_of_the_median_and_needs_enough_items(self) -> None:
        result = self.select(slow=True)
        self.assertEqual(self.keys(result), ["acct-7"])
        self.assertTrue(result["items"][0]["slow"])
        few = summary_for(aggregate(done=3, durations_ms=[3000, 3100, 3200]))
        self.assertEqual(self.select(summary=few, slow=True)["items"], [])
        self.assertFalse(any(r["slow"] for r in self.select(summary=few)["items"]))

    def test_a_running_item_is_slow_when_its_elapsed_time_passes_the_threshold(self) -> None:
        old = make_item(
            "prod", R1, "acct-90", 90, "running", steps=item_steps(running="fetch"),
            started_at=NOW - timedelta(seconds=30),
        )  # fmt: skip
        young = make_item(
            "prod", R1, "acct-91", 91, "running", steps=item_steps(running="fetch"),
            started_at=NOW - timedelta(seconds=2),
        )  # fmt: skip
        result = self.select(items(old, young), slow=True)
        self.assertEqual(self.keys(result), ["acct-90"])
        row = result["items"][0]
        self.assertEqual(
            (row["state"], row["elapsed_ms"], row["duration_ms"]), ("running", 30000, None)
        )

    def test_sort_by_duration_defaults_to_slowest_first_with_running_items_last(self) -> None:
        running = make_item(
            "prod", R1, "acct-90", 90, "running", steps=item_steps(running="fetch"),
            started_at=NOW - timedelta(seconds=1),
        )  # fmt: skip
        pile = self.pile(5) + items(running)
        result = self.select(pile, sort="duration")
        durations = [r["duration_ms"] for r in result["items"]]
        self.assertEqual(
            durations[:-1], sorted([d for d in durations if d is not None], reverse=True)
        )
        self.assertIsNone(durations[-1])
        asc = self.select(pile, sort="duration", order="asc")
        self.assertIsNone(asc["items"][-1]["duration_ms"])  # still last
        self.assertEqual(asc["items"][0]["duration_ms"], min(d for d in durations if d is not None))

    def test_key_sort_is_natural(self) -> None:
        result = self.select(sort="key")
        self.assertEqual(self.keys(result)[:4], ["acct-1", "acct-2", "acct-3", "acct-4"])
        self.assertEqual(self.keys(result)[-3:], ["acct-10", "acct-11", "acct-12"][-3:])
        self.assertLess(self.keys(result).index("acct-2"), self.keys(result).index("acct-10"))
        desc = self.select(sort="key", order="desc")
        self.assertEqual(self.keys(desc)[0], "acct-12")

    def test_failed_first_puts_failures_before_the_chosen_order(self) -> None:
        result = self.select(failed_first=True)
        self.assertEqual(self.keys(result)[:3], ["acct-3", "acct-7", "acct-1"])
        by_key = self.select(failed_first=True, sort="key", order="desc")
        self.assertEqual(self.keys(by_key)[:3], ["acct-7", "acct-3", "acct-12"])

    def test_equal_sort_values_break_ties_by_arrival_then_key(self) -> None:
        same = [make_item("prod", R1, f"k{i}", i, duration_ms=1000) for i in (3, 1, 2)]
        result = self.select(items(*same), sort="duration")
        self.assertEqual(self.keys(result), ["k1", "k2", "k3"])

    def test_the_cursor_continues_without_repeats_for_every_sort(self) -> None:
        pile = self.pile(120)
        for sort, order, failed_first in (
            ("index", None, False),
            ("duration", None, False),
            ("duration", "asc", True),
            ("key", None, False),
            ("key", "desc", True),
        ):
            with self.subTest(sort=sort, order=order, failed_first=failed_first):
                seen: List[str] = []
                after = None
                for _ in range(10):
                    page = self.select(
                        pile,
                        sort=sort,
                        order=order,
                        failed_first=failed_first,
                        limit=25,
                        after=after,
                    )
                    seen += self.keys(page)
                    after = page["next"]
                    if not page["has_more"]:
                        break
                self.assertEqual(len(seen), 120)
                self.assertEqual(len(set(seen)), 120)
                self.assertEqual(
                    seen,
                    self.keys(
                        self.select(
                            pile, sort=sort, order=order, failed_first=failed_first, limit=200
                        )
                    ),
                )

    def test_an_item_that_appears_between_pages_is_never_shown_twice(self) -> None:
        pile = self.pile(60)
        first = self.select(pile, sort="duration", limit=20)
        # items 61.. finish between the two requests; one is the slowest of all
        more = items(
            make_item("prod", R1, "acct-61", 61, duration_ms=50000),
            make_item("prod", R1, "acct-62", 62, duration_ms=3150),
        )
        second = self.select(pile + more, sort="duration", limit=100, after=first["next"])
        self.assertEqual(set(self.keys(first)) & set(self.keys(second)), set())
        self.assertNotIn("acct-61", self.keys(second))  # skipped in this pass, never repeated
        self.assertIn("acct-62", self.keys(second) + self.keys(first))

    def test_filters_combine(self) -> None:
        result = self.select(state="done", slow=True)
        self.assertEqual(result["items"], [])
        result = self.select(state="failed", q="7")
        self.assertEqual(self.keys(result), ["acct-7"])

    def test_stalled_and_died_maps_show_running_items_with_that_state(self) -> None:
        running = items(
            make_item("prod", R1, "acct-1", 1, "running", steps=item_steps(running="fetch"))
        )
        for state in ("stalled", "died"):
            result = self.select(
                running, summary=summary_for(aggregate(running=1, ended=False), state)
            )
            self.assertEqual(result["items"][0]["state"], state)
            self.assertEqual(result["counts"]["running"], 1)  # the stored state is what is counted
        ok = self.select(running, summary=summary_for(aggregate(running=1, ended=False), "running"))
        self.assertEqual(ok["items"][0]["state"], "running")

    def test_data_loss_marks_the_row(self) -> None:
        pile = items(make_item("prod", R1, "acct-3", 3, steps=item_steps(loss_at="transform")))
        row = self.select(pile)["items"][0]
        self.assertTrue(row["loss"])

    def test_invalid_parameters_raise(self) -> None:
        for kw in (
            {"state": "skipped"},
            {"sort": "name"},
            {"order": "up"},
            {"limit": 0},
            {"limit": 201},
            {"q": "x" * 65},
            {"after": "not a cursor"},
            {"after": "e30"},
        ):
            with self.subTest(kw=kw):
                with self.assertRaises(ItemQueryError):
                    self.select(**kw)

    def test_a_retried_inner_step_shows_its_latest_attempt(self) -> None:
        steps = item_steps()
        steps[1] = dict(steps[1], state="failed", output=None, error={"type": "E", "message": "m"})
        steps.insert(2, dict(item_steps()[1], attempt=2))
        row = self.select(items(make_item("prod", R1, "acct-1", 1, steps=steps)))["items"][0]
        self.assertIsNone(row["failed_step"])  # the second attempt succeeded
        self.assertEqual(row["out"], 48)


class TestItemDetail(unittest.TestCase):
    def detail(self, pair: Tuple[str, str], state: str = "done", **kw: Any) -> Dict[str, Any]:
        item = items(pair)[0]
        summary = summary_for(
            aggregate(done=10, durations_ms=[3000 + i * 100 for i in range(10)]), state
        )
        return item_detail(item, decl(), summary, now=NOW, multiple=2.0, **kw)

    def test_a_failed_item_follows_the_declared_flow_with_not_run(self) -> None:
        d = self.detail(make_item("prod", R1, "acct-7", 7, "failed", duration_ms=9120))
        self.assertEqual([s["name"] for s in d["steps"]], ["fetch", "transform", "load"])
        self.assertEqual([s["state"] for s in d["steps"]], ["done", "failed", "not_run"])
        self.assertEqual(d["steps"][1]["error"]["type"], "ValueError")
        self.assertIn("traceback", d["steps"][1]["error"])
        self.assertEqual(d["steps"][0]["inputs"], [{"name": "account", "value": 1}])
        self.assertEqual(
            (d["key"], d["state"], d["slow"], d["compact"]), ("acct-7", "failed", True, False)
        )
        self.assertIsNone(d["error"])
        self.assertEqual(d["duration_ms"], 9120)

    def test_a_running_item_has_waiting_steps_and_elapsed_time(self) -> None:
        pair = make_item(
            "prod", R1, "acct-9", 9, "running", steps=item_steps(running="transform"),
            started_at=NOW - timedelta(seconds=12),
        )  # fmt: skip
        d = self.detail(pair)
        self.assertEqual([s["state"] for s in d["steps"]], ["done", "running", "waiting"])
        self.assertEqual(d["elapsed_ms"], 12000)
        self.assertIsNone(d["finished_at"])

    def test_in_a_stalled_map_running_steps_show_that_state_and_later_steps_did_not_run(
        self,
    ) -> None:
        pair = make_item(
            "prod", R1, "acct-9", 9, "running", steps=item_steps(running="transform"),
            started_at=NOW - timedelta(seconds=12),
        )  # fmt: skip
        d = self.detail(pair, state="stalled")
        self.assertEqual(d["state"], "stalled")
        self.assertEqual([s["state"] for s in d["steps"]], ["done", "stalled", "not_run"])

    def test_loss_and_metrics_use_the_spec_013_shape_with_declared_thresholds(self) -> None:
        pair = make_item(
            "prod", R1, "acct-3", 3, steps=item_steps(loss_at="transform"),
            metrics={"transform": {"rejected": 150, "retries": 2}},
        )  # fmt: skip
        d = self.detail(pair)
        transform = d["steps"][1]
        self.assertTrue(transform["loss"])
        self.assertFalse(d["steps"][0]["loss"])
        names = [m["name"] for m in transform["metrics"]]
        self.assertEqual(names, ["rejected", "retries"])
        rejected = transform["metrics"][0]
        self.assertEqual(
            (rejected["value"], rejected["unit"], rejected["flag"], rejected["over"]),
            (150, "rows", "above", True),
        )
        self.assertFalse(transform["metrics"][1]["over"])
        self.assertNotIn("metrics", d["steps"][0])

    def test_a_declared_metric_not_reported_is_shown_as_not_reported(self) -> None:
        d = self.detail(make_item("prod", R1, "acct-1", 1))
        metrics = d["steps"][1]["metrics"]
        self.assertEqual(len(metrics), 1)
        self.assertIsNone(metrics[0]["value"])
        self.assertFalse(metrics[0]["over"])

    def test_a_result_for_an_undeclared_step_is_added_as_unplanned(self) -> None:
        steps = item_steps() + [dict(item_steps()[0], step="audit", attempt=1)]
        d = self.detail(make_item("prod", R1, "acct-1", 1, steps=steps))
        self.assertEqual(d["steps"][-1]["name"], "audit")
        self.assertTrue(d["steps"][-1]["unplanned"])

    def test_an_item_level_error_and_a_compact_record_pass_through(self) -> None:
        pair = make_item(
            "prod", R1, "acct-2", 2, "failed", steps=[], compact=True,
            error={"type": "KeyError", "message": "k"},
        )  # fmt: skip
        d = self.detail(pair)
        self.assertTrue(d["compact"])
        self.assertEqual(d["error"], {"type": "KeyError", "message": "k", "traceback": ""})
        self.assertEqual([s["state"] for s in d["steps"]], ["not_run"] * 3)

    def test_inputs_follow_the_declared_input_names(self) -> None:
        steps = item_steps()
        steps[1]["inputs"] = {"zzz": 5, "rows": 48}
        d = self.detail(make_item("prod", R1, "acct-1", 1, steps=steps))
        self.assertEqual([i["name"] for i in d["steps"][1]["inputs"]], ["rows", "zzz"])

    def test_without_a_declaration_the_recorded_steps_are_all_unplanned(self) -> None:
        item = items(make_item("prod", R1, "acct-1", 1))[0]
        d = item_detail(item, None, {"state": "done"}, now=NOW, multiple=2.0)
        self.assertEqual([s["name"] for s in d["steps"]], ["fetch", "transform", "load"])
        self.assertTrue(all(s["unplanned"] for s in d["steps"]))


if __name__ == "__main__":
    unittest.main()
