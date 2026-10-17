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
class FlowStep:
    name: str
    label: Optional[str]
    group: Optional[str]
    # in display order
    inputs: Tuple[FlowInput, ...]
    returns_nothing: bool = False
    col: Optional[float] = None
    row: Optional[float] = None


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


@dataclass(frozen=True)
class ParseResult:
    records: List[StepRecord]
    unreadable_by_run: Dict[str, int] = field(default_factory=dict)
    unreadable_unattributed: int = 0

    @property
    def unreadable_total(self) -> int:
        return sum(self.unreadable_by_run.values()) + self.unreadable_unattributed
