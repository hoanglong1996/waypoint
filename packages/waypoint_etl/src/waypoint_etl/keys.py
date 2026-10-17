"""Redis key layout. Contract: specs/007-rename-to-waypoint/contracts/redis-keys.md"""

ROOT = "waypoint"
FLOW_VERSION = 1
START_MARKER_TTL_SECONDS = 86400
HEARTBEAT_SECONDS = 15
# Most events kept per run and level; the oldest of a level is dropped first (specs/012 R6).
EVENT_CAPS = {"info": 500, "warning": 200, "error": 200}


def flow_key(pipeline: str, env: str, run_id: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:flow"


def step_key(pipeline: str, env: str, run_id: str, index: int, step: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:step:{index:02d}-{step}"


def marker_key(pipeline: str, env: str, run_id: str, index: int, step: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:running:{index:02d}-{step}"


def alive_key(pipeline: str, env: str, run_id: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:alive"


def failed_key(pipeline: str, env: str, run_id: str, index: int, step: str) -> str:
    return f"{ROOT}:{pipeline}:{env}:{run_id}:failed:{index:02d}-{step}"


def events_key(pipeline: str, env: str, run_id: str, level: str) -> str:
    """The list of a run's author-sent events of one level (``info``, ``warning`` or ``error``)."""
    if level not in EVENT_CAPS:
        raise ValueError(f"unknown event level: {level}")
    return f"{ROOT}:{pipeline}:{env}:{run_id}:events:{level}"
