"""The skeleton is checked with our own tools: it must compile, and the ledger from the
source to the skeleton must map everything except business logic (the errors)."""

import pytest

from migrator.concepts.extract import build_concept_model
from migrator.ledger import LedgerStatus, build_ledger
from migrator.planning.planner import build_plan
from migrator.repository import LocalRepository
from migrator.skeleton.generate import generate_skeleton, write_skeleton
from tests.conftest import FIXTURES

SOURCE = LocalRepository(FIXTURES / "ts-nestjs-shop")


@pytest.fixture(scope="module")
def skeleton_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("skeleton")
    write_skeleton(generate_skeleton(SOURCE, build_plan(SOURCE)), out, force=True)
    return out


def test_every_python_file_compiles(skeleton_dir):
    files = list(skeleton_dir.rglob("*.py"))
    assert len(files) > 15
    for file in files:
        compile(file.read_text(), str(file), "exec")


def test_generated_code_keeps_source_contract(skeleton_dir):
    models = (skeleton_dir / "app/orders/models.py").read_text()
    assert 'mapped_column("userId", Integer, ForeignKey("users.id"), nullable=False)' in models
    assert "Numeric(10, 2)" in models
    router = (skeleton_dir / "app/orders/router.py").read_text()
    assert '@router.post("/orders/{id}/cancel", status_code=201)' in router
    assert "def list_route(" in router  # `list` would hide the builtin
    schemas = (skeleton_dir / "app/users/schemas.py").read_text()
    assert "email: EmailStr" in schemas and "Field(min_length=8)" in schemas
    assert "MIGRATOR-STUB" in (skeleton_dir / "app/orders/service.py").read_text()


def test_ledger_source_to_skeleton_maps_everything_but_logic(skeleton_dir):
    source = build_concept_model(SOURCE)
    target = build_concept_model(LocalRepository(skeleton_dir))
    ledger = build_ledger(source, target)
    not_mapped = {r.key: r.status for r in ledger.rows if r.status != LedgerStatus.MAPPED}
    # Only errors raised by business logic are left for M6. 401 is already there (auth stub).
    assert not_mapped == {
        "HTTP 400": LedgerStatus.MISSING,
        "HTTP 404": LedgerStatus.MISSING,
        "HTTP 409": LedgerStatus.MISSING,
    }
    assert [r.key for r in ledger.extra_in_target] == ["HTTP 501"]  # the stub marker


def test_refuses_to_overwrite(tmp_path):
    (tmp_path / "keep.txt").write_text("mine")
    with pytest.raises(FileExistsError):
        write_skeleton(generate_skeleton(SOURCE, build_plan(SOURCE)), tmp_path)
