"""M3 exit tests: real apps, real Postgres, real Docker."""

import json

import pytest

from migrator.baseline import BaselineStatus, create_baseline, write_baseline
from migrator.baseline.scenarios import load_rules
from migrator.concepts.extract import build_concept_model
from migrator.concepts.schema_check import check_against_runtime
from migrator.repository import LocalRepository
from tests.conftest import FIXTURES

pytestmark = pytest.mark.docker

SCENARIOS = FIXTURES / "scenarios" / "shop.json"


def tiny_repo(make_repo, name: str, main_py: str, path: str):
    """A dependency-free Python app with a one-request scenario suite."""
    step = {"method": "GET", "path": path}
    project = f'[project]\nname = "{name}"\nversion = "0"\nrequires-python = ">=3.12"\n'
    return make_repo(
        {
            "pyproject.toml": project,
            "main.py": main_py,
            "suite.json": json.dumps({"scenarios": [{"name": name, "steps": [step]}]}),
        }
    )


def rules_file(app: str):
    return FIXTURES / "scenarios" / f"{app}.rules.json"


def test_python_fixture_without_rules_is_unstable_only_because_of_timestamps():
    result = create_baseline(LocalRepository(FIXTURES / "py-fastapi-shop"), SCENARIOS)
    assert result.report.status == BaselineStatus.UNSTABLE
    proposed = {(r.path, r.action) for r in result.report.proposed_rules}
    approved = {(r.path, r.action) for r in load_rules(rules_file("py-fastapi-shop"))}
    assert proposed == approved  # the saved rules are exactly what the app needs


@pytest.mark.parametrize("app", ["py-fastapi-shop", "ts-nestjs-shop"])
def test_fixture_is_stable_with_approved_rules(app, tmp_path):
    result = create_baseline(
        LocalRepository(FIXTURES / app), SCENARIOS, rules_path=rules_file(app), mutants=2
    )
    report = result.report
    assert report.status == BaselineStatus.STABLE, report.differences[:3]
    assert report.scenarios == 10 and report.holdout_scenarios == 2
    assert report.mutation is not None and report.mutation.tested == 2

    write_baseline(result, tmp_path)
    visible = json.loads((tmp_path / "traces.json").read_text())
    holdout = json.loads((tmp_path / "holdout.json").read_text())
    assert len(visible) == 8 and len(holdout) == 2
    assert all(t["holdout"] for t in holdout)
    assert (tmp_path / "app.log").read_text().strip()
    schema = json.loads((tmp_path / "schema.json").read_text())
    assert {"table_name": "users", "type": "UNIQUE", "columns": "email"} in schema["constraints"]
    # Static reading of the ORM code must agree with the real database.
    concepts = build_concept_model(LocalRepository(FIXTURES / app))
    assert check_against_runtime(concepts, schema) == []


PROBE_APP = """
import json, os, socket
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=2).close()
            internet = True
        except OSError:
            internet = False
        body = json.dumps({
            "internet": internet,
            "tz": os.environ.get("TZ"),
            "secret": os.environ.get("MIGRATOR_TEST_SECRET"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.environ["PORT"])), Handler).serve_forever()
"""


def test_running_app_has_no_internet_and_no_host_secrets(make_repo, monkeypatch):
    monkeypatch.setenv("MIGRATOR_TEST_SECRET", "leaked")
    root = tiny_repo(make_repo, "probe", PROBE_APP, "/probe")
    result = create_baseline(LocalRepository(root), root / "suite.json", runs=1)
    assert result.report.status == BaselineStatus.STABLE, result.report.notes
    [trace] = result.traces
    assert trace.steps[0].observed.body == {"internet": False, "tz": "UTC", "secret": None}


def test_app_that_cannot_start_is_reported(make_repo):
    main_py = 'if __name__ == "__main__":\n    raise SystemExit("config missing")\n'
    root = tiny_repo(make_repo, "broken", main_py, "/")
    result = create_baseline(LocalRepository(root), root / "suite.json")
    assert result.report.status == BaselineStatus.FAILED
    assert any("config missing" in note for note in result.report.notes)
