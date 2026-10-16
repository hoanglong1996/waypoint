"""Declaration of a pipeline: its name and its steps with their hand-offs."""

import re
from dataclasses import dataclass
from typing import Optional, Set, Tuple

_PIPELINE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_STEP_NAME = re.compile(r"^[a-z0-9_]{1,64}$")
MAX_STEPS = 100
MAX_PIPELINE_LABEL = 60
MAX_STEP_LABEL = 40


@dataclass(frozen=True)
class GroupSpec:
    key: str
    label: str


@dataclass(frozen=True)
class StepSpec:
    name: str
    # (input name, name of the producing step); the producer must be declared earlier
    inputs: Tuple[Tuple[str, str], ...] = ()
    label: Optional[str] = None
    group: Optional[str] = None
    returns_nothing: bool = False
    col: Optional[float] = None
    row: Optional[float] = None


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    steps: Tuple[StepSpec, ...]
    label: Optional[str] = None
    groups: Tuple[GroupSpec, ...] = ()


def validate_spec(spec: PipelineSpec) -> None:
    """Raise ValueError naming the first problem."""
    if not _PIPELINE_NAME.match(spec.name):
        raise ValueError(f"pipeline name {spec.name!r} must match [a-z0-9][a-z0-9_-]{{0,39}}")
    if spec.label is not None and len(spec.label) > MAX_PIPELINE_LABEL:
        raise ValueError(f"pipeline label longer than {MAX_PIPELINE_LABEL} chars")
    if not 1 <= len(spec.steps) <= MAX_STEPS:
        raise ValueError(f"a pipeline needs between 1 and {MAX_STEPS} steps")
    groups = {g.key for g in spec.groups}
    seen: Set[str] = set()
    for step in spec.steps:
        if not _STEP_NAME.match(step.name):
            raise ValueError(f"step name {step.name!r} must match [a-z0-9_]+ (max 64)")
        if step.name in seen:
            raise ValueError(f"duplicate step {step.name!r}")
        if step.label is not None and len(step.label) > MAX_STEP_LABEL:
            raise ValueError(f"label of step {step.name!r} longer than {MAX_STEP_LABEL} chars")
        if step.group is not None and step.group not in groups:
            raise ValueError(f"step {step.name!r} uses undeclared group {step.group!r}")
        for _, producer in step.inputs:
            if producer not in seen:
                raise ValueError(
                    f"input of step {step.name!r} comes from {producer!r}, "
                    "which is not an earlier step"
                )
        for hint in (step.col, step.row):
            if hint is not None and hint < 0:
                raise ValueError(f"layout hint of step {step.name!r} must be >= 0")
        seen.add(step.name)
