import json

import pytest

from migrator.baseline.scenarios import is_holdout, load_rules, load_suite
from tests.conftest import FIXTURES


def write(tmp_path, data) -> object:
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(data))
    return path


def test_variables_are_replaced(tmp_path):
    path = write(
        tmp_path,
        {
            "vars": {"TOKEN": "abc"},
            "scenarios": [
                {
                    "name": "a",
                    "steps": [
                        {
                            "method": "GET",
                            "path": "/x",
                            "headers": {"Authorization": "Bearer ${TOKEN}"},
                        },
                    ],
                }
            ],
        },
    )
    [scenario] = load_suite(path).scenarios
    assert scenario.steps[0].headers == {"Authorization": "Bearer abc"}


def test_unknown_variable_fails(tmp_path):
    path = write(
        tmp_path,
        {
            "scenarios": [
                {
                    "name": "a",
                    "steps": [
                        {"method": "GET", "path": "/${MISSING}"},
                    ],
                }
            ]
        },
    )
    with pytest.raises(ValueError, match="MISSING"):
        load_suite(path)


def test_scenario_names_must_be_unique(tmp_path):
    step = {"method": "GET", "path": "/"}
    path = write(
        tmp_path, {"scenarios": [{"name": "a", "steps": [step]}, {"name": "a", "steps": [step]}]}
    )
    with pytest.raises(ValueError, match="unique"):
        load_suite(path)


def test_holdout_is_stable_and_about_20_percent():
    names = [f"scenario {i}" for i in range(1000)]
    held = [n for n in names if is_holdout(n)]
    assert held == [n for n in names if is_holdout(n)]  # same answer every time
    assert 150 < len(held) < 250


def test_fixture_suite_and_rules_load():
    suite = load_suite(FIXTURES / "scenarios" / "shop.json")
    assert len(suite.scenarios) == 10
    assert suite.env == {"JWT_SECRET": "baseline-secret"}
    assert "${" not in json.dumps(suite.model_dump())
    rules = load_rules(FIXTURES / "scenarios" / "ts-nestjs-shop.rules.json")
    assert {r.action for r in rules} == {"timestamp"}
