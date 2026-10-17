"""How long steps and runs took (specs/012-duration-and-run-events, research R1, R9, R10).

Pure functions over validated records; nothing here reads a store or the clock.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from app.domain.models import StartMarker, StepFailure, StepRecord


@dataclass(frozen=True)
class StepTiming:
    """When an attempt began (None when unknown), how long it took in whole seconds (None when
    unavailable) and whether that was estimated from the previous step's end."""

    started_at: Optional[datetime]
    seconds: Optional[int]
    approx: bool


UNKNOWN = StepTiming(None, None, False)


def _seconds(start: datetime, end: datetime) -> Optional[int]:
    """Whole seconds from `start` to `end`, None when `end` is before `start`."""
    delta = (end - start).total_seconds()
    return None if delta < 0 else int(round(delta))


def finished_timing(
    found: StepRecord, marker: Optional[StartMarker], previous_end: Optional[datetime]
) -> StepTiming:
    """Timing of a step that finished. The first source that exists decides (research R1):

    `duration_ms`, then the record's own `started_at`, then the start marker of the same attempt,
    then (approximate) the end of the previous step, or of the run's start for the first step.
    A result that would be negative is unavailable.
    """
    if found.duration_ms is not None:
        began = found.started_at
        return StepTiming(began, int(round(found.duration_ms / 1000)), False)
    if found.started_at is not None:
        return StepTiming(found.started_at, _seconds(found.started_at, found.finished_at), False)
    if marker is not None and marker.index == found.index:
        return StepTiming(marker.started_at, _seconds(marker.started_at, found.finished_at), False)
    if previous_end is not None:
        return StepTiming(previous_end, _seconds(previous_end, found.finished_at), True)
    return UNKNOWN


def failed_timing(failure: StepFailure) -> StepTiming:
    """Timing of a failed step: from its start to the failure."""
    return StepTiming(failure.started_at, _seconds(failure.started_at, failure.failed_at), False)


def run_duration(
    started: datetime, ended: datetime, now: datetime, running: bool, complete: bool
) -> Dict[str, Any]:
    """The `duration` object of a run: from its own start to its last activity, or to now while
    running. `slow` is set later, once the typical duration is known."""
    seconds = _seconds(started, now if running else ended)
    return {"seconds": seconds, "running": running, "complete": complete, "slow": False}


def typical(
    runs: Sequence[Dict[str, Any]], window: int, min_runs: int, multiple: float
) -> Optional[Dict[str, Any]]:
    """Median and 95th percentile (nearest rank) of the newest `window` finished runs.

    `runs` are built runs, newest first. Only runs that finished (`duration.complete`) with a known
    duration count; Failed, Died, Stalled, Incomplete and running runs never do. None when fewer than
    `min_runs` qualify (research R9).
    """
    values = [
        r["duration"]["seconds"]
        for r in runs
        if r["duration"]["complete"] and r["duration"]["seconds"] is not None
    ][:window]
    if len(values) < max(1, min_runs):
        return None
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    median_seconds = int(math.floor(median + 0.5))
    rank = max(1, math.ceil(0.95 * count))
    return {
        "median_seconds": median_seconds,
        "p95_seconds": ordered[rank - 1],
        "sample": count,
        "window": window,
        "multiple": multiple,
        "slow_after_seconds": int(math.floor(multiple * median_seconds + 0.5)),
    }


def flag_slow(runs: Sequence[Dict[str, Any]], typical_values: Optional[Dict[str, Any]]) -> None:
    """Set `duration.slow` on each run longer than `multiple` times the median. It is only a flag:
    status and ordering never change (spec FR-013)."""
    for run in runs:
        seconds = run["duration"]["seconds"]
        run["duration"]["slow"] = bool(
            typical_values is not None
            and seconds is not None
            and seconds > typical_values["multiple"] * typical_values["median_seconds"]
        )


__all__ = [
    "StepTiming",
    "UNKNOWN",
    "failed_timing",
    "flag_slow",
    "finished_timing",
    "run_duration",
    "typical",
]
