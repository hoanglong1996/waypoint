from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.domain.models import (
    AliveSignal,
    DiedVerdict,
    Flow,
    FlowStep,
    ParseResult,
    StartMarker,
    StepFailure,
    StepRecord,
)
from app.domain.parsing import parse_run_id

FlowResult = Tuple[str, Optional[Flow]]  # ("ok", Flow), ("unsupported", None) or ("invalid", None)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _elapsed(now: datetime, marker: StartMarker) -> int:
    return max(0, int((now - marker.started_at).total_seconds()))


def _judge_died(
    now: datetime,
    unfinished: bool,
    beat: Optional[AliveSignal],
    verdict: Optional[DiedVerdict],
    dead_seconds: float,
) -> Optional[Dict[str, Any]]:
    """Whether the run died (specs/009-run-liveness-heartbeat).

    A stored verdict is final. Otherwise a run died when it has a heartbeat, still has unfinished
    work, and its latest heartbeat is older than `dead_seconds`. A run with no heartbeat is a run
    of a pipeline that sends none: it is never judged by this rule.
    """
    if verdict is not None:
        return {
            "judged_at": _iso(verdict.judged_at),
            "last_seen_at": _iso(verdict.last_seen_at),
            "recorded": True,
        }
    if beat is None or not unfinished:
        return None
    if (now - beat.beat_at).total_seconds() <= dead_seconds:
        return None
    return {"judged_at": _iso(now), "last_seen_at": _iso(beat.beat_at), "recorded": False}


def _error_json(failure: StepFailure) -> Dict[str, Any]:
    error: Dict[str, Any] = {"type": failure.error.type}
    if failure.error.message is not None:
        error["message"] = failure.error.message
    error["traceback"] = failure.error.traceback
    return error


def _current_failures(
    failures: Sequence[StepFailure],
    reported: Mapping[str, StepRecord],
    run_markers: Mapping[str, StartMarker],
) -> Dict[str, StepFailure]:
    """Steps whose latest attempt failed (specs/011-step-failure-errors/data-model.md).

    Attempts are told apart by `index`, not by time: a failure stands unless a finish record or a
    start marker of the same step has a higher index (a retry that ran or is running).
    """
    latest: Dict[str, StepFailure] = {}
    for failure in failures:
        known = latest.get(failure.step)
        if known is None or failure.index > known.index:
            latest[failure.step] = failure
    current: Dict[str, StepFailure] = {}
    for name, failure in latest.items():
        finished = reported.get(name)
        begun = run_markers.get(name)
        if finished is not None and finished.index >= failure.index:
            continue
        if begun is not None and begun.index > failure.index:
            continue
        current[name] = failure
    return current


def _is_loss(output: Optional[int], inputs: List[Dict[str, Any]]) -> bool:
    return output == 0 and any(i["value"] > 0 for i in inputs)


def _ordered_inputs(declared: Sequence[str], inputs: Dict[str, int]) -> List[Dict[str, Any]]:
    ordered = [{"name": n, "value": inputs[n]} for n in declared if n in inputs]
    ordered += [{"name": n, "value": v} for n, v in inputs.items() if n not in declared]
    return ordered


def _flow_json(flow: Flow) -> Dict[str, Any]:
    return {
        "label": flow.label,
        "groups": [{"key": g.key, "label": g.label} for g in flow.groups],
        "steps": [
            {
                "name": s.name,
                "label": s.label,
                "group": s.group,
                "inputs": [
                    {"name": i.name, "from": i.source, **({"dangling": True} if i.dangling else {})}
                    for i in s.inputs
                ],
                "returns_nothing": s.returns_nothing,
                "col": s.col,
                "row": s.row,
            }
            for s in flow.steps
        ],
    }


def _build_run(
    run_id: str,
    env: str,
    pipeline: str,
    reported: Dict[str, StepRecord],
    run_markers: Dict[str, StartMarker],
    flow_status: str,
    flow: Optional[Flow],
    unreadable: int,
    now: datetime,
    stale_hours: float,
    stall_seconds: float,
    beat: Optional[AliveSignal],
    verdict: Optional[DiedVerdict],
    dead_seconds: float,
    failures: Sequence[StepFailure] = (),
) -> Dict[str, Any]:
    started = parse_run_id(run_id)
    planned: List[FlowStep] = list(flow.steps) if flow else []
    planned_names = {s.name for s in planned}
    current = _current_failures(failures, reported, run_markers)
    # a failure that stopped the pipeline: no other attempt of the run has a higher index
    top = max(
        [r.index for r in reported.values()]
        + [m.index for m in run_markers.values()]
        + [f.index for f in failures],
        default=0,
    )
    stopping = next((f for f in current.values() if f.index == top), None)
    # a failed step is terminal, so it is not unfinished work for the heartbeat rule
    unfinished = any(s.name not in reported and s.name not in current for s in planned) or any(
        name not in reported and name not in current for name in run_markers
    )
    # Failed takes precedence over Died: the failure explains why the heartbeat stopped
    died = (
        None if stopping is not None else _judge_died(now, unfinished, beat, verdict, dead_seconds)
    )

    def live(name: str) -> Optional[StartMarker]:
        begun = run_markers.get(name)
        if name in reported or name in current or begun is None:
            return None
        return begun

    def attempt(name: str) -> int:
        if name in current:
            return current[name].index
        return reported[name].index if name in reported else run_markers[name].index

    # unplanned steps (or every step when there is no flow), in the order they ran
    extra = sorted(
        {n for n in list(reported) + list(run_markers) + list(current) if n not in planned_names},
        key=lambda n: (attempt(n), n),
    )
    running_index: Optional[int] = None
    for i, step in enumerate(planned):
        begun = live(step.name)
        if died is None and begun is not None and _elapsed(now, begun) <= stall_seconds:
            running_index = i
    # just started: the flow exists but nothing has reported yet
    starting = (
        died is None
        and flow is not None
        and not reported
        and not run_markers
        and not current
        and (now - started).total_seconds() <= stall_seconds
    )

    out_steps: List[Dict[str, Any]] = []
    loss: List[str] = []
    missing: List[str] = []
    running_step: Optional[str] = None

    def add_unfinished(name: str, begun: StartMarker, planned_step: bool) -> None:
        nonlocal running_step
        if died is not None:
            out_steps.append(
                {
                    "name": name,
                    "state": "died",
                    "started_at": _iso(begun.started_at),
                    "last_seen_at": died["last_seen_at"],
                }
            )
            if planned_step:
                missing.append(name)
            return
        elapsed = _elapsed(now, begun)
        state = "running" if elapsed <= stall_seconds else "stalled"
        out_steps.append(
            {
                "name": name,
                "state": state,
                "started_at": _iso(begun.started_at),
                "elapsed_seconds": elapsed,
            }
        )
        if state == "running":
            running_step = name
        elif planned_step:
            missing.append(name)

    def add_failed(name: str, failure: StepFailure, planned_step: bool) -> None:
        out_steps.append(
            {
                "name": name,
                "state": "failed",
                "started_at": _iso(failure.started_at),
                "failed_at": _iso(failure.failed_at),
                "error": _error_json(failure),
            }
        )
        if planned_step:
            missing.append(name)

    def add_done(name: str, found: StepRecord, declared: Sequence[str], planned_step: bool) -> None:
        inputs = _ordered_inputs(declared, found.inputs)
        state = "done" if planned_step or flow is None else "unplanned"
        out_steps.append(
            {
                "name": name,
                "state": state,
                "inputs": inputs,
                "output": found.output,
                "finished_at": _iso(found.finished_at),
            }
        )
        if planned_step and _is_loss(found.output, inputs):
            loss.append(name)

    for i, step in enumerate(planned):
        if step.name in current:
            add_failed(step.name, current[step.name], True)
            continue
        found = reported.get(step.name)
        if found is not None:
            add_done(step.name, found, [x.name for x in step.inputs], True)
            continue
        begun = run_markers.get(step.name)
        if begun is not None:
            add_unfinished(step.name, begun, True)
        elif starting or (running_index is not None and i > running_index):
            out_steps.append({"name": step.name, "state": "waiting"})
        else:
            out_steps.append({"name": step.name, "state": "missing", "missing": True})
            missing.append(step.name)
    for name in extra:
        if name in current:
            add_failed(name, current[name], False)
            continue
        found = reported.get(name)
        if found is not None:
            add_done(name, found, [], False)
        else:
            add_unfinished(name, run_markers[name], False)

    ended = max(
        [r.finished_at for r in reported.values()] + [f.failed_at for f in current.values()],
        default=started,
    )
    age = max(0, int((now - ended).total_seconds()))
    running = running_step is not None or starting
    return {
        "run_id": run_id,
        "pipeline": pipeline,
        "env": env,
        "started_at": _iso(started),
        "ended_at": _iso(ended),
        "duration_seconds": max(0, int((ended - started).total_seconds())),
        "age_seconds": age,
        "stale": not running and age > stale_hours * 3600,
        "status": (
            "running"
            if running
            else ("complete" if not missing and died is None and not current else "incomplete")
        ),
        "running_step": running_step,
        "first_missing_step": missing[0] if missing else None,
        "missing_count": len(missing),
        "loss_steps": loss,
        "unreadable": unreadable,
        "died": died,
        "failed": (
            {
                "step": stopping.step,
                "index": stopping.index,
                "failed_at": _iso(stopping.failed_at),
            }
            if stopping is not None
            else None
        ),
        "flow_status": flow_status,
        "flow_problems": list(flow.problems) if flow else [],
        "flow": _flow_json(flow) if flow else None,
        "steps": out_steps,
    }


def build_runs(
    parsed: ParseResult,
    env: str,
    pipeline: str,
    now: datetime,
    stale_hours: float,
    flows: Optional[Dict[str, FlowResult]] = None,
    markers: Sequence[StartMarker] = (),
    stall_seconds: float = 900.0,
    alive: Optional[Mapping[str, AliveSignal]] = None,
    verdicts: Optional[Mapping[str, DiedVerdict]] = None,
    dead_seconds: float = 90.0,
    failures: Sequence[StepFailure] = (),
) -> List[Dict[str, Any]]:
    """Group records into runs (newest first), each drawn from its own flow description.

    `flows` maps run id to its parsed flow. A run with no usable flow still shows the steps that
    reported, in index order, with `flow: null`. A start marker without a finish record means the
    step is running (stalled past `stall_seconds`); planned steps after a live running step are
    waiting; a finish record always wins over a marker. A record or marker for a step that is not
    in the run's flow is `unplanned`: shown, never counted as missing.

    `alive` maps run id to its latest heartbeat and `verdicts` to its stored died verdict. A run
    whose heartbeat is older than `dead_seconds` while work is unfinished, or that has a verdict, is
    Died: its open step is `died`, later planned steps are missing and it is never running. A
    heartbeat alone never creates a run.

    `failures` are the validated failure items. A step whose latest attempt failed is `failed`
    (never running, stalled or died); a failure that no later attempt of the run follows stopped the
    pipeline, and then `failed` names it and the run is not Died. A failure item alone creates a run.
    """
    flows = flows or {}
    alive = alive or {}
    verdicts = verdicts or {}
    by_run: Dict[str, Dict[str, StepRecord]] = {}
    for rec in parsed.records:
        run_steps = by_run.setdefault(rec.run_id, {})
        current = run_steps.get(rec.step)
        if current is None or rec.finished_at >= current.finished_at:
            run_steps[rec.step] = rec
    # a run that has only unreadable records, only markers, or only a flow still exists
    for run_id in parsed.unreadable_by_run:
        by_run.setdefault(run_id, {})
    markers_by_run: Dict[str, Dict[str, StartMarker]] = {}
    for marker in markers:
        current_marker = markers_by_run.setdefault(marker.run_id, {}).get(marker.step)
        if current_marker is None or marker.started_at >= current_marker.started_at:
            markers_by_run[marker.run_id][marker.step] = marker
        by_run.setdefault(marker.run_id, {})
    for run_id in flows:
        by_run.setdefault(run_id, {})
    failures_by_run: Dict[str, List[StepFailure]] = {}
    for failure in failures:
        failures_by_run.setdefault(failure.run_id, []).append(failure)
        by_run.setdefault(failure.run_id, {})

    return [
        _build_run(
            run_id,
            env,
            pipeline,
            by_run[run_id],
            markers_by_run.get(run_id, {}),
            *flows.get(run_id, ("missing", None)),
            parsed.unreadable_by_run.get(run_id, 0),
            now,
            stale_hours,
            stall_seconds,
            alive.get(run_id),
            verdicts.get(run_id),
            dead_seconds,
            failures_by_run.get(run_id, ()),
        )
        for run_id in sorted(by_run, reverse=True)
    ]
