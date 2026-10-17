"""The one active auditor of this process, set by ``init`` and read by ``audited_step``."""

import atexit
from typing import Callable, Optional, Union

from waypoint_etl.auditor import StepAuditor
from waypoint_etl.keys import HEARTBEAT_SECONDS
from waypoint_etl.scopes import ItemScope, MapScope
from waypoint_etl.spec import PipelineSpec, validate_spec
from waypoint_etl.stores import NoopStepAuditStore, RedisStepAuditStore, StepAuditStore

_active: Optional[StepAuditor] = None
_exit_hook = False


def get_active() -> Optional[StepAuditor]:
    return _active


def set_active(auditor: Optional[StepAuditor]) -> None:
    global _active
    _active = auditor


def _flush_at_exit() -> None:
    """Deliver queued events when the process ends (waits at most 2 seconds)."""
    if _active is not None:
        _active.flush_events(2.0)


def clear() -> None:
    """Stop the active auditor's heartbeat, deliver its queued events and leave the process unaudited."""
    if _active is not None:
        _active.stop()
    set_active(None)


def init(
    *,
    pipeline: PipelineSpec,
    redis_url: Optional[str],
    env: str,
    ttl_days: int = 30,
    run_id: Optional[str] = None,
    store: Optional[StepAuditStore] = None,
    heartbeat_seconds: Optional[float] = HEARTBEAT_SECONDS,
    capture_error_message: bool = True,
    redact: Optional[Callable[[str], str]] = None,
) -> bool:
    """Configure auditing once, from the pipeline's entry point.

    Returns True when auditing is active. On an invalid spec or a missing/invalid Redis URL it
    prints a warning, leaves the pipeline unaudited and returns False; it never raises.
    ``store`` replaces the Redis store (tests, other back ends). While the run is alive an
    "alive" item is refreshed every ``heartbeat_seconds`` so the monitor can tell a dead process
    from a slow one; ``None`` or 0 turns that off.

    ``capture_error_message=False`` and ``redact`` cover all free text the library stores: failure
    messages and event messages and text values.

    When a step raises, a failure item with the error type, a shortened message and a shortened
    stack trace (never variable values) is written and the exception is re-raised unchanged.
    ``capture_error_message=False`` leaves the message out; ``redact`` (``str -> str``) cleans every
    message before it is shortened and stored (a ``redact`` that raises drops the message).
    """
    if _active is not None:
        print("Warning: waypoint_etl.init called again, replacing the previous configuration")
    clear()
    try:
        validate_spec(pipeline)
    except ValueError as exc:
        print(f"Warning: Waypoint disabled, invalid pipeline spec: {exc}")
        return False
    if store is None:
        if not redis_url:
            print("Warning: Waypoint disabled, no Redis URL configured")
            return False
        try:
            store = RedisStepAuditStore(redis_url)
        except Exception as exc:
            print(f"Warning: Waypoint disabled, invalid Redis URL: {exc}")
            return False
    if redact is not None and not callable(redact):
        print("Warning: Waypoint ignores redact: it must be a function taking and returning a str")
        redact = None
    auditor = StepAuditor(
        store,
        pipeline,
        env,
        ttl_days * 86400,
        run_id,
        capture_error_message=bool(capture_error_message),
        redact=redact,
    )
    auditor.start()
    set_active(auditor)
    auditor.start_heartbeat(heartbeat_seconds)
    global _exit_hook
    if not _exit_hook:
        _exit_hook = True
        atexit.register(_flush_at_exit)
    return True


def log(message: str, *, level: str = "info", step: Optional[str] = None, **fields: object) -> None:
    """Send an event: a short message with a level, an optional step and a few small named values.

    ``waypoint_etl.log("Loaded batch 3", step="load", rows=1200)``. Inside a running step the event
    belongs to that step unless ``step`` says otherwise. Does nothing, and never raises or waits on
    the network, before ``init``, after a failed ``init`` or when Redis is unreachable.
    """
    try:
        active = _active
        if active is not None:
            active.send_event(message, level, step, fields)
    except Exception:
        return


def metric(
    name: str, value: Union[int, float], *, step: Optional[str] = None, mode: str = "set"
) -> None:
    """Record a named number on a step: ``waypoint_etl.metric("rejected", 42, mode="add")``.

    ``mode`` is ``"set"`` (replace, the default), ``"add"`` (accumulate) or ``"max"`` (keep the largest).
    Inside a running step ``step`` may be left out. Only finite numbers are accepted; a bad name, value
    or mode, or a 21st name on one step, is dropped with a warning. Does nothing, and never raises or
    waits on the network, before ``init``, after a failed ``init`` or when Redis is unreachable.
    """
    try:
        active = _active
        if active is not None:
            active.record_metric(name, value, step, mode)
    except Exception:
        return


def map_step(name: str) -> MapScope:
    """The block around a whole loop: ``with waypoint_etl.map_step("accounts"): ...``.

    ``name`` is a ``MapStepSpec`` of the pipeline. Entering writes the step's ordinary start marker; leaving
    normally writes its finish record, leaving with an exception writes its failure item. Does nothing, and
    never raises or waits on the network, before ``init``, after a failed ``init``, for a name that is not a
    map step or when Redis is unreachable. Also usable as ``async with``.
    """
    return MapScope(name)


def item(key: str, *, map: Optional[str] = None) -> ItemScope:
    """One pass of the item flow: ``with waypoint_etl.item(account_id): ...``.

    ``key`` is an id or an index, never data content: other characters than ``[A-Za-z0-9_.-]`` become ``_``
    and it is cut to 64. ``map`` names the map step when it cannot be told from the context (it is found
    from the enclosing ``map_step`` or the one open block, which is what a worker thread needs). Steps,
    events and metrics recorded inside belong to the item. A key that already started in this map step is a
    duplicate: its pass is ignored. Never suppresses an exception, never raises, never waits on the network.
    """
    return ItemScope(key, map)


def warn(message: str, *, step: Optional[str] = None, **fields: object) -> None:
    """``log`` at level ``warning``."""
    log(message, level="warning", step=step, **fields)


def error(message: str, *, step: Optional[str] = None, **fields: object) -> None:
    """``log`` at level ``error``."""
    log(message, level="error", step=step, **fields)


__all__ = [
    "NoopStepAuditStore",
    "clear",
    "error",
    "get_active",
    "init",
    "item",
    "log",
    "map_step",
    "metric",
    "set_active",
    "warn",
]
