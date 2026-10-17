"""Helpers for a pipeline's own tests."""

from typing import List, Set

from waypoint_etl.decorator import TAG
from waypoint_etl.spec import MapStepSpec, PipelineSpec


def audited_step_names(*objects: object) -> List[str]:
    """Names of every ``@audited_step`` method found on the given classes or instances."""
    found: List[str] = []
    for obj in objects:
        for attr in dir(obj):
            name = getattr(getattr(obj, attr, None), TAG, None)
            if isinstance(name, str):
                found.append(name)
    return found


def assert_spec_matches(spec: PipelineSpec, *objects: object) -> None:
    """Fail if a decorated step is missing from the spec or a spec step has no decorated function."""
    decorated: Set[str] = set(audited_step_names(*objects))
    declared = {s.name for s in spec.steps}
    for s in spec.steps:
        if isinstance(s, MapStepSpec):
            declared |= {inner.name for inner in s.steps}
    problems = []
    if decorated - declared:
        problems.append(f"decorated but not in the spec: {sorted(decorated - declared)}")
    if declared - decorated:
        problems.append(f"in the spec but not decorated: {sorted(declared - decorated)}")
    if problems:
        raise AssertionError("; ".join(problems))
