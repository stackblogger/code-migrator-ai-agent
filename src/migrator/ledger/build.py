"""Build the ledger by matching source concepts to target concepts on their canonical key."""

import json
import logging
from collections import defaultdict
from pathlib import Path

from migrator.concepts.keys import snake_case
from migrator.concepts.models import ConceptKind, ConceptModel, ConceptNode
from migrator.ledger.models import Ledger, LedgerRow, LedgerStatus, Place, Waiver

log = logging.getLogger(__name__)

# Attributes that must be equal for an item to count as mapped.
COMPARED = {
    ConceptKind.ROUTE: ["status", "auth"],
    ConceptKind.COLUMN: ["nullable", "unique", "primary_key", "references"],
    ConceptKind.INPUT_FIELD: ["constraints", "required"],
    ConceptKind.TABLE: [],
    ConceptKind.ERROR: [],
    ConceptKind.ENV_VAR: [],
}
Group = dict[tuple[ConceptKind, str], list[ConceptNode]]


def build_ledger(
    source: ConceptModel, target: ConceptModel | None, waivers: list[Waiver] | None = None
) -> Ledger:
    waivers_by_key = {w.key: w for w in waivers or []}
    source_groups = _group(source)
    target_groups = _group(target) if target else {}

    rows = []
    for (kind, key), nodes in sorted(source_groups.items()):
        matches = target_groups.get((kind, key), [])
        row = _row(kind, key, nodes, matches)
        if not matches:
            row.hint = _hint(kind, key, target_groups) if target else "target not generated yet"
        waiver = waivers_by_key.get(key)
        if waiver and row.status in (LedgerStatus.MISSING, LedgerStatus.MISMATCH):
            row.status = LedgerStatus.WAIVED
            row.waiver = f"{waiver.reason} (approved by {waiver.approved_by})"
        rows.append(row)

    extra = [
        LedgerRow(kind=kind, key=key, status=LedgerStatus.MISSING, source=[], target=_places(nodes))
        for (kind, key), nodes in sorted(target_groups.items())
        if (kind, key) not in source_groups
    ]
    used = {r.key for r in rows if r.status == LedgerStatus.WAIVED}
    ledger = Ledger(
        source_repo=source.repo,
        target_repo=target.repo if target else None,
        rows=rows,
        extra_in_target=extra,
        unused_waivers=[w for w in waivers or [] if w.key not in used],
    )
    log.info(
        "Ledger %s -> %s: %d rows (%d mapped, %d mismatch, %d missing, %d waived), %d extra",
        source.repo,
        ledger.target_repo,
        len(rows),
        ledger.count(LedgerStatus.MAPPED),
        ledger.count(LedgerStatus.MISMATCH),
        ledger.count(LedgerStatus.MISSING),
        ledger.count(LedgerStatus.WAIVED),
        len(extra),
    )
    for waiver in ledger.unused_waivers:
        log.warning("Waiver for '%s' matches nothing, please remove it", waiver.key)
    return ledger


def load_waivers(path: Path | None) -> list[Waiver]:
    if path is None:
        return []
    return [Waiver.model_validate(item) for item in json.loads(path.read_text())]


def _row(
    kind: ConceptKind, key: str, nodes: list[ConceptNode], matches: list[ConceptNode]
) -> LedgerRow:
    if not matches:
        return LedgerRow(kind=kind, key=key, status=LedgerStatus.MISSING, source=_places(nodes))
    differences = []
    for attribute in COMPARED[kind]:
        mine, theirs = nodes[0].attributes.get(attribute), matches[0].attributes.get(attribute)
        if mine != theirs:
            differences.append(f"{attribute}: {mine} vs {theirs}")
    status = LedgerStatus.MISMATCH if differences else LedgerStatus.MAPPED
    return LedgerRow(
        kind=kind,
        key=key,
        status=status,
        source=_places(nodes),
        target=_places(matches),
        differences=differences,
    )


def _hint(kind: ConceptKind, key: str, target_groups: Group) -> str | None:
    """Suggest a target item with nearly the same name, e.g. userId vs user_id."""
    wanted = snake_case(key).replace("-", "_")
    for other_kind, other_key in target_groups:
        if other_kind == kind and snake_case(other_key).replace("-", "_") == wanted:
            return f"maybe '{other_key}' (same name in another style)"
    return None


def _group(model: ConceptModel) -> Group:
    groups: Group = defaultdict(list)
    for node in model.nodes:
        if node.kind in COMPARED:
            groups[(node.kind, node.key)].append(node)
    return groups


def _places(nodes: list[ConceptNode]) -> list[Place]:
    return [Place(name=n.name, file=n.file, line=n.line) for n in nodes]
