"""Generate a target skeleton that compiles and boots: interface first, logic later (M6)."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from migrator.analysis import analyze
from migrator.concepts.extract import build_concept_model
from migrator.concepts.models import ConceptKind
from migrator.planning.models import MigrationPlan
from migrator.repository import LocalRepository
from migrator.skeleton.fastapi import models, project, routes, schemas
from migrator.skeleton.files import FileBuilder

log = logging.getLogger(__name__)


@dataclass
class Skeleton:
    files: dict[str, str]
    notes: list[str] = field(default_factory=list)


def generate_skeleton(repo: LocalRepository, plan: MigrationPlan) -> Skeleton:
    if plan.target != "python-fastapi":
        raise ValueError(f"No skeleton renderer for target '{plan.target}' yet")
    report = analyze(repo)
    concepts = build_concept_model(repo, report)
    targets = {f.source: f.target for f in plan.files()}
    notes = list(concepts.notes)
    files = FileBuilder()

    has_tables = bool(concepts.of_kind(ConceptKind.TABLE))
    if has_tables:
        project.render_database(files)
    model_modules = models.render_models(concepts, targets, files, notes)
    schema_modules = schemas.render_schemas(concepts, targets, files)
    needs_auth = any(r.attributes["auth"] for r in concepts.of_kind(ConceptKind.ROUTE))
    auth_module = routes.render_auth(concepts, targets, files) if needs_auth else ""
    router_modules = routes.render_routes(concepts, targets, files, schema_modules, auth_module)
    project.render_config(concepts, plan, files)
    project.render_main(router_modules, model_modules, has_tables, files)
    project.render_smoke_test(concepts, files)
    project.render_stubs(plan, files)

    manifests = [m for language in report.inventory.languages for m in language.manifests]
    runtime, dev = project.render_dependencies(manifests, plan.source_language, notes)
    project.render_project(plan, runtime, dev, files, repo.name)
    output = files.render()
    output[".migrator/plan.json"] = plan.model_dump_json(indent=2) + "\n"
    output[".migrator/source-concepts.json"] = concepts.model_dump_json(indent=2) + "\n"
    log.info("Skeleton: %d files, %d notes", len(output), len(notes))
    return Skeleton(files=output, notes=notes)


def write_skeleton(skeleton: Skeleton, out_dir: Path, force: bool = False) -> None:
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise FileExistsError(f"{out_dir} is not empty. Use --force to write into it anyway.")
    for path, content in skeleton.files.items():
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (out_dir / ".migrator" / "notes.json").write_text(json.dumps(skeleton.notes, indent=2) + "\n")
    log.info("Skeleton written to %s", out_dir)
