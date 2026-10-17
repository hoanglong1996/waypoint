"""A step's metrics as the API serves them (specs/013-step-metrics, research R6).

Pure functions over validated records and the run's own declarations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from app.domain.models import MetricDecl, MetricNumber, StepMetrics


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def metric_flag(value: Optional[MetricNumber], decl: Optional[MetricDecl]) -> Optional[str]:
    """`above` when the value is strictly over `warn_above`, `below` when strictly under `warn_below`.

    Equal to a limit is not flagged; a metric that is not reported or not declared never is.
    """
    if value is None or decl is None:
        return None
    if decl.warn_above is not None and value > decl.warn_above:
        return "above"
    if decl.warn_below is not None and value < decl.warn_below:
        return "below"
    return None


def count_over(metrics: Sequence[Dict[str, Any]]) -> int:
    return sum(1 for m in metrics if m["flag"] is not None)


def step_metrics(
    records: Sequence[StepMetrics],
    step_name: str,
    attempt_index: int,
    declared: Sequence[MetricDecl] = (),
) -> List[Dict[str, Any]]:
    """The metrics of one step, or an empty list when it has none declared and none recorded.

    Only the record of the step's current attempt counts: a record of an older attempt is ignored.
    Declared metrics come first in declared order (`value` null when not reported), then undeclared
    metrics by name.
    """
    record = next((r for r in records if r.step == step_name and r.index == attempt_index), None)
    values = record.values if record is not None else {}
    updated = _iso(record.updated_at) if record is not None and record.updated_at else None
    out: List[Dict[str, Any]] = []
    known = {d.name for d in declared}
    for decl in declared:
        value = values.get(decl.name)
        out.append(
            {
                "name": decl.name,
                "label": decl.label,
                "value": value,
                "unit": decl.unit,
                "declared": True,
                "flag": metric_flag(value, decl),
                "updated_at": updated if value is not None else None,
            }
        )
    for name in sorted(n for n in values if n not in known):
        out.append(
            {
                "name": name,
                "label": None,
                "value": values[name],
                "unit": None,
                "declared": False,
                "flag": None,
                "updated_at": updated,
            }
        )
    return out
