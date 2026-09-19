"""Turn the dependency graph into ordered migration units.

One unit = one strongly connected group of files from the M1 graph (usually one file).
Units come in dependency order, so nothing is migrated before the things it uses.
"""

from collections import defaultdict

from migrator.concepts.models import ConceptKind, ConceptModel
from migrator.core.models import RepoReport
from migrator.planning.models import FilePlan, FileRole, MigrationUnit

# When a file has several roles, the first one in this list wins.
ROLE_ORDER = [
    FileRole.TEST,
    FileRole.ENTRYPOINT,
    FileRole.API,
    FileRole.MODEL,
    FileRole.SCHEMA,
    FileRole.GUARD,
    FileRole.SERVICE,
    FileRole.WIRING,
    FileRole.CONFIG,
    FileRole.UTILITY,
]


def build_units(report: RepoReport, concepts: ConceptModel) -> list[MigrationUnit]:
    roles = _file_roles(report, concepts)
    keys_by_file: dict[str, list[str]] = defaultdict(list)
    for node in concepts.nodes:
        keys_by_file[node.file].append(f"{node.kind.value}:{node.key}")

    unit_of: dict[str, str] = {}
    units: list[MigrationUnit] = []
    edges = defaultdict(set)
    for edge in report.graph.edges:
        edges[edge.source].add(edge.target)

    for number, group in enumerate(report.graph.migration_order, start=1):
        unit_id = f"u{number:02d}"
        for file in group:
            unit_of[file] = unit_id
        depends = sorted(
            {unit_of[t] for f in group for t in edges[f] if unit_of.get(t, unit_id) != unit_id}
        )
        units.append(
            MigrationUnit(
                id=unit_id,
                files=[
                    FilePlan(source=f, role=roles[f], target=None, reason="not mapped yet")
                    for f in group
                ],
                depends_on=depends,
                concepts=sorted(k for f in group for k in keys_by_file[f]),
            )
        )
    return units


def check_order(units: list[MigrationUnit]) -> list[str]:
    """Every unit must come after the units it depends on."""
    seen: set[str] = set()
    problems = []
    for unit in units:
        for dependency in unit.depends_on:
            if dependency not in seen:
                problems.append(f"{unit.id} comes before its dependency {dependency}")
        seen.add(unit.id)
    return problems


def _file_roles(report: RepoReport, concepts: ConceptModel) -> dict[str, FileRole]:
    found: dict[str, set[FileRole]] = defaultdict(set)
    for language in report.inventory.languages:
        for file in language.test_files:
            found[file].add(FileRole.TEST)
        for file in language.entry_points:
            found[file].add(FileRole.ENTRYPOINT)
    for node in concepts.nodes:
        role = _role_for(node)
        if node.kind == ConceptKind.ENV_VAR:
            for file in node.attributes.get("files", []):
                found[file].add(FileRole.CONFIG)
        elif role:
            found[node.file].add(role)

    roles = {}
    for file in report.graph.nodes:
        options = found.get(file, set())
        roles[file] = next((r for r in ROLE_ORDER if r in options), FileRole.UTILITY)
    return roles


def _role_for(node) -> FileRole | None:
    if node.kind == ConceptKind.ROUTE:
        return FileRole.API
    if node.kind in (ConceptKind.TABLE, ConceptKind.COLUMN):
        return FileRole.MODEL
    if node.kind == ConceptKind.INPUT_FIELD:
        return FileRole.SCHEMA
    if node.kind == ConceptKind.PROVIDER:
        return FileRole.GUARD if node.attributes.get("guard") else FileRole.SERVICE
    if node.kind == ConceptKind.MODULE:
        return FileRole.WIRING
    return None
