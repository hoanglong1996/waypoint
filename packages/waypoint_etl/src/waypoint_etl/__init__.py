"""Waypoint: per-step tracking for ETL pipelines, shown by Waypoint Monitor.

    waypoint_etl.init(pipeline=SPEC, redis_url=url, env="prod")   # once, in main.py

    @waypoint_etl.audited_step("read_partners")                    # on each step function
    def execute(self) -> list[Partner]: ...

Only names and counts are recorded, never item contents. See README.md.
"""

from waypoint_etl.decorator import audited_step, wrap
from waypoint_etl.keys import FLOW_VERSION
from waypoint_etl.registry import init
from waypoint_etl.spec import GroupSpec, PipelineSpec, StepSpec

__version__ = "0.3.0"

__all__ = [
    "FLOW_VERSION",
    "GroupSpec",
    "PipelineSpec",
    "StepSpec",
    "__version__",
    "audited_step",
    "init",
    "wrap",
]
