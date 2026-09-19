from migrator.baseline.models import NormalizationRule
from migrator.baseline.normalize import find_differences, normalize, propose_rules


def rule(path: str, action: str = "timestamp") -> NormalizationRule:
    return NormalizationRule(path=path, action=action)  # type: ignore[arg-type]


def test_timestamp_rule_replaces_only_timestamps():
    value = {"body": [{"createdAt": "2026-09-19T16:00:30.170Z", "note": "x"}]}
    assert normalize(value, [rule("body[*].createdAt")]) == {
        "body": [{"createdAt": "<timestamp>", "note": "x"}]
    }
    # A timestamp rule on a non-timestamp value does nothing, so a surprise still shows up.
    assert normalize({"body": {"createdAt": "yesterday"}}, [rule("body.createdAt")]) == {
        "body": {"createdAt": "yesterday"}
    }


def test_ignore_rule():
    assert normalize({"headers": {"etag": "abc"}}, [rule("headers.etag", "ignore")]) == {
        "headers": {"etag": "<ignored>"}
    }


def test_find_differences_uses_star_for_list_items():
    first = {"status": 200, "body": [{"id": 1}, {"id": 2}]}
    second = {"status": 200, "body": [{"id": 1}, {"id": 3}]}
    assert find_differences(first, second) == [("body[*].id", 2, 3)]


def test_list_length_change_is_one_difference():
    assert find_differences({"body": [1, 2]}, {"body": [1]}) == [("body", [1, 2], [1])]


def test_proposals():
    diffs = [
        ("body.createdAt", "2026-01-01T00:00:00Z", "2026-01-01T00:00:05Z"),
        ("body.createdAt", "2026-01-01T00:00:01Z", "2026-01-01T00:00:06Z"),
        ("body.token", "abc", "def"),
    ]
    assert [(r.path, r.action) for r in propose_rules(diffs)] == [
        ("body.createdAt", "timestamp"),
        ("body.token", "ignore"),
    ]
