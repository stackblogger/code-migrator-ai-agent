"""Build the Canonical Concept Model for a repo by running every matching framework adapter."""

import logging

from migrator.adapters.frameworks import default_framework_adapters, load_files
from migrator.adapters.languages import default_adapters
from migrator.analysis import analyze
from migrator.concepts.models import ConceptKind, ConceptModel, ConceptNode
from migrator.core.models import RepoReport
from migrator.repository import LocalRepository

log = logging.getLogger(__name__)


def build_concept_model(repo: LocalRepository, report: RepoReport | None = None) -> ConceptModel:
    report = report or analyze(repo)
    languages = {adapter.name: adapter for adapter in default_adapters()}
    nodes: list[ConceptNode] = []
    notes: list[str] = []
    used: list[str] = []

    for inventory in report.inventory.languages:
        frameworks = [f for f in default_framework_adapters() if f.detect(inventory)]
        if not frameworks:
            notes.append(
                f"No framework adapter matched the {inventory.language} code, "
                "so routes and tables were not extracted"
            )
            continue
        files = load_files(repo, inventory.source_files, languages[inventory.language])
        for framework in frameworks:
            extraction = framework.extract(files)
            log.info(
                "%s: %d concepts, %d notes",
                framework.name,
                len(extraction.nodes),
                len(extraction.notes),
            )
            nodes += extraction.nodes
            notes += extraction.notes
            used.append(framework.name)

    nodes += _env_vars(report)
    nodes.sort(key=lambda n: (n.kind, n.key, n.file, n.line))
    for note in notes:
        log.warning(note)
    counts = {kind.value: sum(n.kind == kind for n in nodes) for kind in ConceptKind}
    log.info("Concept model for '%s': %s", repo.name, counts)
    return ConceptModel(repo=repo.name, frameworks=used, nodes=nodes, notes=notes)


def _env_vars(report: RepoReport) -> list[ConceptNode]:
    return [
        ConceptNode(
            kind=ConceptKind.ENV_VAR,
            key=name,
            name=name,
            file=files[0],
            line=0,
            framework="core",
            attributes={"files": files},
        )
        for name, files in report.inventory.env_vars.items()
    ]
