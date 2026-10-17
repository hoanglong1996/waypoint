"""Map steps as the API serves them (specs/014-map-step-fan-out, research R6, R7, R10, R12).

Pure functions over validated aggregates and item records and the run's own declaration; nothing
here reads a store or the clock.
"""

import base64
import binascii
import json
import math
import re
from datetime import datetime
from functools import cmp_to_key
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from app.domain.metrics import step_metrics
from app.domain.models import (
    ErrorInfo,
    ItemRecord,
    ItemStepResult,
    MapAggregate,
    MapDecl,
    MetricDecl,
    StepFailure,
    StepMetrics,
)

HIST_RATIO = 1.1
MAX_LIMIT = 200
MAX_QUERY = 64
STATES = ("failed", "running", "done")
SORTS = ("index", "duration", "key")
ITEMS_FAILED = "ItemsFailed"


class ItemQueryError(ValueError):
    """A parameter of the item list is not valid (the API answers 400)."""


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------------
# State and summary


def map_state(aggregate: MapAggregate, step_state: str) -> str:
    """The state of a map step (research R6): the run's own state for a stalled, died or failed step;
    running while the block is open (even when items have failed); once the block has ended, failed
    when any item failed, else done."""
    if step_state in ("stalled", "died", "failed", "running"):
        return step_state
    if step_state in ("done", "unplanned"):
        return "failed" if aggregate.counts.failed > 0 else "done"
    return step_state


def synthetic_failure(aggregate: MapAggregate, ended_at: datetime) -> StepFailure:
    """The failure a map step gets when items failed but its block ended normally: numbers only, no
    stack trace, so nothing about the items' data can appear in it (research R6)."""
    counts = aggregate.counts
    return StepFailure(
        pipeline=aggregate.pipeline,
        run_id=aggregate.run_id,
        env=aggregate.env,
        step=aggregate.map,
        index=aggregate.index,
        started_at=aggregate.started_at,
        failed_at=ended_at,
        error=ErrorInfo(
            type=ITEMS_FAILED,
            message=f"{counts.failed} of {counts.started} items failed",
            traceback="",
        ),
    )


def _bucket_midpoint(bucket: int) -> int:
    return int(round(HIST_RATIO ** (bucket + 0.5)))


def percentile_ms(hist: Mapping[int, int], q: float) -> Optional[int]:
    """Nearest-rank percentile of a duration histogram: the geometric midpoint of the bucket holding
    the item of rank `ceil(q * n)`; within 5% of the true value. None for an empty histogram."""
    total = sum(hist.values())
    if total <= 0:
        return None
    rank = max(1, math.ceil(q * total))
    seen = 0
    for bucket in sorted(hist):
        seen += hist[bucket]
        if seen >= rank:
            return _bucket_midpoint(bucket)
    return None


def slow_threshold_ms(summary: Mapping[str, Any], multiple: float) -> Optional[float]:
    """Items longer than this are slow: `multiple` times the median item duration, once at least the
    minimum number of items finished (research R7). None when percentiles are not available."""
    duration = summary.get("duration") or {}
    median = duration.get("median_ms")
    if not duration.get("enough") or median is None:
        return None
    return float(multiple) * float(median)


def summarize(
    aggregate: MapAggregate,
    decl: Optional[MapDecl],
    step: Mapping[str, Any],
    min_items: int,
) -> Dict[str, Any]:
    """The `map` object of a run's step (contracts/api.md). `step` is the step as built so far (its
    `state` and `duration_seconds`); `min_items` is `duration_min_runs`."""
    counts = aggregate.counts
    total = sum(aggregate.hist.values())
    enough = total >= max(1, min_items)
    declared = [s.name for s in decl.steps] if decl else []
    by_name = {i.name: i for i in aggregate.inner}
    inner: List[Dict[str, Any]] = []
    for name in declared + [n for n in by_name if n not in declared]:
        entry = by_name.get(name)
        inner.append(
            {
                "name": name,
                "running": entry.running if entry else 0,
                "done": entry.done if entry else 0,
                "failed": entry.failed if entry else 0,
                "in": entry.inputs_total if entry else 0,
                "out": entry.output_total if entry else 0,
            }
        )
    return {
        "state": map_state(aggregate, str(step.get("state"))),
        "counts": {
            "started": counts.started,
            "running": counts.running,
            "done": counts.done,
            "failed": counts.failed,
        },
        "in_total": aggregate.in_total,
        "out_total": aggregate.out_total,
        "lost_items": aggregate.lost_items,
        "concurrency_limit": decl.max_concurrency if decl else None,
        "over": decl.over if decl else None,
        "loop_seconds": step.get("duration_seconds"),
        "duration": {
            "count": total,
            "median_ms": percentile_ms(aggregate.hist, 0.5) if enough else None,
            "p95_ms": percentile_ms(aggregate.hist, 0.95) if enough else None,
            "approx": True,
            "enough": enough,
        },
        "slowest": [{"key": k, "ms": ms} for k, ms in aggregate.slowest],
        "failed_items": [
            {"key": k, "step": s, "error_type": e} for k, s, e in aggregate.failed_items
        ],
        "inner": inner,
        "detail": {
            "partial": counts.started > aggregate.kept,
            "kept": aggregate.kept,
            "failed_without_record": aggregate.failed_without_record,
        },
        "unreadable": 0,
    }


# ---------------------------------------------------------------------------------------------------
# Items


def effective_state(item: ItemRecord, map_state_value: str) -> str:
    """An item stored as running in a stalled or died map step is shown with that state (research R12)."""
    if item.state == "running" and map_state_value in ("stalled", "died"):
        return map_state_value
    return item.state


def _latest_steps(item: ItemRecord) -> List[ItemStepResult]:
    """The latest attempt of each inner step, in the order the steps first began."""
    best: Dict[str, ItemStepResult] = {}
    order: List[str] = []
    for result in item.steps:
        if result.step not in best:
            order.append(result.step)
        if result.step not in best or result.attempt >= best[result.step].attempt:
            best[result.step] = result
    return [best[name] for name in order]


def _is_loss(result: ItemStepResult) -> bool:
    return (
        result.state == "done"
        and result.output == 0
        and any(value > 0 for value in result.inputs.values())
    )


def _elapsed_ms(item: ItemRecord, now: datetime) -> int:
    return max(0, int((now - item.started_at).total_seconds() * 1000))


def _is_slow(item: ItemRecord, threshold: Optional[float], now: datetime) -> bool:
    if threshold is None:
        return False
    if item.state == "running":
        return _elapsed_ms(item, now) > threshold
    return item.duration_ms is not None and item.duration_ms > threshold


def item_row(
    item: ItemRecord, state: str, threshold: Optional[float], now: datetime
) -> Dict[str, Any]:
    """One row of the item list (contracts/api.md)."""
    steps = _latest_steps(item)
    failed = next((s for s in steps if s.state == "failed"), None)
    error = failed.error if failed and failed.error else item.error
    first, last = (steps[0], steps[-1]) if steps else (None, None)
    row: Dict[str, Any] = {
        "key": item.key,
        "index": item.index,
        "state": state,
        "slow": _is_slow(item, threshold, now),
        "started_at": _iso(item.started_at),
        "duration_ms": item.duration_ms,
        "failed_step": failed.step if failed else None,
        "error_type": error.type if error else None,
        "in": sum(first.inputs.values()) if first else None,
        "out": last.output if last and last.state == "done" else None,
        "loss": any(_is_loss(s) for s in steps),
        "compact": item.compact,
    }
    if item.state == "running":
        row["elapsed_ms"] = _elapsed_ms(item, now)
    return row


def _natural(key: str) -> List[List[Any]]:
    """Case-insensitive natural order: `acct-2` before `acct-10`."""
    return [
        [0, int(part)] if part.isdigit() else [1, part]
        for part in re.split(r"(\d+)", key.lower())
        if part != ""
    ]


SortKey = Tuple[int, Any, int, str]


def _sort_key(row: Mapping[str, Any], sort: str, failed_first: bool) -> SortKey:
    group = 0 if failed_first and row["state"] == "failed" else 1
    if sort == "duration":
        value: Any = row["duration_ms"]
    elif sort == "key":
        value = _natural(row["key"])
    else:
        value = row["index"]
    return (group, value, row["index"], row["key"])


def _comparator(desc: bool) -> Callable[[SortKey, SortKey], int]:
    def compare(a: SortKey, b: SortKey) -> int:
        if a[0] != b[0]:
            return -1 if a[0] < b[0] else 1
        if a[1] != b[1]:
            if a[1] is None:  # no value (a running item sorted by duration) is always last
                return 1
            if b[1] is None:
                return -1
            result = -1 if a[1] < b[1] else 1
            return -result if desc else result
        if a[2] != b[2]:
            return -1 if a[2] < b[2] else 1
        return (a[3] > b[3]) - (a[3] < b[3])

    return compare


def encode_cursor(key: SortKey) -> str:
    raw = json.dumps(list(key), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(text: str) -> SortKey:
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        group, value, index, key = json.loads(raw)
    except (ValueError, binascii.Error, TypeError):
        raise ItemQueryError("after is not a cursor from this list") from None
    if not (
        isinstance(group, int)
        and isinstance(index, int)
        and isinstance(key, str)
        and (value is None or isinstance(value, (int, list)))
    ):
        raise ItemQueryError("after is not a cursor from this list")
    return (group, value, index, key)


def validate_query(
    state: Optional[str],
    q: Optional[str],
    sort: str,
    order: Optional[str],
    limit: int,
) -> None:
    """Raise `ItemQueryError` for a parameter the item list does not accept."""
    if state is not None and state not in STATES:
        raise ItemQueryError("state must be failed, running or done")
    if sort not in SORTS:
        raise ItemQueryError("sort must be index, duration or key")
    if order is not None and order not in ("asc", "desc"):
        raise ItemQueryError("order must be asc or desc")
    if not 1 <= limit <= MAX_LIMIT:
        raise ItemQueryError(f"limit must be between 1 and {MAX_LIMIT}")
    if q is not None and len(q) > MAX_QUERY:
        raise ItemQueryError(f"q must be at most {MAX_QUERY} characters")


def select_items(
    items: Sequence[ItemRecord],
    summary: Mapping[str, Any],
    *,
    now: datetime,
    multiple: float,
    state: Optional[str] = None,
    slow: bool = False,
    q: Optional[str] = None,
    sort: str = "index",
    order: Optional[str] = None,
    failed_first: bool = False,
    limit: int = 50,
    after: Optional[str] = None,
) -> Dict[str, Any]:
    """One page of the item list (research R7): the rows, the counts over every record read, how many
    match the filters and the cursor for the next page.

    Order: failed first (when asked), the sort value, the arrival number, the key: total and
    deterministic. The cursor holds the last row's position, so a page never repeats a row.
    """
    validate_query(state, q, sort, order, limit)
    cursor = decode_cursor(after) if after else None
    threshold = slow_threshold_ms(summary, multiple)
    desc = (order or ("desc" if sort == "duration" else "asc")) == "desc"
    map_value = str(summary.get("state"))
    counts = {"failed": 0, "running": 0, "done": 0}
    rows: List[Tuple[SortKey, Dict[str, Any]]] = []
    needle = q.lower() if q else None
    for item in items:
        counts[item.state] += 1
        if state is not None and item.state != state:
            continue
        if needle is not None and needle not in item.key.lower():
            continue
        row = item_row(item, effective_state(item, map_value), threshold, now)
        if slow and not row["slow"]:
            continue
        rows.append((_sort_key(row, sort, failed_first), row))
    compare = _comparator(desc)
    ordering = cmp_to_key(compare)
    rows.sort(key=lambda r: ordering(r[0]))
    matched = len(rows)
    if cursor is not None:
        rows = [r for r in rows if compare(r[0], cursor) > 0]
    page = rows[:limit]
    more = len(rows) > limit
    return {
        "items": [row for _, row in page],
        "counts": counts,
        "matched": matched,
        "has_more": more,
        "next": encode_cursor(page[-1][0]) if more and page else None,
    }


def _error_json(error: ErrorInfo) -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": error.type}
    if error.message is not None:
        out["message"] = error.message
    out["traceback"] = error.traceback
    return out


def _ordered_inputs(declared: Sequence[str], inputs: Mapping[str, int]) -> List[Dict[str, Any]]:
    ordered = [{"name": n, "value": inputs[n]} for n in declared if n in inputs]
    ordered += [{"name": n, "value": v} for n, v in inputs.items() if n not in declared]
    return ordered


def _step_json(
    result: ItemStepResult,
    declared_inputs: Sequence[str],
    declared_metrics: Sequence[MetricDecl],
    item: ItemRecord,
    state: str,
    unplanned: bool,
) -> Dict[str, Any]:
    values = item.metrics.get(result.step, {})
    record = StepMetrics(
        item.pipeline, item.run_id, item.env, result.step, result.attempt, dict(values), None
    )
    metrics = [
        {**m, "over": m["flag"] is not None}
        for m in step_metrics([record], result.step, result.attempt, declared_metrics)
    ]
    out: Dict[str, Any] = {
        "name": result.step,
        "state": state,
        "inputs": _ordered_inputs(declared_inputs, result.inputs),
        "output": result.output,
        "duration_ms": result.duration_ms,
        "loss": _is_loss(result),
    }
    if result.error is not None:
        out["error"] = _error_json(result.error)
    if metrics:
        out["metrics"] = metrics
    if unplanned:
        out["unplanned"] = True
    return out


def item_detail(
    item: ItemRecord,
    decl: Optional[MapDecl],
    summary: Mapping[str, Any],
    *,
    now: datetime,
    multiple: float,
) -> Dict[str, Any]:
    """One item for the item view (contracts/api.md): its inner steps in the declared order, with
    `not_run` or `waiting` for a declared step with no result."""
    map_value = str(summary.get("state"))
    state = effective_state(item, map_value)
    latest = {r.step: r for r in _latest_steps(item)}
    steps: List[Dict[str, Any]] = []
    waiting = item.state == "running" and state == "running"
    declared = decl.steps if decl else ()
    for flow_step in declared:
        result = latest.pop(flow_step.name, None)
        if result is None:
            steps.append({"name": flow_step.name, "state": "waiting" if waiting else "not_run"})
            continue
        shown = state if result.state == "running" and state != "running" else result.state
        steps.append(
            _step_json(
                result,
                [i.name for i in flow_step.inputs],
                flow_step.metrics,
                item,
                shown,
                False,
            )
        )
    for result in latest.values():  # recorded but not declared
        shown = state if result.state == "running" and state != "running" else result.state
        steps.append(_step_json(result, [], (), item, shown, True))
    row = item_row(item, state, slow_threshold_ms(summary, multiple), now)
    out: Dict[str, Any] = {
        "key": item.key,
        "index": item.index,
        "state": state,
        "slow": row["slow"],
        "compact": item.compact,
        "started_at": _iso(item.started_at),
        "finished_at": _iso(item.finished_at) if item.finished_at else None,
        "duration_ms": item.duration_ms,
        "steps": steps,
        "error": _error_json(item.error) if item.error else None,
    }
    if item.state == "running":
        out["elapsed_ms"] = _elapsed_ms(item, now)
    return out
