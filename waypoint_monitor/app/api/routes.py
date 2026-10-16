import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.config import Settings
from app.domain.analysis import build_runs
from app.domain.overview import build_overview
from app.domain.parsing import (
    PIPELINE_NAME,
    alive_key,
    died_key,
    parse_alive,
    parse_died,
    parse_flows,
    parse_markers,
    parse_records,
)
from app.infrastructure.store import RecordStore, StoreUnavailable

UNAVAILABLE = "Data store unavailable"


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
    Raw = List[Tuple[str, str]]
    cache: Dict[Tuple[str, str], Tuple[float, Raw, Raw, Raw, Raw, Raw]] = {}

    def keys_for(env: str, pipeline: str) -> Tuple[Raw, Raw, Raw, Raw, Raw]:
        """Flows, audit records, start markers, heartbeats and verdicts, read in one cached window."""
        hit = cache.get((env, pipeline))
        if hit is not None and clock() - hit[0] < settings.cache_seconds:
            return hit[1], hit[2], hit[3], hit[4], hit[5]
        try:
            flows = store.list_flows(env, pipeline)
            records = store.list_records(env, pipeline)
            markers = store.list_markers(env, pipeline)
            alive = store.list_alive(env, pipeline)
            died = store.list_died(env, pipeline)
        except StoreUnavailable:
            cache.pop((env, pipeline), None)  # never answer an unreachable store from old data
            raise
        cache[(env, pipeline)] = (clock(), flows, records, markers, alive, died)
        return flows, records, markers, alive, died

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

    def build(env: str, pipeline: str, moment: datetime) -> Tuple[Any, List[Dict[str, Any]]]:
        raw_flows, raw_records, raw_markers, raw_alive, raw_died = keys_for(env, pipeline)
        parsed = parse_records(env, pipeline, raw_records)
        flows = parse_flows(env, pipeline, raw_flows)
        built = build_runs(
            parsed,
            env,
            pipeline,
            moment,
            settings.stale_hours,
            flows=flows,
            markers=parse_markers(env, pipeline, raw_markers),
            stall_seconds=settings.stall_seconds,
            alive=parse_alive(env, pipeline, raw_alive),
            verdicts=parse_died(env, pipeline, raw_died),
            dead_seconds=settings.heartbeat_dead_seconds,
        )
        record_verdicts(env, pipeline, built)
        return parsed, built

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
                _, built = build(env, name, moment)
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
                    parsed, built = build(env, name, moment)
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
            parsed, built = build(env, pipeline, moment)
        except StoreUnavailable:
            return _error(503, UNAVAILABLE)
        body: Dict[str, Optional[Any]] = {
            "env": env,
            "pipeline": pipeline,
            "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unreadable_total": parsed.unreadable_total,
            "runs": built[:limit],
        }
        return JSONResponse(body)

    return router
