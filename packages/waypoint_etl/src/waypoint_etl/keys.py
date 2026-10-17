"""Redis key layout. Contract: specs/007-rename-to-waypoint/contracts/redis-keys.md"""

ROOT = "waypoint"
FLOW_VERSION = 1
START_MARKER_TTL_SECONDS = 86400
HEARTBEAT_SECONDS = 15
# Most events kept per run and level; the oldest of a level is dropped first (specs/012 R6).
EVENT_CAPS = {"info": 500, "warning": 200, "error": 200}
# Step metrics (specs/013): most metrics per step attempt, name/label/unit lengths, record version, and
# how often changed metrics are written.
MAX_METRICS_PER_STEP = 20
MAX_METRIC_NAME = 64
MAX_METRIC_LABEL = 40
MAX_METRIC_UNIT = 16
METRICS_VERSION = 1
METRIC_FLUSH_SECONDS = 1.0


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


def metrics_key(pipeline: str, env: str, run_id: str, index: int, step: str) -> str:
    """The record of one step attempt's metrics; ``index`` is the attempt's index, as in ``step_key``."""
    return f"{ROOT}:{pipeline}:{env}:{run_id}:metrics:{index:02d}-{step}"
