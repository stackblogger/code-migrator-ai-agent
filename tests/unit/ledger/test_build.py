from migrator.concepts.models import ConceptKind, ConceptModel, ConceptNode
from migrator.ledger import LedgerStatus, Waiver, build_ledger


def node(kind: ConceptKind, key: str, **attributes) -> ConceptNode:
    return ConceptNode(
        kind=kind, key=key, name=key, file="f", line=1, framework="x", attributes=attributes
    )


def model(name: str, *nodes: ConceptNode) -> ConceptModel:
    return ConceptModel(repo=name, frameworks=[], nodes=list(nodes))


ROUTE = ConceptKind.ROUTE
COLUMN = ConceptKind.COLUMN
SOURCE = model(
    "src",
    node(ROUTE, "GET /a", status=200, auth=True),
    node(ROUTE, "POST /b", status=201, auth=False),
    node(COLUMN, "t.userId", nullable=False, unique=False, primary_key=False),
    node(ConceptKind.ERROR, "HTTP 404", status=404),
    node(ConceptKind.ERROR, "HTTP 404", status=404),  # raised in two places -> one row
    node(ConceptKind.PROVIDER, "SomeService"),  # info only, not in the ledger
)
TARGET = model(
    "dst",
    node(ROUTE, "GET /a", status=200, auth=True),
    node(ROUTE, "POST /b", status=200, auth=False),
    node(COLUMN, "t.user_id", nullable=False, unique=False, primary_key=False),
    node(ConceptKind.ERROR, "HTTP 404", status=404),
)


def rows(ledger):
    return {r.key: r for r in ledger.rows}


def test_statuses_hints_and_extra():
    ledger = build_ledger(SOURCE, TARGET)
    found = rows(ledger)
    assert set(found) == {"GET /a", "POST /b", "t.userId", "HTTP 404"}
    assert found["GET /a"].status == LedgerStatus.MAPPED
    assert found["POST /b"].status == LedgerStatus.MISMATCH
    assert found["POST /b"].differences == ["status: 201 vs 200"]
    assert found["t.userId"].status == LedgerStatus.MISSING
    assert "t.user_id" in (found["t.userId"].hint or "")
    assert len(found["HTTP 404"].source) == 2
    assert [r.key for r in ledger.extra_in_target] == ["t.user_id"]
    assert not ledger.complete


def test_waivers_make_it_complete_and_unused_ones_are_reported():
    waivers = [
        Waiver(key="POST /b", reason="known", approved_by="me"),
        Waiver(key="t.userId", reason="renamed", approved_by="me"),
        Waiver(key="GET /a", reason="not needed", approved_by="me"),  # row is mapped, so unused
        Waiver(key="nothing", reason="typo", approved_by="me"),
    ]
    ledger = build_ledger(SOURCE, TARGET, waivers)
    assert ledger.complete
    assert rows(ledger)["POST /b"].waiver == "known (approved by me)"
    assert {w.key for w in ledger.unused_waivers} == {"GET /a", "nothing"}


def test_without_target_everything_is_missing():
    ledger = build_ledger(SOURCE, None)
    assert all(r.status == LedgerStatus.MISSING for r in ledger.rows)
    assert all(r.hint == "target not generated yet" for r in ledger.rows)
