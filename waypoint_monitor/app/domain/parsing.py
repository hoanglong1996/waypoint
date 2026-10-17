import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.domain.flow import parse_flow
from app.domain.models import (
    AliveSignal,
    DiedVerdict,
    ErrorInfo,
    FieldValue,
    Flow,
    ItemRecord,
    ItemStepResult,
    MapAggregate,
    MapCounts,
    MapInner,
    MetricNumber,
    ParseResult,
    RunEvent,
    StartMarker,
    StepFailure,
    StepMetrics,
    StepRecord,
)

_RUN_ID = re.compile(r"^\d{8}T\d{6}Z$")
ROOT = "waypoint"
MAX_ERROR_TYPE = 200
MAX_ERROR_MESSAGE = 500
MAX_TRACEBACK_BYTES = 8192
_OMITTED = "... (earlier frames omitted)\n"
PIPELINE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_P = r"(?P<pipeline>[a-z0-9][a-z0-9_-]{0,39}):(?P<env>[^:]+):(?P<run>\d{8}T\d{6}Z)"
_KEY = re.compile(rf"^{ROOT}:{_P}:step:(?P<idx>\d{{2,}})-(?P<step>.+)$")
_MARKER_KEY = re.compile(rf"^{ROOT}:{_P}:running:(?P<idx>\d{{2,}})-(?P<step>.+)$")
_FLOW_KEY = re.compile(rf"^{ROOT}:{_P}:flow$")
_FAILED_KEY = re.compile(rf"^{ROOT}:{_P}:failed:(?P<idx>\d{{2,}})-(?P<step>.+)$")
EVENT_LEVELS = ("info", "warning", "error")
MAX_EVENT_MESSAGE = 300
MAX_EVENT_FIELDS = 10
MAX_EVENT_TEXT = 100
MAX_EVENT_STEP = 200
_FIELD_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
_EVENTS_KEY = re.compile(rf"^{ROOT}:{_P}:events:(?P<level>info|warning|error)$")
_METRICS_KEY = re.compile(rf"^{ROOT}:{_P}:metrics:(?P<idx>\d{{2,}})-(?P<step>.+)$")
MAX_METRICS_PER_STEP = 20
_METRIC_NAME = re.compile(r"^[a-z0-9_]{1,64}$")
_MAP_KEY = re.compile(rf"^{ROOT}:{_P}:map:(?P<map>[a-z0-9_]{{1,64}})$")
_ITEM_KEY = re.compile(
    rf"^{ROOT}:{_P}:item:(?P<map>[a-z0-9_]{{1,64}}):(?P<key>[A-Za-z0-9_.-]{{1,64}})$"
)
_ITEM_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_INNER_STEPS = 20
MAX_MAP_FAILED_LISTED = 20
MAX_MAP_SLOWEST_LISTED = 5
MAX_ITEM_TRACEBACK_BYTES = 2048
_ALIVE_KEY = re.compile(rf"^{ROOT}:{_P}:alive$")
_DIED_KEY = re.compile(rf"^{ROOT}:{_P}:died$")
_ANY_KEY = re.compile(rf"^{ROOT}:(?P<pipeline>[a-z0-9][a-z0-9_-]{{0,39}}):(?P<env>[^:]+):")


def alive_key(pipeline: str, env: str, run_id: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:alive"


def died_key(pipeline: str, env: str, run_id: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:died"


def parse_run_id(run_id: str) -> datetime:
    return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_time(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _validate(pipeline: str, env: str, run_id: str, step: str, raw: str) -> Optional[StepRecord]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    index = data.get("index")
    inputs = data.get("inputs")
    output = data.get("output")
    finished = _parse_time(data.get("finished_at"))
    if data.get("run_id") != run_id or data.get("env") != env:
        return None
    if data.get("pipeline") != pipeline or data.get("step") != step:
        return None
    if not (isinstance(index, int) and not isinstance(index, bool) and index >= 1):
        return None
    if not isinstance(inputs, dict) or not all(_is_count(v) for v in inputs.values()):
        return None
    if output is not None and not _is_count(output):
        return None
    if finished is None:
        return None
    began = _parse_time(data.get("started_at"))
    duration = data.get("duration_ms")
    if not _is_count(duration):  # wrong type: treated as absent, the record stays readable
        duration = None
    # Only known fields are kept; anything else in the record is dropped.
    return StepRecord(
        pipeline=pipeline,
        run_id=run_id,
        env=env,
        step=step,
        index=index,
        inputs={str(k): int(v) for k, v in inputs.items()},
        output=output,
        finished_at=finished,
        started_at=began,
        duration_ms=duration,
    )


def parse_records(env: str, pipeline: str, raw: Iterable[Tuple[str, str]]) -> ParseResult:
    """Validate raw `(key, json)` pairs. Never raises; invalid records are counted."""
    records: List[StepRecord] = []
    by_run: Dict[str, int] = {}
    unattributed = 0
    for key, value in raw:
        match = _KEY.match(key)
        if not match:
            # a malformed key under this pipeline counts as unreadable; foreign keys are not ours
            if key.startswith(f"{ROOT}:{pipeline}:{env}:"):
                unattributed += 1
            continue
        if match["env"] != env or match["pipeline"] != pipeline:
            continue
        run_id = match["run"]
        record = _validate(pipeline, env, run_id, match["step"], value)
        if record is None:
            by_run[run_id] = by_run.get(run_id, 0) + 1
        else:
            records.append(record)
    return ParseResult(records, by_run, unattributed)


def _shorten_traceback(text: str, limit: int = MAX_TRACEBACK_BYTES) -> str:
    """At most `limit` UTF-8 bytes (8192 for a step, 2048 for an item), keeping the last frames (a
    longer one was not written by the library)."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    room = limit - len(_OMITTED.encode("utf-8"))
    return _OMITTED + raw[-room:].decode("utf-8", errors="ignore")


def _validate_failure(
    pipeline: str, env: str, run_id: str, step: str, key_index: int, raw: str
) -> Optional[StepFailure]:
    data = _load(raw, pipeline, env, run_id)
    if data is None or data.get("step") != step:
        return None
    index = data.get("index")
    if not (isinstance(index, int) and not isinstance(index, bool) and index >= 1):
        return None
    if index != key_index:
        return None
    started = _parse_time(data.get("started_at"))
    failed = _parse_time(data.get("failed_at"))
    error = data.get("error")
    if started is None or failed is None or not isinstance(error, dict):
        return None
    kind, message, trace = error.get("type"), error.get("message"), error.get("traceback")
    if not isinstance(kind, str) or not kind or not isinstance(trace, str):
        return None
    if message is not None and not isinstance(message, str):
        return None
    return StepFailure(
        pipeline=pipeline,
        run_id=run_id,
        env=env,
        step=step,
        index=index,
        started_at=started,
        failed_at=failed,
        error=ErrorInfo(
            type=kind[:MAX_ERROR_TYPE],
            message=message[:MAX_ERROR_MESSAGE] if message else None,
            traceback=_shorten_traceback(trace),
        ),
    )


def parse_failures(
    env: str, pipeline: str, raw: Iterable[Tuple[str, str]]
) -> Tuple[List[StepFailure], Dict[str, int]]:
    """Validate raw `(key, json)` failure items: the failures and the unreadable count by run id.

    Never raises. An invalid item is skipped and counted for its run, like a step record. Keys of
    other pipelines or environments, and keys that are not failure keys, are not ours and are ignored.
    """
    failures: List[StepFailure] = []
    unreadable: Dict[str, int] = {}
    for key, value in raw:
        match = _FAILED_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        run_id = match["run"]
        failure = _validate_failure(pipeline, env, run_id, match["step"], int(match["idx"]), value)
        if failure is None:
            unreadable[run_id] = unreadable.get(run_id, 0) + 1
        else:
            failures.append(failure)
    return failures, unreadable


def _validate_metrics(
    pipeline: str, env: str, run_id: str, step: str, index: int, raw: str
) -> Optional[StepMetrics]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("v") != 1:
        return None
    if (data.get("pipeline"), data.get("env"), data.get("run_id")) != (pipeline, env, run_id):
        return None
    if (
        data.get("step") != step
        or data.get("index") != index
        or isinstance(data.get("index"), bool)
    ):
        return None
    entries = data.get("metrics")
    if not isinstance(entries, dict) or len(entries) > MAX_METRICS_PER_STEP:
        return None
    values: Dict[str, MetricNumber] = {}
    for name, value in entries.items():
        if not isinstance(name, str) or not _METRIC_NAME.match(name) or isinstance(value, bool):
            continue
        if not isinstance(value, (int, float)):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        values[name] = value
    return StepMetrics(
        pipeline=pipeline,
        run_id=run_id,
        env=env,
        step=step,
        index=index,
        values=values,
        updated_at=_parse_time(data.get("updated_at")),
    )


def parse_metrics(
    env: str, pipeline: str, raw: Iterable[Tuple[str, str]]
) -> Tuple[List[StepMetrics], Dict[str, int]]:
    """Validate raw `(key, json)` metrics records: the records and the unreadable count by run id.

    Never raises. A record that is not valid as a whole is skipped and counted for its run; inside a
    readable record an entry with a bad name or value is dropped. Keys that are not metrics keys of
    this pipeline and environment are ignored.
    """
    records: List[StepMetrics] = []
    unreadable: Dict[str, int] = {}
    for key, value in raw:
        match = _METRICS_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        run_id = match["run"]
        record = _validate_metrics(pipeline, env, run_id, match["step"], int(match["idx"]), value)
        if record is None:
            unreadable[run_id] = unreadable.get(run_id, 0) + 1
        else:
            records.append(record)
    return records, unreadable


def _int_or(value: object, default: int = 0) -> int:
    """A count >= 0 (never a bool), else `default`: a wrong-typed optional field is treated as absent."""
    return value if isinstance(value, int) and _is_count(value) else default


def _counts(raw: object) -> Optional[MapCounts]:
    if not isinstance(raw, dict):
        return None
    parts = [raw.get(k) for k in ("started", "running", "done", "failed")]
    if not all(_is_count(v) for v in parts):
        return None
    started, running, done, failed = (_int_or(v) for v in parts)
    if started != running + done + failed:
        return None
    return MapCounts(started, running, done, failed)


def _validate_map(
    pipeline: str, env: str, run_id: str, map_name: str, raw: str
) -> Optional[MapAggregate]:
    data = _load_versioned(raw, pipeline, env, run_id)
    if data is None or data.get("map") != map_name:
        return None
    index = data.get("index")
    if not (isinstance(index, int) and not isinstance(index, bool) and index >= 1):
        return None
    started_at = _parse_time(data.get("started_at"))
    counts = _counts(data.get("counts"))
    if started_at is None or counts is None:
        return None
    inner: List[MapInner] = []
    raw_inner = data.get("inner")
    if isinstance(raw_inner, dict):
        if len(raw_inner) > MAX_INNER_STEPS:
            return None
        for name, entry in raw_inner.items():
            if not isinstance(name, str) or not name or not isinstance(entry, dict):
                return None
            numbers = [entry.get(k) for k in ("running", "done", "failed", "in", "out")]
            if not all(_is_count(v) for v in numbers):
                return None
            r, d, f, i, o = (_int_or(v) for v in numbers)
            inner.append(MapInner(name, r, d, f, i, o))
    count = sum_ms = 0
    hist: Dict[int, int] = {}
    slowest: List[Tuple[str, int]] = []
    duration = data.get("duration")
    if isinstance(duration, dict):
        count, sum_ms = _int_or(duration.get("count")), _int_or(duration.get("sum_ms"))
        raw_hist = duration.get("hist", {})
        if not isinstance(raw_hist, dict):
            return None
        for bucket, n in raw_hist.items():
            if not (isinstance(bucket, str) and bucket.isdigit()) or not _is_count(n):
                return None
            hist[int(bucket)] = _int_or(n)
        raw_slowest = duration.get("slowest", [])
        if not isinstance(raw_slowest, list) or len(raw_slowest) > MAX_MAP_SLOWEST_LISTED:
            return None
        for entry in raw_slowest:
            key = entry.get("key") if isinstance(entry, dict) else None
            ms = entry.get("ms") if isinstance(entry, dict) else None
            if not isinstance(key, str) or not _ITEM_NAME.match(key) or not _is_count(ms):
                return None
            slowest.append((key, _int_or(ms)))
    failed_items: List[Tuple[str, str, str]] = []
    raw_failed = data.get("failed_items", [])
    if not isinstance(raw_failed, list) or len(raw_failed) > MAX_MAP_FAILED_LISTED:
        return None
    for entry in raw_failed:
        key = entry.get("key") if isinstance(entry, dict) else None
        step = entry.get("step") if isinstance(entry, dict) else None
        kind = entry.get("error_type") if isinstance(entry, dict) else None
        if not isinstance(key, str) or not _ITEM_NAME.match(key):
            return None
        failed_items.append(
            (
                key,
                step[:MAX_EVENT_STEP] if isinstance(step, str) else "",
                kind[:MAX_ERROR_TYPE] if isinstance(kind, str) else "",
            )
        )
    detail = data.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    return MapAggregate(
        pipeline=pipeline,
        run_id=run_id,
        env=env,
        map=map_name,
        index=index,
        started_at=started_at,
        ended_at=_parse_time(data.get("ended_at")),
        updated_at=_parse_time(data.get("updated_at")),
        counts=counts,
        in_total=_int_or(data.get("in_total")),
        out_total=_int_or(data.get("out_total")),
        lost_items=_int_or(data.get("lost_items")),
        inner=tuple(inner),
        count=count,
        sum_ms=sum_ms,
        hist=hist,
        slowest=tuple(slowest),
        failed_items=tuple(failed_items),
        kept=_int_or(detail.get("kept"), counts.started),
        failed_without_record=_int_or(detail.get("failed_without_record")),
        slow_kept=_int_or(detail.get("slow_kept")),
    )


def _load_versioned(raw: str, pipeline: str, env: str, run_id: str) -> Optional[Dict[str, Any]]:
    """The JSON object of a `v: 1` map or item record that names this pipeline, env and run."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("v") != 1:
        return None
    if (data.get("pipeline"), data.get("env"), data.get("run_id")) != (pipeline, env, run_id):
        return None
    return data


def parse_maps(
    env: str, pipeline: str, raw: Iterable[Tuple[str, str]]
) -> Tuple[List[MapAggregate], Dict[str, int]]:
    """Validate raw `(key, json)` map aggregates: the aggregates and the unreadable count by run id.

    Never raises. An aggregate that is not valid as a whole is skipped and counted for its run. Keys that
    are not map keys of this pipeline and environment are ignored.
    """
    records: List[MapAggregate] = []
    unreadable: Dict[str, int] = {}
    for key, value in raw:
        match = _MAP_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        run_id = match["run"]
        record = _validate_map(pipeline, env, run_id, match["map"], value)
        if record is None:
            unreadable[run_id] = unreadable.get(run_id, 0) + 1
        else:
            records.append(record)
    return records, unreadable


def _item_error(raw: object) -> Optional[ErrorInfo]:
    """An error block of an item: type, message (at most 500), traceback (at most 2048 bytes; a compact
    record has none). None when absent or not a usable error."""
    if not isinstance(raw, dict):
        return None
    kind, message, trace = raw.get("type"), raw.get("message"), raw.get("traceback")
    if not isinstance(kind, str) or not kind:
        return None
    return ErrorInfo(
        type=kind[:MAX_ERROR_TYPE],
        message=message[:MAX_ERROR_MESSAGE] if isinstance(message, str) and message else None,
        traceback=(
            _shorten_traceback(trace, MAX_ITEM_TRACEBACK_BYTES) if isinstance(trace, str) else ""
        ),
    )


def _item_step(raw: object) -> Optional[ItemStepResult]:
    if not isinstance(raw, dict):
        return None
    name, attempt, state = raw.get("step"), raw.get("attempt"), raw.get("state")
    inputs, output = raw.get("inputs", {}), raw.get("output")
    if not isinstance(name, str) or not 0 < len(name) <= MAX_EVENT_STEP:
        return None
    if not (isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1):
        return None
    if state not in ("running", "done", "failed"):
        return None
    if not isinstance(inputs, dict) or not all(_is_count(v) for v in inputs.values()):
        return None
    if output is not None and not _is_count(output):
        return None
    duration = raw.get("duration_ms")
    return ItemStepResult(
        step=name,
        attempt=attempt,
        state=state,
        inputs={str(k): int(v) for k, v in inputs.items()},
        output=output,
        started_at=_parse_time(raw.get("started_at")),
        duration_ms=duration if _is_count(duration) else None,
        error=_item_error(raw.get("error")),
    )


def _item_metrics(raw: object) -> Dict[str, Dict[str, MetricNumber]]:
    """Per inner step, the valid metrics (names matching `^[a-z0-9_]{1,64}$`, finite numbers, at most
    20 per step); invalid entries are dropped."""
    out: Dict[str, Dict[str, MetricNumber]] = {}
    if not isinstance(raw, dict):
        return out
    for step, entries in raw.items():
        if not isinstance(step, str) or not isinstance(entries, dict):
            continue
        values: Dict[str, MetricNumber] = {}
        for name, value in entries.items():
            if len(values) >= MAX_METRICS_PER_STEP:
                break
            if not isinstance(name, str) or not _METRIC_NAME.match(name) or isinstance(value, bool):
                continue
            if not isinstance(value, (int, float)):
                continue
            if isinstance(value, float) and not math.isfinite(value):
                continue
            values[name] = value
        if values:
            out[step] = values
    return out


def _validate_item(
    pipeline: str, env: str, run_id: str, map_name: str, key: str, raw: str
) -> Optional[ItemRecord]:
    data = _load_versioned(raw, pipeline, env, run_id)
    if data is None or data.get("map") != map_name or data.get("key") != key:
        return None
    index, state = data.get("index"), data.get("state")
    if not (isinstance(index, int) and not isinstance(index, bool) and index >= 1):
        return None
    if state not in ("running", "done", "failed"):
        return None
    started = _parse_time(data.get("started_at"))
    raw_steps = data.get("steps", [])
    if started is None or not isinstance(raw_steps, list) or len(raw_steps) > MAX_INNER_STEPS:
        return None
    steps: List[ItemStepResult] = []
    for entry in raw_steps:
        result = _item_step(entry)
        if result is None:
            return None
        steps.append(result)
    duration = data.get("duration_ms")
    return ItemRecord(
        pipeline=pipeline,
        run_id=run_id,
        env=env,
        map=map_name,
        key=key,
        index=index,
        state=state,
        started_at=started,
        finished_at=_parse_time(data.get("finished_at")),
        duration_ms=duration if _is_count(duration) else None,
        steps=tuple(steps),
        metrics=_item_metrics(data.get("metrics")),
        error=_item_error(data.get("error")),
        compact=data.get("compact") is True,
    )


def parse_items(
    env: str, pipeline: str, run_id: str, map_name: str, raw: Iterable[Tuple[str, str]]
) -> Tuple[List[ItemRecord], int]:
    """Validate raw `(key, json)` item records of one map step of one run: the items and how many were
    unreadable. Never raises. Keys of other runs, maps, pipelines or environments are ignored."""
    items: List[ItemRecord] = []
    unreadable = 0
    for key, value in raw:
        match = _ITEM_KEY.match(key)
        if (
            not match
            or match["env"] != env
            or match["pipeline"] != pipeline
            or match["run"] != run_id
            or match["map"] != map_name
        ):
            continue
        item = _validate_item(pipeline, env, run_id, map_name, match["key"], value)
        if item is None:
            unreadable += 1
        else:
            items.append(item)
    return items, unreadable


def parse_item(
    env: str, pipeline: str, run_id: str, map_name: str, key: str, raw: str
) -> Optional[ItemRecord]:
    """One item record read by its key, or None when it is absent or not valid."""
    return _validate_item(pipeline, env, run_id, map_name, key, raw)


def _event_fields(raw: object) -> Optional[Dict[str, FieldValue]]:
    """The valid entries of an event's `fields` (at most 10); None when there are none."""
    if not isinstance(raw, dict):
        return None
    out: Dict[str, FieldValue] = {}
    for name, value in raw.items():
        if len(out) >= MAX_EVENT_FIELDS:
            break
        if not isinstance(name, str) or not _FIELD_NAME.match(name):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                continue
            out[name] = value
        elif isinstance(value, str) and len(value) <= MAX_EVENT_TEXT:
            out[name] = value
    return out or None


def _validate_event(
    pipeline: str, env: str, run_id: str, level: str, raw: str
) -> Optional[RunEvent]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("level") != level:
        return None
    n = data.get("n")
    ts = _parse_time(data.get("ts"))
    if not (isinstance(n, int) and not isinstance(n, bool) and n >= 1) or ts is None:
        return None
    step = data.get("step")
    message = data.get("message")
    item = data.get("item")
    return RunEvent(
        run_id=run_id,
        level=level,
        n=n,
        ts=ts,
        step=step if isinstance(step, str) and 0 < len(step) <= MAX_EVENT_STEP else None,
        message=message[:MAX_EVENT_MESSAGE] if isinstance(message, str) and message else None,
        fields=_event_fields(data.get("fields")),
        item=item if isinstance(item, str) and _ITEM_NAME.match(item) else None,
    )


def parse_events(
    env: str, pipeline: str, raw: Iterable[Tuple[str, Sequence[str]]]
) -> Tuple[List[RunEvent], Dict[str, int]]:
    """Validate `(key, [json, ...])` pairs of event lists: the events and the unreadable count by run.

    Never raises. A damaged element is skipped and counted for its run; keys of other pipelines or
    environments and keys that are not event lists are not ours and are ignored.
    """
    events: List[RunEvent] = []
    unreadable: Dict[str, int] = {}
    for key, elements in raw:
        match = _EVENTS_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        run_id = match["run"]
        for element in elements:
            event = _validate_event(pipeline, env, run_id, match["level"], element)
            if event is None:
                unreadable[run_id] = unreadable.get(run_id, 0) + 1
            else:
                events.append(event)
    return events, unreadable


def event_list_key(pipeline: str, env: str, run_id: str, level: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:events:{level}"


def _validate_marker(
    pipeline: str, env: str, run_id: str, step: str, raw: str
) -> Optional[StartMarker]:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    index = data.get("index")
    started = _parse_time(data.get("started_at"))
    if data.get("run_id") != run_id or data.get("env") != env or data.get("step") != step:
        return None
    if data.get("pipeline") != pipeline or started is None:
        return None
    if not (isinstance(index, int) and not isinstance(index, bool) and index >= 1):
        return None
    return StartMarker(
        pipeline=pipeline, run_id=run_id, env=env, step=step, index=index, started_at=started
    )


def parse_markers(env: str, pipeline: str, raw: Iterable[Tuple[str, str]]) -> List[StartMarker]:
    """Validate raw `(key, json)` start markers. Never raises; invalid markers are dropped.

    Markers are not audit records, so an invalid one is never counted as unreadable.
    """
    out: List[StartMarker] = []
    for key, value in raw:
        match = _MARKER_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        marker = _validate_marker(pipeline, env, match["run"], match["step"], value)
        if marker is not None:
            out.append(marker)
    return out


def _load(raw: str, pipeline: str, env: str, run_id: str) -> Optional[Dict[str, object]]:
    """The JSON object of an alive or died item when it names this pipeline, env and run."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("pipeline") != pipeline or data.get("env") != env or data.get("run_id") != run_id:
        return None
    return data


def parse_alive(env: str, pipeline: str, raw: Iterable[Tuple[str, str]]) -> Dict[str, AliveSignal]:
    """Map run id -> its latest heartbeat. Never raises.

    An invalid item is dropped and never counted as unreadable: the run is then treated like a run
    from a pipeline that sends no heartbeat.
    """
    out: Dict[str, AliveSignal] = {}
    for key, value in raw:
        match = _ALIVE_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        data = _load(value, pipeline, env, match["run"])
        beat = _parse_time(data.get("beat_at")) if data else None
        if beat is not None:
            out[match["run"]] = AliveSignal(pipeline, match["run"], env, beat)
    return out


def parse_died(env: str, pipeline: str, raw: Iterable[Tuple[str, str]]) -> Dict[str, DiedVerdict]:
    """Map run id -> the stored died verdict. Never raises; an invalid verdict is dropped."""
    out: Dict[str, DiedVerdict] = {}
    for key, value in raw:
        match = _DIED_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        data = _load(value, pipeline, env, match["run"])
        judged = _parse_time(data.get("judged_at")) if data else None
        seen = _parse_time(data.get("last_seen_at")) if data else None
        if judged is not None and seen is not None:
            out[match["run"]] = DiedVerdict(pipeline, match["run"], env, judged, seen)
    return out


def parse_flows(
    env: str, pipeline: str, raw: Iterable[Tuple[str, str]]
) -> Dict[str, Tuple[str, Optional[Flow]]]:
    """Map run id -> ("ok", Flow), ("unsupported", None) or ("invalid", None). Never raises."""
    out: Dict[str, Tuple[str, Optional[Flow]]] = {}
    for key, value in raw:
        match = _FLOW_KEY.match(key)
        if not match or match["env"] != env or match["pipeline"] != pipeline:
            continue
        out[match["run"]] = parse_flow(pipeline, env, match["run"], value)
    return out


def pipeline_of_key(env: str, key: str) -> Optional[str]:
    """The pipeline segment of any `waypoint:` key of `env`, else None (old layouts are ignored)."""
    match = _ANY_KEY.match(key)
    if not match or match["env"] != env:
        return None
    return match["pipeline"]
