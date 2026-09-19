"""Ask the LLM for an idiomatic file layout. Its answer is checked by code; if it stays
invalid after one retry, we keep the convention layout and say so in the plan notes."""

import json
import logging

from pydantic import BaseModel

from migrator.llm import LLMClient, LLMError, as_data, load_prompt
from migrator.planning.layout import VALID_TARGET
from migrator.planning.models import FileRole, MigrationUnit

log = logging.getLogger(__name__)


class FileMapping(BaseModel):
    source: str
    target: str | None
    reason: str


class UnitRisk(BaseModel):
    unit_id: str
    risks: list[str]


class MappingAnswer(BaseModel):
    files: list[FileMapping]
    unit_risks: list[UnitRisk]


def llm_mapping(
    client: LLMClient, units: list[MigrationUnit], source_stack: str, target_stack: str
) -> tuple[MappingAnswer | None, list[str]]:
    """Returns the answer (or None) and notes about what happened."""
    prompt = load_prompt("plan_mapping")
    units_data = as_data(json.dumps([_unit_view(u) for u in units], indent=1))
    values = {"source_stack": source_stack, "target_stack": target_stack, "units": units_data}

    errors: list[str] = []
    for attempt in (1, 2):
        if errors:  # second try: tell the model what was wrong
            values["units"] = (
                units_data
                + "\n\nYour previous answer had these problems, fix them:\n"
                + "\n".join(errors)
            )
        try:
            answer = client.structured("plan_mapping", prompt, values, MappingAnswer)
        except LLMError as error:
            return None, [f"LLM mapping failed, using convention layout: {error}"]
        errors = validate_mapping(units, answer)
        if not errors:
            return answer, []
        log.warning("LLM mapping attempt %d has %d problems: %s", attempt, len(errors), errors[:3])
    return None, [f"LLM mapping rejected, using convention layout: {'; '.join(errors[:5])}"]


def validate_mapping(units: list[MigrationUnit], answer: MappingAnswer) -> list[str]:
    roles = {f.source: f.role for u in units for f in u.files}
    sources = [m.source for m in answer.files]
    problems = [
        f"{s} is listed more than once"
        for s in sorted({s for s in sources if sources.count(s) > 1})
    ]
    problems += [f"{s} is missing" for s in sorted(roles.keys() - set(sources))]
    problems += [f"{s} is not a source file" for s in sorted(set(sources) - roles.keys())]
    for mapping in answer.files:
        role = roles.get(mapping.source)
        if mapping.target is None:
            if role != FileRole.WIRING:
                problems.append(f"{mapping.source} ({role}) needs a target file")
        elif not VALID_TARGET.match(mapping.target):
            problems.append(f"{mapping.source}: target '{mapping.target}' is not a valid path")
        elif role == FileRole.ENTRYPOINT and mapping.target != "app/main.py":
            problems.append(f"{mapping.source} is the entry point and must map to app/main.py")
        elif (role == FileRole.TEST) != mapping.target.startswith("tests/"):
            problems.append(f"{mapping.source}: tests go under tests/, app code under app/")
    unit_ids = {u.id for u in units}
    problems += [
        f"unknown unit id {r.unit_id}" for r in answer.unit_risks if r.unit_id not in unit_ids
    ]
    return problems


def _unit_view(unit: MigrationUnit) -> dict:
    return {
        "unit": unit.id,
        "depends_on": unit.depends_on,
        "files": [
            {"source": f.source, "role": f.role.value, "proposed_target": f.target}
            for f in unit.files
        ],
        "concepts": unit.concepts,
    }
