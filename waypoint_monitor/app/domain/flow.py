"""Parse and validate a stored flow description. Never raises; bad parts are dropped and reported."""

import json
import math
import re
from typing import Dict, List, Optional, Set, Tuple

from app.domain.models import Flow, FlowInput, FlowStep, GroupDef, MetricDecl

SUPPORTED_VERSION = 1
MAX_STEPS = 100
MAX_PIPELINE_LABEL = 60
MAX_STEP_LABEL = 40
MAX_METRIC_LABEL = 40
MAX_METRIC_UNIT = 16
MAX_METRICS_PER_STEP = 20
_METRIC_NAME = re.compile(r"^[a-z0-9_]{1,64}$")
_STEP_NAME = re.compile(r"^[a-z0-9_]{1,64}$")
_GROUP_KEY = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _label(value: object, limit: int) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:limit]


def _hint(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def _limit(value: object) -> Optional[float]:
    """A warning limit: a finite number that is not a bool, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _metric_decls(step: str, raw: object, problems: List[str]) -> Tuple[MetricDecl, ...]:
    """The valid metric declarations of a step; each bad one is dropped and reported."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        problems.append(f"the metric declarations of '{step}' were malformed and dropped")
        return ()
    out: List[MetricDecl] = []
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        bad = not isinstance(name, str) or not _METRIC_NAME.match(name)
        bad = bad or any(name == d.name for d in out) or len(out) >= MAX_METRICS_PER_STEP
        limits = {k: item.get(k) for k in ("warn_above", "warn_below")} if not bad else {}
        bad = bad or any(v is not None and _limit(v) is None for v in limits.values())
        if bad:
            problems.append(f"a metric declaration of '{step}' was dropped")
            continue
        out.append(
            MetricDecl(
                name=str(name),
                label=_label(item.get("label"), MAX_METRIC_LABEL),
                unit=_label(item.get("unit"), MAX_METRIC_UNIT),
                warn_above=_limit(limits["warn_above"]),
                warn_below=_limit(limits["warn_below"]),
            )
        )
    return tuple(out)


def _drop_cycles(steps: List[FlowStep], problems: List[str]) -> List[FlowStep]:
    """Remove the edges that close a cycle (depth-first, in declared order)."""
    by_name = {s.name: s for s in steps}
    state: Dict[str, int] = {}  # 1 = on the current path, 2 = done
    dropped: Set[Tuple[str, str, str]] = set()  # (consumer, input name, producer)

    def visit(name: str) -> None:
        state[name] = 1
        for inp in by_name[name].inputs:
            if inp.dangling:
                continue
            if state.get(inp.source) == 1:
                dropped.add((name, inp.name, inp.source))
                problems.append(
                    f"cycle: input '{inp.name}' of '{name}' from '{inp.source}' ignored"
                )
            elif inp.source not in state:
                visit(inp.source)
        state[name] = 2

    for step in steps:
        if step.name not in state:
            visit(step.name)
    if not dropped:
        return steps
    out: List[FlowStep] = []
    for step in steps:
        kept = tuple(i for i in step.inputs if (step.name, i.name, i.source) not in dropped)
        out.append(
            FlowStep(
                step.name,
                step.label,
                step.group,
                kept,
                step.returns_nothing,
                step.col,
                step.row,
                step.metrics,
            )
        )
    return out


def parse_flow(pipeline: str, env: str, run_id: str, raw: str) -> Tuple[str, Optional[Flow]]:
    """Return ("ok", Flow), ("unsupported", None) or ("invalid", None).

    A flow with dropped parts is still "ok". "unsupported" is a well-formed object written in a
    record format version this dashboard does not know (e.g. by a newer waypoint_etl library).
    """
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return "invalid", None
    if not isinstance(data, dict):
        return "invalid", None
    version = data.get("v")
    if isinstance(version, bool) or not isinstance(version, int):
        return "invalid", None
    if version != SUPPORTED_VERSION:
        return "unsupported", None
    if (data.get("pipeline"), data.get("env"), data.get("run_id")) != (pipeline, env, run_id):
        return "invalid", None
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        return "invalid", None
    problems: List[str] = []
    if len(raw_steps) > MAX_STEPS:
        problems.append(f"only the first {MAX_STEPS} steps are shown")
        raw_steps = raw_steps[:MAX_STEPS]

    groups: List[GroupDef] = []
    raw_groups = data.get("groups")
    for g in raw_groups if isinstance(raw_groups, list) else []:
        key = g.get("key") if isinstance(g, dict) else None
        if isinstance(key, str) and _GROUP_KEY.match(key) and key not in {x.key for x in groups}:
            groups.append(GroupDef(key, _label(g.get("label"), MAX_STEP_LABEL) or key))
    group_keys = {g.key for g in groups}

    names = {
        s["name"]
        for s in raw_steps
        if isinstance(s, dict) and isinstance(s.get("name"), str) and _STEP_NAME.match(s["name"])
    }
    steps: List[FlowStep] = []
    seen: Set[str] = set()
    for item in raw_steps:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not _STEP_NAME.match(name):
            problems.append("a step with an invalid name was dropped")
            continue
        if name in seen:
            problems.append(f"duplicate step '{name}' dropped")
            continue
        seen.add(name)
        inputs: List[FlowInput] = []
        raw_inputs = item.get("inputs")
        for inp in raw_inputs if isinstance(raw_inputs, list) else []:
            in_name = inp.get("name") if isinstance(inp, dict) else None
            src = inp.get("from") if isinstance(inp, dict) else None
            if not isinstance(in_name, str) or not in_name or not isinstance(src, str):
                problems.append(f"an input of '{name}' was malformed and dropped")
                continue
            dangling = src not in names or src == name
            if dangling:
                problems.append(f"input '{in_name}' of '{name}' names unknown step '{src}'")
            inputs.append(FlowInput(in_name, src, dangling))
        group = item.get("group")
        steps.append(
            FlowStep(
                name=name,
                label=_label(item.get("label"), MAX_STEP_LABEL),
                group=group if isinstance(group, str) and group in group_keys else None,
                inputs=tuple(inputs),
                returns_nothing=item.get("returns_nothing") is True,
                col=_hint(item.get("col")),
                row=_hint(item.get("row")),
                metrics=_metric_decls(name, item.get("metrics"), problems),
            )
        )
    if not steps:
        return "invalid", None
    steps = _drop_cycles(steps, problems)
    return "ok", Flow(
        pipeline=pipeline,
        label=_label(data.get("label"), MAX_PIPELINE_LABEL),
        groups=tuple(groups),
        steps=tuple(steps),
        problems=tuple(problems),
    )
