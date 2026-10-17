"""Smallest possible adopter of Waypoint (waypoint_etl): three steps, one init block, no audit code in run().

REDIS_URL=redis://localhost:6379/0 python examples/sample_pipeline.py
"""

import os
from typing import List

import waypoint_etl
from waypoint_etl import Metric, PipelineSpec, StepSpec, audited_step

SAMPLE = PipelineSpec(
    name="sample",
    label="Sample",
    steps=(
        StepSpec("extract"),
        StepSpec(
            "clean",
            inputs=(("rows", "extract"),),
            metrics=(Metric("rejected", label="Rejected rows", unit="rows", warn_above=100),),
        ),
        StepSpec("load", inputs=(("rows", "clean"),), returns_nothing=True),
    ),
)


@audited_step("extract")
def extract() -> List[int]:
    return list(range(10))


@audited_step("clean")
def clean(rows: List[int]) -> List[int]:
    kept = [r for r in rows if r % 2 == 0]
    waypoint_etl.metric(
        "rejected", len(rows) - len(kept), mode="add"
    )  # a named number on this step
    waypoint_etl.metric("peak_batch", len(rows), mode="max")
    return kept


@audited_step("load")
def load(rows: List[int]) -> None:
    print(f"loaded {len(rows)} rows")


def run() -> None:
    load(clean(extract()))


if __name__ == "__main__":
    waypoint_etl.init(
        pipeline=SAMPLE,
        redis_url=os.getenv("REDIS_URL"),
        env=os.getenv("ENV_NAME", "qa"),
    )
    run()
