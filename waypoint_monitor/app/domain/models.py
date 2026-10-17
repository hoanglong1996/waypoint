from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union


@dataclass(frozen=True)
class GroupDef:
    key: str
    label: str


@dataclass(frozen=True)
class FlowInput:
    name: str
    source: str
    # the producer is not a step of the flow: drawn as a flagged stub, not as an edge
    dangling: bool = False


@dataclass(frozen=True)
class MetricDecl:
    """A metric a step declares (specs/013): optional label (at most 40 characters), unit (at most 16)
    and warning limits. Names match `^[a-z0-9_]{1,64}$`."""

    name: str
    label: Optional[str] = None
    unit: Optional[str] = None
    warn_above: Optional[float] = None
    warn_below: Optional[float] = None


@dataclass(frozen=True)
class MapDecl:
    """A map step's declaration (specs/014): the optional top-level step that supplies its items, the
    informational concurrency limit (int >= 1) and the item flow, a linear list of at most 20 inner
    steps. Inner steps are never top-level steps of the flow."""

    over: Optional[str] = None
    max_concurrency: Optional[int] = None
    steps: Tuple["FlowStep", ...] = ()


@dataclass(frozen=True)
class FlowStep:
    name: str
    label: Optional[str]
    group: Optional[str]
    # in display order
    inputs: Tuple[FlowInput, ...]
    returns_nothing: bool = False
    col: Optional[float] = None
    row: Optional[float] = None
    metrics: Tuple[MetricDecl, ...] = ()
    map: Optional[MapDecl] = None


@dataclass(frozen=True)
class Flow:
    """A run's own flow description as stored by the pipeline (contracts/redis-keys.md)."""

    pipeline: str
    label: Optional[str]
    groups: Tuple[GroupDef, ...]
    steps: Tuple[FlowStep, ...]
    # parts of the stored description that were dropped or flagged
    problems: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StepRecord:
    """One validated step record.

    pipeline, run_id (`YYYYMMDDTHHMMSSZ`) and env must equal the ones in the key.
    step: non-empty (a step outside the run's flow is shown as unplanned). index: int >= 1.
    inputs: map string -> int >= 0 (values may not be null). output: int >= 0 or null.
    finished_at: UTC ISO-8601. started_at (UTC ISO-8601) and duration_ms (int >= 0) are optional,
    written by library 0.4.0; a value of the wrong type is treated as absent.
    """

    pipeline: str
    run_id: str
    env: str
    step: str
    index: int
    inputs: Dict[str, int]
    output: Optional[int]
    finished_at: datetime
    started_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


@dataclass(frozen=True)
class StartMarker:
    """A step's start announcement: it began at `started_at` (UTC); `index` is int >= 1."""

    pipeline: str
    run_id: str
    env: str
    step: str
    index: int
    started_at: datetime


@dataclass(frozen=True)
class AliveSignal:
    """A run's latest heartbeat: its process was alive at `beat_at` (UTC)."""

    pipeline: str
    run_id: str
    env: str
    beat_at: datetime


@dataclass(frozen=True)
class DiedVerdict:
    """The stored judgement that a run died: judged at `judged_at`, last seen alive at `last_seen_at`."""

    pipeline: str
    run_id: str
    env: str
    judged_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class ErrorInfo:
    """What a failure item says went wrong: the error `type` (at most 200 characters), the `message`
    (at most 500 characters, None when not stored) and the frames-only `traceback` (at most 8192
    UTF-8 bytes, last frames kept)."""

    type: str
    message: Optional[str]
    traceback: str


@dataclass(frozen=True)
class StepFailure:
    """One validated failure item: attempt `index` (int >= 1) of `step` began at `started_at` and
    raised at `failed_at` (both UTC). pipeline, run_id and env must equal the ones in the key."""

    pipeline: str
    run_id: str
    env: str
    step: str
    index: int
    started_at: datetime
    failed_at: datetime
    error: ErrorInfo


FieldValue = Union[int, float, str]


@dataclass(frozen=True)
class RunEvent:
    """One validated author-sent event (specs/012 data-model.md "Run event").

    `n` is the sender's sequence number (int >= 1), `ts` a UTC time with milliseconds, `level` one of
    info, warning, error and equal to the list the event was stored in. `step` and `message` are None
    when absent (message is also None when the author turned message text off, or it was not a string);
    `message` is at most 300 characters. `fields` holds at most 10 entries: names matching
    `^[A-Za-z0-9_.-]{1,40}$`, values finite numbers or strings of at most 100 characters.
    """

    run_id: str
    level: str
    n: int
    ts: datetime
    step: Optional[str]
    message: Optional[str]
    fields: Optional[Dict[str, FieldValue]]
    # the item key an event inside a map step item carries (specs/014); None otherwise
    item: Optional[str] = None


MetricNumber = Union[int, float]


@dataclass(frozen=True)
class StepMetrics:
    """One validated metrics record (specs/013 data-model.md): the metrics of attempt `index` (int >= 1)
    of `step`. `values` has at most 20 entries: names matching `^[a-z0-9_]{1,64}$`, values finite numbers
    (never bool). `updated_at` is None when absent or of the wrong type."""

    pipeline: str
    run_id: str
    env: str
    step: str
    index: int
    values: Dict[str, MetricNumber]
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class MapCounts:
    """Items per state over **all** items of a map step: ints >= 0 with
    `started == running + done + failed`."""

    started: int
    running: int
    done: int
    failed: int


@dataclass(frozen=True)
class MapInner:
    """Counts of one inner step across all items: items running, done and failed in it, and the sums of
    its input and output counts (ints >= 0)."""

    name: str
    running: int
    done: int
    failed: int
    inputs_total: int
    output_total: int


@dataclass(frozen=True)
class MapAggregate:
    """One validated map aggregate (specs/014 data-model.md "Aggregate"): the state of a map step of a
    run. `index` is the attempt index of the map block (int >= 1); `ended_at` is None while the block
    is open. `inner` has at most 20 entries; `hist` maps a log-scale bucket (int >= 0) to a count;
    `slowest` holds at most 5 `(key, ms)` pairs; `failed_items` at most 20 `(key, step, error_type)`.
    """

    pipeline: str
    run_id: str
    env: str
    map: str
    index: int
    started_at: datetime
    ended_at: Optional[datetime]
    updated_at: Optional[datetime]
    counts: MapCounts
    in_total: int = 0
    out_total: int = 0
    lost_items: int = 0
    inner: Tuple[MapInner, ...] = ()
    count: int = 0
    sum_ms: int = 0
    hist: Dict[int, int] = field(default_factory=dict)
    slowest: Tuple[Tuple[str, int], ...] = ()
    failed_items: Tuple[Tuple[str, str, str], ...] = ()
    kept: int = 0
    failed_without_record: int = 0
    slow_kept: int = 0


@dataclass(frozen=True)
class ItemStepResult:
    """The result of one inner step for one item: `attempt` int >= 1, `state` one of running, done,
    failed, `inputs` map string -> int >= 0, `output` int >= 0 or None, `duration_ms` int >= 0 or None,
    `error` set for a failed step (a compact record has an empty traceback)."""

    step: str
    attempt: int
    state: str
    inputs: Dict[str, int]
    output: Optional[int]
    started_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[ErrorInfo] = None


@dataclass(frozen=True)
class ItemRecord:
    """One validated item record (specs/014 data-model.md "Item"). `key` matches
    `^[A-Za-z0-9_.-]{1,64}$`, `index` is the arrival number (int >= 1), `state` one of running, done,
    failed. `steps` has at most 20 results in the order the inner steps began; `metrics` maps inner
    step -> metric name -> finite number; `error` is an item-level error; `compact` is true for a record
    kept beyond the detail limit."""

    pipeline: str
    run_id: str
    env: str
    map: str
    key: str
    index: int
    state: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    steps: Tuple[ItemStepResult, ...] = ()
    metrics: Dict[str, Dict[str, MetricNumber]] = field(default_factory=dict)
    error: Optional[ErrorInfo] = None
    compact: bool = False


@dataclass(frozen=True)
class ParseResult:
    records: List[StepRecord]
    unreadable_by_run: Dict[str, int] = field(default_factory=dict)
    unreadable_unattributed: int = 0

    @property
    def unreadable_total(self) -> int:
        return sum(self.unreadable_by_run.values()) + self.unreadable_unattributed
