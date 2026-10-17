"""``MapStepSpec`` declaration and validation. Specs 014 data-model.md "Declaration", FR-001, FR-010."""

import unittest
from typing import Dict, Tuple

from waypoint_etl import GroupSpec, MapStepSpec, Metric, PipelineSpec, StepSpec
from waypoint_etl.spec import validate_spec


def inner(*names: str) -> Tuple[StepSpec, ...]:
    return tuple(StepSpec(n) for n in names)


def spec(*steps: object) -> PipelineSpec:
    return PipelineSpec(name="demo", steps=tuple(steps))  # type: ignore[arg-type]


class TestMapStepSpec(unittest.TestCase):
    def test_a_full_valid_declaration(self) -> None:
        validate_spec(
            spec(
                StepSpec("list_accounts"),
                MapStepSpec(
                    "accounts",
                    over="list_accounts",
                    max_concurrency=5,
                    label="Accounts",
                    inputs=(("accounts", "list_accounts"),),
                    steps=(
                        StepSpec("fetch"),
                        StepSpec(
                            "transform",
                            inputs=(("rows", "fetch"),),
                            metrics=(Metric("rejected", unit="rows", warn_above=100),),
                        ),
                        StepSpec("load", inputs=(("rows", "transform"),)),
                    ),
                ),
                StepSpec("publish", inputs=(("done", "accounts"),)),
            )
        )

    def test_an_inner_step_may_read_an_earlier_top_level_step(self) -> None:
        validate_spec(
            spec(
                StepSpec("a"),
                MapStepSpec("m", steps=(StepSpec("x", inputs=(("v", "a"),)),)),
            )
        )

    def test_a_map_step_may_be_the_first_step(self) -> None:
        validate_spec(spec(MapStepSpec("m", steps=inner("x"))))

    def test_refused_declarations(self) -> None:
        cases: Dict[str, PipelineSpec] = {
            "bad name": spec(MapStepSpec("Accounts", steps=inner("x"))),
            "long name": spec(MapStepSpec("m" * 65, steps=inner("x"))),
            "duplicate of a top-level step": spec(
                StepSpec("m"), MapStepSpec("m", steps=inner("x"))
            ),
            "inner duplicate of a top-level step": spec(
                StepSpec("x"), MapStepSpec("m", steps=inner("x"))
            ),
            "inner duplicate of a later top-level step": spec(
                MapStepSpec("m", steps=inner("x")), StepSpec("x")
            ),
            "inner duplicate of another map's inner step": spec(
                MapStepSpec("m", steps=inner("x")), MapStepSpec("n", steps=inner("x"))
            ),
            "duplicate inner step": spec(MapStepSpec("m", steps=inner("x", "x"))),
            "empty item flow": spec(MapStepSpec("m", steps=())),
            "21 inner steps": spec(MapStepSpec("m", steps=inner(*[f"s{i}" for i in range(21)]))),
            "nested map": spec(
                MapStepSpec("m", steps=(MapStepSpec("n", steps=inner("x")),))  # type: ignore[arg-type]
            ),
            "input from a later inner step": spec(
                MapStepSpec("m", steps=(StepSpec("x", inputs=(("v", "y"),)), StepSpec("y")))
            ),
            "input from another map's inner step": spec(
                MapStepSpec("m", steps=inner("x")),
                MapStepSpec("n", steps=(StepSpec("y", inputs=(("v", "x"),)),)),
            ),
            "map input from a later step": spec(
                MapStepSpec("m", steps=inner("x"), inputs=(("v", "later"),)), StepSpec("later")
            ),
            "max_concurrency 0": spec(MapStepSpec("m", steps=inner("x"), max_concurrency=0)),
            "max_concurrency bool": spec(MapStepSpec("m", steps=inner("x"), max_concurrency=True)),
            "max_concurrency float": spec(
                MapStepSpec("m", steps=inner("x"), max_concurrency=2.5)  # type: ignore[arg-type]
            ),
            "over a later step": spec(
                MapStepSpec("m", steps=inner("x"), over="later"), StepSpec("later")
            ),
            "over an unknown step": spec(MapStepSpec("m", steps=inner("x"), over="nope")),
            "bad inner metric": spec(
                MapStepSpec("m", steps=(StepSpec("x", metrics=(Metric("Bad"),)),))
            ),
            "undeclared group": spec(MapStepSpec("m", steps=inner("x"), group="g")),
            "inner step with a group": PipelineSpec(
                name="demo",
                groups=(GroupSpec("g", "G"),),
                steps=(MapStepSpec("m", steps=(StepSpec("x", group="g"),)),),
            ),
            "negative layout hint": spec(MapStepSpec("m", steps=inner("x"), col=-1)),
        }
        for label, candidate in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_spec(candidate)

    def test_the_error_names_the_map_step(self) -> None:
        with self.assertRaises(ValueError) as caught:
            validate_spec(spec(MapStepSpec("m", steps=(StepSpec("x"), MapStepSpec("n", steps=inner("y"))))))  # type: ignore[arg-type]
        self.assertIn("'m'", str(caught.exception))

    def test_inner_steps_count_toward_the_step_limit(self) -> None:
        many = tuple(StepSpec(f"t{i}") for i in range(81))
        maps = tuple(
            MapStepSpec(f"m{i}", steps=inner(*[f"m{i}_s{j}" for j in range(10)])) for i in range(2)
        )
        with self.assertRaises(ValueError):
            validate_spec(spec(*many, *maps))  # 83 top-level + 20 inner > 100
        validate_spec(spec(*many[:70], *maps))  # 72 + 20 = 92

    def test_pipelines_without_a_map_step_validate_as_before(self) -> None:
        validate_spec(spec(StepSpec("a"), StepSpec("b", inputs=(("x", "a"),))))
        with self.assertRaises(ValueError):
            validate_spec(spec(StepSpec("a"), StepSpec("a")))


if __name__ == "__main__":
    unittest.main()
