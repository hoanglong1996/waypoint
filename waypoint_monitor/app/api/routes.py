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
from app.domain.flow import parse_flow
from app.domain.maps import ItemQueryError, item_detail, select_items, validate_query
from app.domain.models import MapDecl, ParseResult
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
    parse_item,
    parse_items,
    parse_maps,
    parse_markers,
    parse_metrics,
    parse_records,
)
from app.domain.timeline import derive_events, dropped, merge, public, recorded_entries, select
from app.infrastructure.store import RecordStore, StoreUnavailable

UNAVAILABLE = "Data store unavailable"
_RUN_ID = re.compile(r"^\d{8}T\d{6}Z$")
_MAP_NAME = re.compile(r"^[a-z0-9_]{1,64}$")
_ITEM_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

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
    maps: Raw


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
    item_cache: Dict[Tuple[str, str, str, str], Tuple[float, Raw]] = {}

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
                store.list_maps(env, pipeline),
            )
        except StoreUnavailable:
            cache.pop((env, pipeline), None)  # never answer an unreachable store from old data
            raise
        cache[(env, pipeline)] = window
        return window

    def items_for(env: str, pipeline: str, run_id: str, map_name: str) -> Raw:
        """The raw item records of one map step of one run, cached for `cache_seconds`."""
        name = (env, pipeline, run_id, map_name)
        hit = item_cache.get(name)
        if hit is not None and clock() - hit[0] < settings.cache_seconds:
            return hit[1]
        try:
            raw = store.list_items(env, pipeline, run_id, map_name)
        except StoreUnavailable:
            item_cache.pop(name, None)
            raise
        if len(item_cache) > 64:  # keep the cache small: only the maps being looked at matter
            item_cache.clear()
        item_cache[name] = (clock(), raw)
        return raw

    def map_of(
        env: str, pipeline: str, run_id: str, map_name: str, moment: datetime
    ) -> Optional[Tuple[Dict[str, Any], Optional[MapDecl]]]:
        """The `map` summary of a run's map step and its declaration, or None when the run or the
        step has no map data."""
        _, built, _ = build(env, pipeline, moment)
        run = next((r for r in built if r["run_id"] == run_id), None)
        step = next((s for s in run["steps"] if s["name"] == map_name), None) if run else None
        if step is None or "map" not in step:
            return None
        decl: Optional[MapDecl] = None
        wanted = f"waypoint:{pipeline}:{env}:{run_id}:flow"
        raw_flow = next((v for k, v in keys_for(env, pipeline).flows if k == wanted), None)
        if raw_flow is not None:
            _, flow = parse_flow(pipeline, env, run_id, raw_flow)
            found = next((s for s in flow.steps if s.name == map_name), None) if flow else None
            decl = found.map if found else None
        return step["map"], decl

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
        aggregates, map_unreadable = parse_maps(env, pipeline, window.maps)
        for run_id, count in map_unreadable.items():
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
            maps=aggregates,
            min_items=settings.duration_min_runs,
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

    def _map_path_error(
        pipeline: str, env: str, run_id: str, map_name: str
    ) -> Optional[JSONResponse]:
        if env not in settings.environments:
            return _error(400, f"Unknown environment '{env}'")
        if not PIPELINE_NAME.match(pipeline):
            return _error(400, f"Invalid pipeline '{pipeline}'")
        if not _RUN_ID.match(run_id):
            return _error(400, f"Invalid run id '{run_id}'")
        if not _MAP_NAME.match(map_name):
            return _error(400, f"Invalid map step '{map_name}'")
        return None

    def _flag(value: Optional[int]) -> Optional[bool]:
        return None if value is None else (True if value == 1 else False if value == 0 else None)

    @router.get("/runs/{pipeline}/{env}/{run_id}/maps/{map_name}/items")
    def map_items(
        pipeline: str,
        env: str,
        run_id: str,
        map_name: str,
        state: Optional[str] = Query(None),
        slow: Optional[int] = Query(None),
        q: Optional[str] = Query(None),
        sort: str = Query("index"),
        order: Optional[str] = Query(None),
        failed_first: Optional[int] = Query(None),
        limit: int = Query(50),
        after: Optional[str] = Query(None),
    ) -> JSONResponse:
        """One page of a map step's item list: filter by state, slow and key text, sort, page by cursor."""
        bad = _map_path_error(pipeline, env, run_id, map_name)
        if bad is not None:
            return bad
        slow_on, first_on = _flag(slow), _flag(failed_first)
        if slow_on is None and slow is not None or first_on is None and failed_first is not None:
            return _error(400, "slow and failed_first must be 0 or 1")
        try:
            validate_query(state, q, sort, order, limit)
        except ItemQueryError as exc:
            return _error(400, str(exc))
        moment = now()
        try:
            found = map_of(env, pipeline, run_id, map_name, moment)
            raw = items_for(env, pipeline, run_id, map_name) if found else []
        except StoreUnavailable:
            return _error(503, UNAVAILABLE)
        records, unreadable = parse_items(env, pipeline, run_id, map_name, raw)
        summary = found[0] if found else None
        try:
            page = (
                select_items(
                    records,
                    summary,
                    now=moment,
                    multiple=settings.slow_run_multiple,
                    state=state,
                    slow=bool(slow_on),
                    q=q,
                    sort=sort,
                    order=order,
                    failed_first=bool(first_on),
                    limit=limit,
                    after=after,
                )
                if summary is not None
                else {
                    "items": [],
                    "counts": {"failed": 0, "running": 0, "done": 0},
                    "matched": 0,
                    "has_more": False,
                    "next": None,
                }
            )
        except ItemQueryError as exc:
            return _error(400, str(exc))
        return JSONResponse(
            {
                "env": env,
                "pipeline": pipeline,
                "run_id": run_id,
                "map": map_name,
                "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "state": summary["state"] if summary else None,
                "total": summary["counts"]["started"] if summary else 0,
                "with_record": len(records),
                "counts": page["counts"],
                "partial": bool(summary and summary["detail"]["partial"]),
                "failed_without_record": (
                    summary["detail"]["failed_without_record"] if summary else 0
                ),
                "matched": page["matched"],
                "has_more": page["has_more"],
                "next": page["next"],
                "items": page["items"],
                "unreadable": unreadable,
            }
        )

    @router.get("/runs/{pipeline}/{env}/{run_id}/maps/{map_name}/items/{key}")
    def map_item(pipeline: str, env: str, run_id: str, map_name: str, key: str) -> JSONResponse:
        """One item of a map step for the item view; 404 when it has no record of its own."""
        bad = _map_path_error(pipeline, env, run_id, map_name)
        if bad is not None:
            return bad
        if not _ITEM_KEY.match(key):
            return _error(400, f"Invalid item key '{key}'")
        moment = now()
        try:
            found = map_of(env, pipeline, run_id, map_name, moment)
            raw = store.read_item(env, pipeline, run_id, map_name, key) if found else None
        except StoreUnavailable:
            return _error(503, UNAVAILABLE)
        record = parse_item(env, pipeline, run_id, map_name, key, raw) if raw else None
        if found is None or record is None:
            return _error(404, "Item not found")
        return JSONResponse(
            item_detail(record, found[1], found[0], now=moment, multiple=settings.slow_run_multiple)
        )

    @router.get("/runs/{pipeline}/{env}/{run_id}/events")
    def run_events(
        pipeline: str,
        env: str,
        run_id: str,
        level: Optional[str] = Query(None),
        step: Optional[str] = Query(None),
        item: Optional[str] = Query(None),
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
        if item is not None and not _ITEM_KEY.match(item):
            return _error(400, f"Invalid item key '{item}'")
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
        page, matched = select(entries, levels, step, offset, limit, item)
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
