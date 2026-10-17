import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.config import Settings
from app.domain.analysis import build_runs
from app.domain.durations import flag_slow, typical
from app.domain.models import ParseResult
from app.domain.overview import build_overview
from app.domain.parsing import (
    EVENT_LEVELS,
    PIPELINE_NAME,
    alive_key,
    died_key,
    parse_alive,
    parse_died,
    parse_events,
    parse_failures,
    parse_flows,
    parse_markers,
    parse_metrics,
    parse_records,
)
from app.domain.timeline import derive_events, dropped, merge, public, recorded_entries, select
from app.infrastructure.store import RecordStore, StoreUnavailable

UNAVAILABLE = "Data store unavailable"
_RUN_ID = re.compile(r"^\d{8}T\d{6}Z$")

Raw = List[Tuple[str, str]]


class Window(NamedTuple):
    """Everything read for one pipeline and environment in one cached window."""

    at: float
    flows: Raw
    records: Raw
    markers: Raw
    alive: Raw
    died: Raw
    failures: Raw
    event_counts: Dict[str, Dict[str, int]]
    metrics: Raw


def _error(status: int, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message, **extra})


def build_router(
    store: RecordStore,
    settings: Settings,
    clock: Optional[Callable[[], float]] = None,
    now: Optional[Callable[[], datetime]] = None,
) -> APIRouter:
    clock = clock or time.monotonic
    now = now or (lambda: datetime.now(timezone.utc))
    router = APIRouter(prefix="/api")
    cache: Dict[Tuple[str, str], Window] = {}

    def keys_for(env: str, pipeline: str) -> Window:
        """Flows, audit records, start markers, heartbeats, verdicts and failures, in one cached window."""
        hit = cache.get((env, pipeline))
        if hit is not None and clock() - hit.at < settings.cache_seconds:
            return hit
        try:
            window = Window(
                clock(),
                store.list_flows(env, pipeline),
                store.list_records(env, pipeline),
                store.list_markers(env, pipeline),
                store.list_alive(env, pipeline),
                store.list_died(env, pipeline),
                store.list_failures(env, pipeline),
                store.list_event_counts(env, pipeline),
                store.list_metrics(env, pipeline),
            )
        except StoreUnavailable:
            cache.pop((env, pipeline), None)  # never answer an unreachable store from old data
            raise
        cache[(env, pipeline)] = window
        return window

    def record_verdicts(env: str, pipeline: str, built: List[Dict[str, Any]]) -> None:
        """Store the verdict of each run judged Died for the first time (the monitor's only write).

        A failed write (store down, read-only account, another monitor was first) never changes the
        answer: the run is still shown as Died and the write is tried again on a later view.
        """
        attempted = False
        for run in built:
            died = run["died"]
            if died is None or died["recorded"]:
                continue
            attempted = True
            value = {
                "v": 1,
                "pipeline": pipeline,
                "env": env,
                "run_id": run["run_id"],
                "judged_at": died["judged_at"],
                "last_seen_at": died["last_seen_at"],
            }
            if store.record_died(
                died_key(pipeline, env, run["run_id"]),
                json.dumps(value),
                alive_key(pipeline, env, run["run_id"]),
            ):
                died["recorded"] = True
        if attempted:
            cache.pop((env, pipeline), None)  # the next view reads back what is stored

    def build(
        env: str, pipeline: str, moment: datetime
    ) -> Tuple[Any, List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        window = keys_for(env, pipeline)
        parsed = parse_records(env, pipeline, window.records)
        failures, failure_unreadable = parse_failures(env, pipeline, window.failures)
        # a damaged failure item counts as unreadable for its run, like a damaged step record
        by_run = dict(parsed.unreadable_by_run)
        for run_id, count in failure_unreadable.items():
            by_run[run_id] = by_run.get(run_id, 0) + count
        metric_records, metric_unreadable = parse_metrics(env, pipeline, window.metrics)
        for run_id, count in metric_unreadable.items():
            by_run[run_id] = by_run.get(run_id, 0) + count
        parsed = ParseResult(parsed.records, by_run, parsed.unreadable_unattributed)
        flows = parse_flows(env, pipeline, window.flows)
        built = build_runs(
            parsed,
            env,
            pipeline,
            moment,
            settings.stale_hours,
            flows=flows,
            markers=parse_markers(env, pipeline, window.markers),
            stall_seconds=settings.stall_seconds,
            alive=parse_alive(env, pipeline, window.alive),
            verdicts=parse_died(env, pipeline, window.died),
            failures=failures,
            event_counts=window.event_counts,
            metrics=metric_records,
            dead_seconds=settings.heartbeat_dead_seconds,
        )
        record_verdicts(env, pipeline, built)
        # typical durations come from every run read, not only the slice a client asks for
        usual = typical(
            built,
            settings.duration_window_runs,
            settings.duration_min_runs,
            settings.slow_run_multiple,
        )
        flag_slow(built, usual)
        return parsed, built, usual

    @router.get("/health")
    def health() -> JSONResponse:
        try:
            store.ping()
        except StoreUnavailable:
            return _error(503, UNAVAILABLE, redis="unavailable")
        return JSONResponse({"redis": "ok"})

    @router.get("/config")
    def config() -> Dict[str, Any]:
        return {
            "environments": settings.environments,
            "refresh_seconds": settings.refresh_seconds,
            "retry_seconds": settings.retry_seconds,
            "stale_hours": settings.stale_hours,
            "stall_seconds": settings.stall_seconds,
            "heartbeat_dead_seconds": settings.heartbeat_dead_seconds,
            "slow_run_multiple": settings.slow_run_multiple,
            "duration_window_runs": settings.duration_window_runs,
            "duration_min_runs": settings.duration_min_runs,
        }

    @router.get("/pipelines")
    def pipelines(env: str = Query(...)) -> JSONResponse:
        if env not in settings.environments:
            return _error(400, f"Unknown environment '{env}'")
        try:
            names = store.list_pipelines(env)
            moment = now()
            found: List[Dict[str, Any]] = []
            for name in names:
                _, built, _ = build(env, name, moment)
                newest = built[0] if built else None
                label = newest["flow"]["label"] if newest and newest["flow"] else None
                found.append(
                    {
                        "name": name,
                        "label": label or name,
                        "last_run_id": newest["run_id"] if newest else None,
                    }
                )
        except StoreUnavailable:
            return _error(503, UNAVAILABLE)
        found.sort(key=lambda p: (p["last_run_id"] or "", p["name"]), reverse=True)
        return JSONResponse({"env": env, "pipelines": found})

    @router.get("/overview")
    def overview() -> JSONResponse:
        moment = now()
        runs: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        unreadable = 0
        try:
            for env in settings.environments:
                runs[env] = {}
                for name in store.list_pipelines(env):
                    parsed, built, _ = build(env, name, moment)
                    runs[env][name] = built
                    unreadable += parsed.unreadable_total
        except StoreUnavailable:
            return _error(503, UNAVAILABLE)
        return JSONResponse(
            {
                "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "unreadable_total": unreadable,
                "pipelines": build_overview(runs, settings.environments),
            }
        )

    @router.get("/runs")
    def runs(
        env: str = Query(...), pipeline: str = Query(...), limit: int = Query(30, ge=1, le=100)
    ) -> JSONResponse:
        if env not in settings.environments:
            return _error(400, f"Unknown environment '{env}'")
        if not PIPELINE_NAME.match(pipeline):
            return _error(400, f"Invalid pipeline '{pipeline}'")
        moment = now()
        try:
            parsed, built, usual = build(env, pipeline, moment)
        except StoreUnavailable:
            return _error(503, UNAVAILABLE)
        body: Dict[str, Optional[Any]] = {
            "env": env,
            "pipeline": pipeline,
            "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unreadable_total": parsed.unreadable_total,
            "typical": usual,
            "runs": built[:limit],
        }
        return JSONResponse(body)

    @router.get("/runs/{pipeline}/{env}/{run_id}/events")
    def run_events(
        pipeline: str,
        env: str,
        run_id: str,
        level: Optional[str] = Query(None),
        step: Optional[str] = Query(None),
        offset: int = Query(0),
        limit: int = Query(200),
    ) -> JSONResponse:
        """The timeline of one run: recorded events merged with the events derived from its records."""
        if env not in settings.environments:
            return _error(400, f"Unknown environment '{env}'")
        if not PIPELINE_NAME.match(pipeline):
            return _error(400, f"Invalid pipeline '{pipeline}'")
        if not _RUN_ID.match(run_id):
            return _error(400, f"Invalid run id '{run_id}'")
        levels = [part.strip() for part in level.split(",") if part.strip()] if level else None
        if levels and any(part not in EVENT_LEVELS for part in levels):
            return _error(400, "level must be info, warning or error")
        if offset < 0 or not 1 <= limit <= 500:
            return _error(400, "offset must be 0 or more and limit between 1 and 500")
        moment = now()
        try:
            _, built, _ = build(env, pipeline, moment)
            raw = store.read_events(env, pipeline, run_id)
        except StoreUnavailable:
            return _error(503, UNAVAILABLE)
        run = next((r for r in built if r["run_id"] == run_id), None)
        recorded, unreadable = parse_events(env, pipeline, raw)
        derived = derive_events(run, settings.stall_seconds) if run else []
        entries = merge(derived, recorded_entries(recorded))
        page, matched = select(entries, levels, step, offset, limit)
        return JSONResponse(
            {
                "env": env,
                "pipeline": pipeline,
                "run_id": run_id,
                "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total": len(entries),
                "matched": matched,
                "offset": offset,
                "has_more": offset + len(page) < matched,
                "recorded": len(recorded),
                "dropped": dropped(recorded),
                "unreadable": unreadable.get(run_id, 0),
                "events": [public(e) for e in page],
            }
        )

    return router
