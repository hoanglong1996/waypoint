from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


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
    finished_at: UTC ISO-8601.
    """

    pipeline: str
    run_id: str
    env: str
    step: str
    index: int
    inputs: Dict[str, int]
    output: Optional[int]
    finished_at: datetime


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
class ParseResult:
    records: List[StepRecord]
    unreadable_by_run: Dict[str, int] = field(default_factory=dict)
    unreadable_unattributed: int = 0

    @property
    def unreadable_total(self) -> int:
        return sum(self.unreadable_by_run.values()) + self.unreadable_unattributed
