import json
import math
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.domain.flow import parse_flow
from app.domain.models import (
    AliveSignal,
    DiedVerdict,
    ErrorInfo,
    FieldValue,
    Flow,
    ParseResult,
    RunEvent,
    StartMarker,
    StepFailure,
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


def _shorten_traceback(text: str) -> str:
    """At most 8192 UTF-8 bytes, keeping the last frames (a longer one was not written by the library)."""
    raw = text.encode("utf-8")
    if len(raw) <= MAX_TRACEBACK_BYTES:
        return text
    room = MAX_TRACEBACK_BYTES - len(_OMITTED.encode("utf-8"))
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
    return RunEvent(
        run_id=run_id,
        level=level,
        n=n,
        ts=ts,
        step=step if isinstance(step, str) and 0 < len(step) <= MAX_EVENT_STEP else None,
        message=message[:MAX_EVENT_MESSAGE] if isinstance(message, str) and message else None,
        fields=_event_fields(data.get("fields")),
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
