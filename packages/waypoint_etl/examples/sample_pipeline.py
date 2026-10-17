"""Smallest possible adopter of Waypoint (waypoint_etl): three steps, one init block, no audit code in run().

REDIS_URL=redis://localhost:6379/0 python examples/sample_pipeline.py
REDIS_URL=redis://localhost:6379/0 python examples/sample_pipeline.py map    # a loop: a map step
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List

import waypoint_etl
from waypoint_etl import MapStepSpec, Metric, PipelineSpec, StepSpec, audited_step

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


# A loop inside the pipeline: one step repeats fetch -> transform -> load for every account, up to five at a
# time. ``over`` names the step that supplies the accounts; ``max_concurrency`` is shown, not enforced.
LOOP = PipelineSpec(
    name="sample-loop",
    label="Sample loop",
    steps=(
        StepSpec("list_accounts"),
        MapStepSpec(
            "accounts",
            over="list_accounts",
            max_concurrency=5,
            steps=(
                StepSpec("fetch_account", inputs=(("account", "list_accounts"),)),
                StepSpec(
                    "transform_rows",
                    inputs=(("rows", "fetch_account"),),
                    metrics=(Metric("rejected", unit="rows", warn_above=100),),
                ),
                StepSpec("load_rows", inputs=(("rows", "transform_rows"),), returns_nothing=True),
            ),
        ),
    ),
)


@audited_step("list_accounts")
def list_accounts() -> List[int]:
    return list(range(1, 11))


@audited_step("fetch_account")
def fetch(account: int) -> List[int]:
    return list(range(account * 10))


@audited_step("transform_rows")
def transform(rows: List[int]) -> List[int]:
    kept = [r for r in rows if r % 7]
    waypoint_etl.metric("rejected", len(rows) - len(kept), mode="add")
    if len(rows) == 70:
        raise ValueError("bad date")  # one item fails; the loop carries on
    return kept


@audited_step("load_rows")
def load_rows(rows: List[int]) -> None:
    waypoint_etl.log("Loaded rows", rows=len(rows))


def process(account: int) -> None:
    # An item key is an id or an index, never a name or other personal data.
    with waypoint_etl.item(f"acct-{account}"):
        load_rows(transform(fetch(account)))


def process_safely(account: int) -> None:
    try:
        process(account)
    except ValueError:
        pass  # the failure is already recorded on the item


def run_loop(workers: int = 5) -> None:
    accounts = list_accounts()
    with waypoint_etl.map_step("accounts"):  # the whole loop
        if workers <= 1:
            for account in accounts:
                process_safely(account)
        else:
            with ThreadPoolExecutor(workers) as pool:  # item() inside the worker finds its map step
                list(pool.map(process_safely, accounts))


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
    looping = sys.argv[1:] == ["map"]
    waypoint_etl.init(
        pipeline=LOOP if looping else SAMPLE,
        redis_url=os.getenv("REDIS_URL"),
        env=os.getenv("ENV_NAME", "qa"),
    )
    run_loop() if looping else run()
