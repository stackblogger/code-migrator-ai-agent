"""M4 exit tests: surface extracted on both stacks, ledger complete for the fixture pair."""

from migrator.concepts.extract import build_concept_model
from migrator.concepts.models import ConceptKind
from migrator.ledger import LedgerStatus, build_ledger, load_waivers
from migrator.repository import LocalRepository
from tests.conftest import FIXTURES

WAIVERS = FIXTURES / "ledger" / "ts-to-py.waivers.json"


def model(app: str):
    return build_concept_model(LocalRepository(FIXTURES / app))


def surface(app: str) -> dict:
    m = model(app)
    return {
        "routes": {
            n.key: (n.attributes["status"], n.attributes["auth"])
            for n in m.of_kind(ConceptKind.ROUTE)
        },
        "tables": sorted(n.key for n in m.of_kind(ConceptKind.TABLE)),
        "columns": len(m.of_kind(ConceptKind.COLUMN)),
        "notes": m.notes,
    }


def test_typescript_surface():
    s = surface("ts-nestjs-shop")
    assert s["routes"] == {
        "GET /orders": (200, True),
        "GET /users/{}": (200, True),
        "POST /orders": (201, True),
        "POST /orders/{}/cancel": (201, True),
        "POST /users": (201, False),
    }
    assert s["tables"] == ["orders", "users"] and s["columns"] == 11
    # Enum default (OrderStatus.Pending) is not a plain value, so it is reported, not guessed.
    assert s["notes"] == ["typeorm: default of orders.status is not a plain value, set it by hand"]


def test_python_surface():
    s = surface("py-fastapi-shop")
    assert s["routes"]["POST /orders/{}/cancel"] == (200, True)
    assert set(s["routes"]) == set(surface("ts-nestjs-shop")["routes"])
    assert s["tables"] == ["orders", "users"] and s["columns"] == 11
    assert s["notes"] == []


def test_ledger_finds_exactly_the_real_differences():
    ledger = build_ledger(model("ts-nestjs-shop"), model("py-fastapi-shop"))
    problems = {r.key: r.status for r in ledger.rows if r.status != LedgerStatus.MAPPED}
    assert problems == {
        "POST /orders/{}/cancel": LedgerStatus.MISMATCH,
        "POST /orders body.total": LedgerStatus.MISMATCH,
        "orders.userId": LedgerStatus.MISSING,
    }
    assert [r.key for r in ledger.extra_in_target] == ["orders.user_id"]
    assert len(ledger.rows) == 30


def test_ledger_is_complete_with_fixture_waivers():
    ledger = build_ledger(model("ts-nestjs-shop"), model("py-fastapi-shop"), load_waivers(WAIVERS))
    assert ledger.complete
    assert ledger.count(LedgerStatus.WAIVED) == 3 and ledger.unused_waivers == []
