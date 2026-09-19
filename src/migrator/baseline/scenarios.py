"""Load scenario suites and pick hold-out scenarios."""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from migrator.baseline.models import NormalizationRule, Scenario, ScenarioSuite

log = logging.getLogger(__name__)

VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
HOLDOUT_EVERY = 5  # about 20% of scenarios are held out


def load_suite(path: Path) -> ScenarioSuite:
    suite = ScenarioSuite.model_validate_json(path.read_text())
    scenarios = [
        Scenario.model_validate(_substitute(s.model_dump(), suite.vars)) for s in suite.scenarios
    ]
    names = [s.name for s in scenarios]
    if len(set(names)) != len(names):
        raise ValueError(f"Scenario names must be unique in {path}")
    log.info("Loaded %d scenarios from %s", len(scenarios), path)
    return suite.model_copy(update={"scenarios": scenarios})


def load_rules(path: Path | None) -> list[NormalizationRule]:
    if path is None:
        return []
    rules = [NormalizationRule.model_validate(r) for r in json.loads(path.read_text())]
    log.info("Loaded %d approved normalization rules from %s", len(rules), path)
    return rules


def is_holdout(scenario_name: str) -> bool:
    """Stable choice based on the name, so the same scenarios are always held out."""
    digest = hashlib.sha256(scenario_name.encode()).digest()
    return digest[0] % HOLDOUT_EVERY == 0


def _substitute(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return VARIABLE.sub(lambda m: _lookup(m.group(1), variables), value)
    if isinstance(value, dict):
        return {k: _substitute(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, variables) for v in value]
    return value


def _lookup(name: str, variables: dict[str, str]) -> str:
    if name not in variables:
        raise ValueError(f"Unknown variable ${{{name}}} in scenario suite")
    return variables[name]
