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
# Map steps (specs/014): record version, how many items keep a full record, how many further failed items
# keep a compact one, how many of the slowest later items are kept, key and item flow limits, how often changed
# records are written, the trace budget of a full item record, the compact message length, how many failures
# and slowest items the aggregate lists, the histogram bucket ratio, and the TTL that retires a displaced record.
MAP_VERSION = 1
MAP_DETAIL_LIMIT = 1000
MAP_EXTRA_FAILED_LIMIT = 1000
MAP_SLOWEST_KEPT = 50
MAX_ITEM_KEY = 64
MAX_INNER_STEPS = 20
MAP_FLUSH_SECONDS = 1.0
ITEM_TRACE_BYTES = 2048
COMPACT_MESSAGE = 200
MAP_FAILED_LISTED = 20
MAP_SLOWEST_LISTED = 5
HIST_RATIO = 1.1
EVICT_TTL_SECONDS = 1


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


def map_key(pipeline: str, env: str, run_id: str, map_name: str) -> str:
    """The aggregate of one map step of a run (specs/014 contracts/redis-keys.md)."""
    return f"{ROOT}:{pipeline}:{env}:{run_id}:map:{map_name}"


def item_key(pipeline: str, env: str, run_id: str, map_name: str, key: str) -> str:
    """The record of one detailed item of a map step; ``key`` has no ``:``."""
    return f"{ROOT}:{pipeline}:{env}:{run_id}:item:{map_name}:{key}"
