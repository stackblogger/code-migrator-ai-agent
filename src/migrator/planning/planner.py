"""Build the migration plan: ordered units + a target file for every source file."""

import logging

from migrator.analysis import analyze
from migrator.concepts.extract import build_concept_model
from migrator.llm import LLMClient
from migrator.planning.layout import fastapi_target
from migrator.planning.llm_mapping import llm_mapping
from migrator.planning.models import MigrationPlan
from migrator.planning.units import build_units, check_order
from migrator.repository import LocalRepository

log = logging.getLogger(__name__)

SUPPORTED_TARGETS = {"python-fastapi": ("Python + FastAPI + SQLAlchemy + Pydantic", fastapi_target)}


def build_plan(
    repo: LocalRepository, target: str = "python-fastapi", llm: LLMClient | None = None
) -> MigrationPlan:
    if target not in SUPPORTED_TARGETS:
        raise ValueError(
            f"Target '{target}' is not supported yet. Supported: {sorted(SUPPORTED_TARGETS)}"
        )
    target_stack, layout = SUPPORTED_TARGETS[target]
    report = analyze(repo)
    concepts = build_concept_model(repo, report)
    units = build_units(report, concepts)
    for unit in units:
        for file in unit.files:
            file.target, file.reason = layout(file.role, file.source)

    source_language = (
        report.inventory.languages[0].language if report.inventory.languages else "unknown"
    )
    notes = list(concepts.notes)
    mapped_by = "convention"
    if llm is not None:
        source_stack = f"{source_language} ({', '.join(concepts.frameworks) or 'no framework'})"
        answer, llm_notes = llm_mapping(llm, units, source_stack, target_stack)
        notes += llm_notes
        if answer is not None:
            chosen = {m.source: m for m in answer.files}
            risks = {r.unit_id: r.risks for r in answer.unit_risks}
            for unit in units:
                unit.risks = risks.get(unit.id, [])
                for file in unit.files:
                    file.target, file.reason = (
                        chosen[file.source].target,
                        chosen[file.source].reason,
                    )
            mapped_by = f"llm:{llm.settings.model_for('default')}"

    problems = check_order(units)
    if problems:  # built from a topological order, so this means a bug in our code
        raise RuntimeError(f"Plan order is wrong: {problems}")
    plan = MigrationPlan(
        source_repo=repo.name,
        source_language=source_language,
        source_frameworks=concepts.frameworks,
        target=target,
        units=units,
        mapped_by=mapped_by,
        llm_calls=llm.calls if llm else [],
        notes=notes,
    )
    log.info("Plan: %d units, %d files, mapped by %s", len(units), len(plan.files()), mapped_by)
    return plan
