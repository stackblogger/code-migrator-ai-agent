from migrator.adapters.languages import PythonAdapter, TypeScriptAdapter
from migrator.analysis import analyze
from migrator.baseline.runspec import build_run_spec
from migrator.repository import LocalRepository
from tests.conftest import FIXTURES


def spec_for(root, adapter, suite_env=None):
    repo = LocalRepository(root)
    report = analyze(repo, [adapter])
    [inventory] = report.inventory.languages
    return build_run_spec(
        repo,
        adapter.toolchain(repo, inventory),
        adapter.launch_info(repo, inventory),
        set(report.inventory.env_vars),
        suite_env or {},
    )


def test_typescript_fixture_spec():
    spec = spec_for(FIXTURES / "ts-nestjs-shop", TypeScriptAdapter(), {"JWT_SECRET": "s"})
    assert spec.command == ["npm", "start"]
    assert spec.services == ["postgres"]
    assert spec.env["DATABASE_URL"] == "postgres://app:app@db:5432/app"
    assert spec.env["PORT"] == "8080"
    assert spec.env["TZ"] == "UTC"
    assert spec.env["JWT_SECRET"] == "s"


def test_python_fixture_spec():
    spec = spec_for(FIXTURES / "py-fastapi-shop", PythonAdapter())
    assert spec.command == [".venv/bin/python", "-m", "app.main"]
    assert spec.env["DATABASE_URL"] == "postgresql+psycopg://app:app@db:5432/app"
    assert spec.env["PYTHONHASHSEED"] == "0"


def test_override_file_wins(make_repo):
    root = make_repo(
        {
            "requirements.txt": "flask\n",
            "server.py": "import os\nPORT = os.getenv('PORT')\n",
            ".migrator.toml": (
                '[run]\ncommand = ["python", "server.py"]\nport = 5000\nhealth_path = "/health"\n'
                '[run.env]\nFLAG = "1"\n'
            ),
        }
    )
    spec = spec_for(root, PythonAdapter())
    assert spec.command == ["python", "server.py"]
    assert spec.port == 5000
    assert spec.env["PORT"] == "5000"
    assert spec.env["FLAG"] == "1"
    assert spec.health_path == "/health"


def test_notes_when_things_are_missing(make_repo):
    root = make_repo({"requirements.txt": "requests\npsycopg\n", "lib.py": "x = 1\n"})
    spec = spec_for(root, PythonAdapter())
    assert spec.command is None
    notes = " ".join(spec.notes)
    assert "No entry point found" in notes
    assert "Uses 'requests'" in notes
    assert "no database URL env var" in notes
    assert "No port env var found" in notes
