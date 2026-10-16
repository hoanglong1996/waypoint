"""The one active auditor of this process, set by ``init`` and read by ``audited_step``."""

from typing import Optional

from waypoint_etl.auditor import StepAuditor
from waypoint_etl.keys import HEARTBEAT_SECONDS
from waypoint_etl.spec import PipelineSpec, validate_spec
from waypoint_etl.stores import NoopStepAuditStore, RedisStepAuditStore, StepAuditStore

_active: Optional[StepAuditor] = None


def get_active() -> Optional[StepAuditor]:
    return _active


def set_active(auditor: Optional[StepAuditor]) -> None:
    global _active
    _active = auditor


def clear() -> None:
    """Stop the active auditor's heartbeat and leave the process unaudited."""
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
) -> bool:
    """Configure auditing once, from the pipeline's entry point.

    Returns True when auditing is active. On an invalid spec or a missing/invalid Redis URL it
    prints a warning, leaves the pipeline unaudited and returns False; it never raises.
    ``store`` replaces the Redis store (tests, other back ends). While the run is alive an
    "alive" item is refreshed every ``heartbeat_seconds`` so the monitor can tell a dead process
    from a slow one; ``None`` or 0 turns that off.
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
    auditor = StepAuditor(store, pipeline, env, ttl_days * 86400, run_id)
    auditor.start()
    set_active(auditor)
    auditor.start_heartbeat(heartbeat_seconds)
    return True


__all__ = ["NoopStepAuditStore", "clear", "get_active", "init", "set_active"]
