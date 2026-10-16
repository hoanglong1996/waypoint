from typing import Any, Dict, List, Mapping, Optional, Sequence

Run = Dict[str, Any]

# Card status, first match wins: running, died, stale, incomplete, lost, ok
ATTENTION = ("died", "stale", "incomplete", "lost")


def _metric(step: Mapping[str, Any]) -> Optional[int]:
    """A step's count: its output, or its first input when it returns nothing."""
    if step.get("state") != "done":
        return None
    if step.get("output") is not None:
        return int(step["output"])
    inputs = step.get("inputs") or []
    return int(inputs[0]["value"]) if inputs else None


def card_status(run: Mapping[str, Any]) -> str:
    if run["status"] == "running":
        return "running"
    if run.get("died"):
        return "died"
    if run["stale"]:
        return "stale"
    if run["status"] == "incomplete":
        return "incomplete"
    if run["loss_steps"]:
        return "lost"
    return "ok"


def _headline(run: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """First step, largest step between first and last, last step of the run's own flow."""
    labels = {s["name"]: s.get("label") for s in ((run.get("flow") or {}).get("steps") or [])}
    listed = [s for s in run["steps"] if s.get("state") != "unplanned"]
    if not listed:
        return [
            {"key": k, "step": None, "label": None, "value": None}
            for k in ("first", "peak", "last")
        ]
    largest: Optional[Mapping[str, Any]] = None
    best = -1
    for s in listed[1:-1]:
        value = _metric(s)
        if value is not None and value > best:
            best, largest = value, s
    if largest is None and len(listed) > 2:
        largest = listed[1]
    picks = {"first": listed[0], "peak": largest, "last": listed[-1]}
    out: List[Dict[str, Any]] = []
    for key in ("first", "peak", "last"):
        s = picks[key]
        out.append(
            {
                "key": key,
                "step": s["name"] if s else None,
                "label": (labels.get(s["name"]) or s["name"]) if s else None,
                "value": _metric(s) if s else None,
            }
        )
    return out


def _latest(env_order: Sequence[str], by_env: Mapping[str, Sequence[Run]]) -> Optional[Run]:
    """Newest run across environments: greatest run id; a tie goes to the environment listed first."""
    newest: Optional[Run] = None
    for env in env_order:
        runs = by_env.get(env) or []
        if runs and (newest is None or runs[0]["run_id"] > newest["run_id"]):
            newest = runs[0]
    return newest


def _summary(run: Run) -> Dict[str, Any]:
    stalled = next((s for s in run["steps"] if s.get("state") == "stalled"), None)
    died = run.get("died")
    died_step = next((s for s in run["steps"] if s.get("state") == "died"), None)
    return {
        "run_id": run["run_id"],
        "env": run["env"],
        "status": run["status"],
        "stale": run["stale"],
        "started_at": run["started_at"],
        "ended_at": run["ended_at"],
        "age_seconds": run["age_seconds"],
        "loss_steps": list(run["loss_steps"]),
        "first_missing_step": run["first_missing_step"],
        "stalled_step": stalled["name"] if stalled else None,
        "stalled_seconds": stalled.get("elapsed_seconds") if stalled else None,
        "died_step": died_step["name"] if died_step else None,
        "last_seen_at": died["last_seen_at"] if died else None,
        "unreadable": run["unreadable"],
        "headline": _headline(run),
    }


def build_overview(
    runs: Mapping[str, Mapping[str, Sequence[Run]]], env_order: Sequence[str]
) -> List[Dict[str, Any]]:
    """One card per pipeline that has a run. `runs[env][pipeline]` is that pipeline's runs, newest first.

    Cards that need attention come first; each group is ordered by label.
    """
    names = sorted({name for by_pipeline in runs.values() for name in by_pipeline})
    cards: List[Dict[str, Any]] = []
    for name in names:
        by_env = {env: runs.get(env, {}).get(name, []) for env in env_order}
        newest = _latest(env_order, by_env)
        if newest is None:
            continue
        status = card_status(newest)
        flow = newest.get("flow")
        cards.append(
            {
                "name": name,
                "label": (flow or {}).get("label") or name,
                "environments": [env for env in env_order if by_env[env]],
                "card_status": status,
                "needs_attention": status in ATTENTION,
                "latest": _summary(newest),
            }
        )
    cards.sort(key=lambda c: (not c["needs_attention"], c["label"].casefold(), c["name"]))
    return cards
