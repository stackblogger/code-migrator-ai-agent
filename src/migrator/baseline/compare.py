"""Normalize traces with approved rules and compare two sets of traces."""

from typing import Any

from migrator.baseline.models import Difference, NormalizationRule, Observation, Trace
from migrator.baseline.normalize import find_differences, normalize


def normalize_trace(trace: Trace, rules: list[NormalizationRule]) -> Trace:
    steps = [
        step.model_copy(update={"observed": Observation.model_validate(_normalized(step, rules))})
        for step in trace.steps
    ]
    return trace.model_copy(update={"steps": steps})


def compare_traces(expected: list[Trace], actual: list[Trace]) -> list[Difference]:
    """Both lists must be already normalized and in the same scenario order."""
    differences: list[Difference] = []
    for want, got in zip(expected, actual, strict=True):
        if len(want.steps) != len(got.steps):
            differences.append(
                Difference(
                    scenario=want.scenario,
                    step=0,
                    path="steps",
                    first=len(want.steps),
                    second=len(got.steps),
                )
            )
            continue
        for number, (a, b) in enumerate(zip(want.steps, got.steps, strict=True), start=1):
            for path, first, second in find_differences(
                a.observed.model_dump(), b.observed.model_dump()
            ):
                differences.append(
                    Difference(
                        scenario=want.scenario, step=number, path=path, first=first, second=second
                    )
                )
    return differences


def compare_schemas(expected: dict, actual: dict) -> list[Difference]:
    return [
        Difference(scenario="(database schema)", step=0, path=path, first=first, second=second)
        for path, first, second in find_differences(expected, actual)
    ]


def _normalized(step: Any, rules: list[NormalizationRule]) -> Any:
    return normalize(step.observed.model_dump(), rules)
