import json

from migrator.adapters.languages import PythonAdapter, TypeScriptAdapter
from migrator.analysis import analyze
from migrator.repository import LocalRepository
from tests.conftest import FIXTURES


def toolchain_for(root, adapter):
    repo = LocalRepository(root)
    [inventory] = analyze(repo, [adapter]).inventory.languages
    return adapter.toolchain(repo, inventory)


def commands(toolchain):
    return [(s.name, " ".join(s.command), s.network) for s in toolchain.steps]


def test_typescript_fixture_toolchain():
    toolchain = toolchain_for(FIXTURES / "ts-nestjs-shop", TypeScriptAdapter())
    assert commands(toolchain) == [
        ("install", "npm ci --no-audit --no-fund", True),
        ("build", "npm run build", False),
        ("test", "npm test", False),
    ]
    assert toolchain.notes == []


def test_typescript_without_lockfile_or_tests(make_repo):
    root = make_repo(
        {
            "package.json": json.dumps(
                {
                    "scripts": {"test": 'echo "Error: no test specified" && exit 1'},
                    "devDependencies": {"typescript": "5"},
                }
            ),
            "src/a.ts": "export const a = 1;",
        }
    )
    toolchain = toolchain_for(root, TypeScriptAdapter())
    assert commands(toolchain) == [
        ("install", "npm install --no-audit --no-fund", True),
        ("build", "npx --no-install tsc --noEmit", False),
    ]
    assert "No package-lock.json, so install is not reproducible" in toolchain.notes
    assert "No test command found" in toolchain.notes


def test_python_fixture_toolchain():
    toolchain = toolchain_for(FIXTURES / "py-fastapi-shop", PythonAdapter())
    assert commands(toolchain) == [
        ("install", "uv sync --frozen", True),
        ("build", r".venv/bin/python -m compileall -q -x \.venv .", False),
        ("test", ".venv/bin/python -m pytest -q -p no:cacheprovider", False),
    ]


def test_python_requirements_project(make_repo):
    root = make_repo(
        {
            "requirements.txt": "fastapi\n",
            "requirements-dev.txt": "pytest\n",
            "app.py": "x = 1\n",
        }
    )
    toolchain = toolchain_for(root, PythonAdapter())
    assert [c for _, c, _ in commands(toolchain)][:3] == [
        "uv venv",
        "uv pip install -r requirements-dev.txt",
        "uv pip install -r requirements.txt",
    ]
    assert toolchain.steps[-1].name == "test"


def test_python_without_manifest(make_repo):
    toolchain = toolchain_for(make_repo({"app.py": "x = 1\n"}), PythonAdapter())
    assert toolchain.steps == []
    assert any("cannot install" in note for note in toolchain.notes)


def test_only_install_steps_get_network():
    for fixture, adapter in [
        ("ts-nestjs-shop", TypeScriptAdapter()),
        ("py-fastapi-shop", PythonAdapter()),
    ]:
        for step in toolchain_for(FIXTURES / fixture, adapter).steps:
            assert step.network == (step.name == "install")
