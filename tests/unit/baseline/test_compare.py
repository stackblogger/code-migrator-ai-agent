from migrator.baseline.compare import compare_traces, normalize_trace
from migrator.baseline.models import NormalizationRule, Observation, ScenarioStep, StepTrace, Trace


def trace(created_at: str, status: int = 201) -> Trace:
    step = StepTrace(
        request=ScenarioStep(method="POST", path="/users"),
        observed=Observation(status=status, body={"id": 1, "createdAt": created_at}),
    )
    return Trace(scenario="register", steps=[step])


RULES = [NormalizationRule(path="body.createdAt", action="timestamp")]


def test_same_after_normalization():
    a = normalize_trace(trace("2026-01-01T00:00:00Z"), RULES)
    b = normalize_trace(trace("2026-01-01T00:00:09Z"), RULES)
    assert compare_traces([a], [b]) == []


def test_real_change_is_reported():
    a = normalize_trace(trace("2026-01-01T00:00:00Z"), RULES)
    b = normalize_trace(trace("2026-01-01T00:00:00Z", status=200), RULES)
    [difference] = compare_traces([a], [b])
    assert (difference.scenario, difference.step, difference.path) == ("register", 1, "status")
    assert (difference.first, difference.second) == (201, 200)
