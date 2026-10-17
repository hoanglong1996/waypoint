"""Declaration of a pipeline: its name and its steps with their hand-offs."""

import math
import re
from dataclasses import dataclass
from typing import Optional, Set, Tuple

from waypoint_etl.keys import (
    MAX_METRIC_LABEL,
    MAX_METRIC_NAME,
    MAX_METRIC_UNIT,
    MAX_METRICS_PER_STEP,
)

_PIPELINE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_STEP_NAME = re.compile(r"^[a-z0-9_]{1,64}$")
_METRIC_NAME = re.compile(rf"^[a-z0-9_]{{1,{MAX_METRIC_NAME}}}$")
MAX_STEPS = 100
MAX_PIPELINE_LABEL = 60
MAX_STEP_LABEL = 40


@dataclass(frozen=True)
class GroupSpec:
    key: str
    label: str


@dataclass(frozen=True)
class Metric:
    """A declared metric of a step: optional label, unit and warning limits (specs/013)."""

    name: str
    label: Optional[str] = None
    unit: Optional[str] = None
    warn_above: Optional[float] = None
    warn_below: Optional[float] = None


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
    metrics: Tuple[Metric, ...] = ()


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    steps: Tuple[StepSpec, ...]
    label: Optional[str] = None
    groups: Tuple[GroupSpec, ...] = ()


def _validate_metrics(step: StepSpec) -> None:
    if len(step.metrics) > MAX_METRICS_PER_STEP:
        raise ValueError(f"step {step.name!r} declares more than {MAX_METRICS_PER_STEP} metrics")
    names: Set[str] = set()
    for metric in step.metrics:
        where = f"metric {metric.name!r} of step {step.name!r}"
        if not isinstance(metric.name, str) or not _METRIC_NAME.match(metric.name):
            raise ValueError(f"{where} must match [a-z0-9_]+ (max {MAX_METRIC_NAME})")
        if metric.name in names:
            raise ValueError(f"duplicate {where}")
        names.add(metric.name)
        for text, limit, what in (
            (metric.label, MAX_METRIC_LABEL, "label"),
            (metric.unit, MAX_METRIC_UNIT, "unit"),
        ):
            if text is not None and (not isinstance(text, str) or len(text) > limit):
                raise ValueError(f"{what} of {where} must be text of at most {limit} chars")
        for limit_value in (metric.warn_above, metric.warn_below):
            if limit_value is not None and (
                isinstance(limit_value, bool)
                or not isinstance(limit_value, (int, float))
                or not math.isfinite(limit_value)
            ):
                raise ValueError(f"a warning limit of {where} must be a finite number")
        if (
            metric.warn_above is not None
            and metric.warn_below is not None
            and metric.warn_below > metric.warn_above
        ):
            raise ValueError(f"warn_below of {where} is above its warn_above")


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
        _validate_metrics(step)
        seen.add(step.name)
