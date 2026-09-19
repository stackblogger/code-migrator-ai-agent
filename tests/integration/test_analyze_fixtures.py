import pytest

from migrator.analysis import analyze
from migrator.repository import LocalRepository
from tests.conftest import FIXTURES, assert_snapshot


@pytest.mark.parametrize("name", ["ts-nestjs-shop", "py-fastapi-shop"])
def test_report_snapshot(name):
    report = analyze(LocalRepository(FIXTURES / name))
    assert_snapshot(name, report.model_dump(mode="json"))


def test_typescript_fixture():
    report = analyze(LocalRepository(FIXTURES / "ts-nestjs-shop"))
    [ts] = report.inventory.languages
    assert ts.language == "typescript"
    assert ts.entry_points == ["src/main.ts"]
    assert ts.test_files == ["test/orders.service.spec.ts"]
    assert ts.tools["test"] == ["jest"]
    assert report.graph.cycles == [["src/orders/order.entity.ts", "src/users/user.entity.ts"]]
    assert set(report.inventory.env_vars) == {
        "DATABASE_URL",
        "JWT_EXPIRES_IN",
        "JWT_SECRET",
        "PORT",
    }
    assert report.warnings == []

    order = report.graph.migration_order
    position = {f: i for i, group in enumerate(order) for f in group}
    assert position["src/users/user.entity.ts"] < position["src/users/users.service.ts"]
    assert position["src/users/users.service.ts"] < position["src/orders/orders.service.ts"]
    assert position["src/orders/orders.service.ts"] < position["src/orders/orders.controller.ts"]

    controller = next(s for s in report.symbols if s.name == "OrdersController")
    assert controller.decorators == ["UseGuards", "Controller"]


def test_python_fixture():
    report = analyze(LocalRepository(FIXTURES / "py-fastapi-shop"))
    [py] = report.inventory.languages
    assert py.language == "python"
    assert py.entry_points == ["app/main.py"]
    assert py.tools["test"] == ["pytest"]
    assert report.graph.cycles == [["app/orders/models.py", "app/users/models.py"]]
    cycle_edges = [
        e
        for e in report.graph.edges
        if e.source.endswith("models.py") and e.target.endswith("models.py")
    ]
    assert cycle_edges and all(e.type_only for e in cycle_edges)
    assert report.warnings == []


def test_warns_about_undeclared_and_unresolved(make_repo):
    root = make_repo(
        {
            "requirements.txt": "fastapi\n",
            "app/__init__.py": "",
            "app/main.py": "import requests\nfrom app.missing import x\nfrom .gone import y\n",
        }
    )
    warnings = analyze(LocalRepository(root)).warnings
    assert any("'requests' is imported" in w for w in warnings)
    assert any("cannot resolve 'app.missing'" in w for w in warnings)
    assert any("cannot resolve '.gone'" in w for w in warnings)


def test_empty_repo_is_reported(make_repo):
    report = analyze(LocalRepository(make_repo({"README.md": "hi"})))
    assert report.warnings == ["No supported language found in this repository."]
