"""The timeline of a run: recorded events plus events derived from its records
(specs/012-duration-and-run-events, research R3, R4, R13). Pure functions, no I/O."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domain.models import RunEvent

Entry = Dict[str, Any]

START = 0  # derived "started" events sit at the start of their second
END = 999  # "finished", "failed" and "ended" events at the end of their second
_RANK_DERIVED = 0
_RANK_RECORDED = 1


def stamp(moment: datetime, millis: int = 0) -> str:
    """ISO-8601 UTC with milliseconds, as the API returns it."""
    moment = moment.astimezone(timezone.utc).replace(microsecond=millis * 1000)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def _recorded_stamp(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _seconds_label(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes} min" if minutes >= 1 else f"{int(seconds)} s"


def recorded_entries(events: Sequence[RunEvent]) -> List[Entry]:
    """Timeline entries for author-sent events."""
    out: List[Entry] = []
    for e in events:
        entry: Entry = {
            "id": f"r:{e.level}:{e.n}",
            "ts": _recorded_stamp(e.ts),
            "level": e.level,
            "step": e.step,
            "message": e.message,
            "fields": dict(e.fields) if e.fields else None,
            "source": "pipeline",
            "kind": "custom",
            "_rank": _RANK_RECORDED,
            "_seq": e.n,
        }
        if e.item is not None:  # only events recorded inside a map step item (specs/014)
            entry["item"] = e.item
        out.append(entry)
    return out


def derive_events(run: Dict[str, Any], stall_seconds: float) -> List[Entry]:
    """Events the monitor builds from a built run (data-model.md "Timeline entry")."""
    out: List[Entry] = []

    def add(
        kind: str,
        level: str,
        moment: datetime,
        millis: int,
        message: str,
        step: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
        index: int = 0,
    ) -> None:
        out.append(
            {
                "id": f"d:{kind}:{step or ''}:{index}",
                "ts": stamp(moment, millis),
                "level": level,
                "step": step,
                "message": message,
                "fields": fields or None,
                "source": "monitor",
                "kind": kind,
                "_rank": _RANK_DERIVED,
                "_seq": len(out),
            }
        )

    add("run_started", "info", _parse(run["started_at"]), START, "Run started")
    # Steps run one after another: handle them in the order they ran, so that a step that starts in
    # the second the previous one finished is listed after it (the records only have whole seconds).
    ordered = sorted(
        enumerate(run["steps"]),
        key=lambda item: (
            item[1].get("started_at")
            or item[1].get("finished_at")
            or item[1].get("failed_at")
            or "~",
            item[1].get("finished_at") or item[1].get("failed_at") or "~",
            item[0],
        ),
    )
    previous_end: Optional[datetime] = None
    for i, step in ordered:
        name = step["name"]
        state = step.get("state")
        began = step.get("started_at")
        if began and state in ("done", "unplanned", "failed", "running", "stalled", "died"):
            start = _parse(began)
            after_previous = (
                previous_end is not None and previous_end.replace(microsecond=0) == start
            )
            add(
                "step_started",
                "info",
                start,
                END if after_previous else START,
                f"Step {name} started",
                name,
                index=i,
            )
        if state in ("done", "unplanned") and step.get("finished_at"):
            fields: Dict[str, Any] = {}
            if step.get("output") is not None:
                fields["output"] = step["output"]
            if step.get("duration_seconds") is not None:
                fields["duration_seconds"] = step["duration_seconds"]
            previous_end = _parse(step["finished_at"])
            add(
                "step_finished",
                "info",
                previous_end,
                END,
                f"Step {name} finished",
                name,
                fields,
                i,
            )
        elif state == "failed":
            error = step.get("error") or {}
            text = str(error.get("type") or "Error")
            if error.get("message") is not None:
                text += f": {error['message']}"
            previous_end = _parse(step["failed_at"])
            add(
                "step_failed",
                "error",
                previous_end,
                END,
                f"Step {name} failed: {text}",
                name,
                {"error_type": error.get("type") or "Error"},
                i,
            )
        elif state == "stalled" and began:
            add(
                "step_stalled",
                "warning",
                _parse(began) + timedelta(seconds=stall_seconds),
                START,
                f"Step {name} stalled: still running after {_seconds_label(stall_seconds)}",
                name,
                index=i,
            )
    if run.get("died"):
        died = run["died"]
        add(
            "run_died",
            "error",
            _parse(died["judged_at"]),
            END,
            f"Run died: the process stopped sending signs of life (last seen {died['last_seen_at'][11:19]} UTC)",
        )
    if run.get("failed"):
        failed = run["failed"]
        add(
            "run_stopped",
            "error",
            _parse(failed["failed_at"]),
            END,
            f"Run stopped at step {failed['step']}",
        )
    elif run["status"] == "complete":
        duration = (run.get("duration") or {}).get("seconds")
        add(
            "run_finished",
            "info",
            _parse(run["ended_at"]),
            END,
            "Run finished",
            fields={"duration_seconds": duration} if duration is not None else None,
        )
    return out


def merge(derived: Sequence[Entry], recorded: Sequence[Entry]) -> List[Entry]:
    """One list, oldest first: by time, derived before recorded at the same instant, derived in
    derivation order and recorded by their sequence number (research R4)."""
    return sorted(list(derived) + list(recorded), key=lambda e: (e["ts"], e["_rank"], e["_seq"]))


def select(
    entries: Sequence[Entry],
    levels: Optional[Sequence[str]],
    step: Optional[str],
    offset: int,
    limit: int,
    item: Optional[str] = None,
) -> Tuple[List[Entry], int]:
    """The page `[offset, offset + limit)` of the entries matching the filters, and how many match.

    `item` keeps only the events recorded inside that map step item (specs/014)."""
    matched = [
        e
        for e in entries
        if (not levels or e["level"] in levels)
        and (step is None or e["step"] == step)
        and (item is None or e.get("item") == item)
    ]
    return matched[offset : offset + limit], len(matched)


def dropped(recorded: Sequence[RunEvent]) -> int:
    """Events the sender numbered but that are no longer stored: highest `n` minus events read."""
    if not recorded:
        return 0
    return max(0, max(e.n for e in recorded) - len(recorded))


def public(entry: Entry) -> Entry:
    """The entry as the API returns it (without the sort helpers)."""
    return {k: v for k, v in entry.items() if not k.startswith("_")}
