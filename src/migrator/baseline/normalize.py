"""Normalization rules and comparing two observations.

A path looks like `status`, `body.createdAt`, `body[*].id` or `db.users.added[*].created_at`.
List positions are always written as `[*]`, so one rule covers every item in a list.
"""

import re
from typing import Any

from migrator.baseline.models import NormalizationRule

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
TIMESTAMP_PLACEHOLDER = "<timestamp>"
IGNORED_PLACEHOLDER = "<ignored>"


def normalize(value: Any, rules: list[NormalizationRule], path: str = "") -> Any:
    actions = {rule.path: rule.action for rule in rules}
    return _normalize(value, actions, path)


def find_differences(first: Any, second: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """Every leaf path where the two values are not equal."""
    if isinstance(first, dict) and isinstance(second, dict):
        found = []
        for key in sorted(set(first) | set(second)):
            found += find_differences(first.get(key), second.get(key), _join(path, key))
        return found
    if isinstance(first, list) and isinstance(second, list) and len(first) == len(second):
        found = []
        for a, b in zip(first, second, strict=True):
            found += find_differences(a, b, f"{path}[*]")
        return found
    return [] if first == second else [(path, first, second)]


def propose_rules(paths_and_values: list[tuple[str, Any, Any]]) -> list[NormalizationRule]:
    """Suggest a rule for every unstable path. A human must approve them before use."""
    proposals: dict[str, NormalizationRule] = {}
    for path, first, second in paths_and_values:
        if path in proposals:
            continue
        if _looks_like_timestamp(first) and _looks_like_timestamp(second):
            action, reason = "timestamp", "time value changes on every run"
        else:
            action, reason = "ignore", "value changed between two runs of the same source app"
        proposals[path] = NormalizationRule(path=path, action=action, reason=reason)
    return [proposals[p] for p in sorted(proposals)]


def _normalize(value: Any, actions: dict[str, str], path: str) -> Any:
    if isinstance(value, dict):
        return {k: _normalize(v, actions, _join(path, k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v, actions, f"{path}[*]") for v in value]
    action = actions.get(path)
    if action == "ignore":
        return IGNORED_PLACEHOLDER
    if action == "timestamp" and _looks_like_timestamp(value):
        return TIMESTAMP_PLACEHOLDER
    # A "timestamp" rule on a value that is not a timestamp does nothing, so the difference
    # still shows up. We never hide a surprise.
    return value


def _looks_like_timestamp(value: Any) -> bool:
    return isinstance(value, str) and bool(TIMESTAMP.match(value))


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key
