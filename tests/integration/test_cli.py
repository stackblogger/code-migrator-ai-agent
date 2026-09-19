import json

from migrator.cli import main
from tests.conftest import FIXTURES


def test_analyze_command(tmp_path, capsys):
    out = tmp_path / "report.json"
    assert main(["analyze", str(FIXTURES / "ts-nestjs-shop"), "--out", str(out)]) == 0
    assert "Cycles: 1" in capsys.readouterr().out
    assert json.loads(out.read_text())["inventory"]["repo_name"] == "ts-nestjs-shop"


def test_deps_command(capsys):
    repo = str(FIXTURES / "py-fastapi-shop")
    assert main(["deps", repo, "app/orders/service.py"]) == 0
    output = capsys.readouterr().out
    assert "app/users/service.py" in output
    assert "app/orders/models.py" in output


def test_bad_input_returns_error(capsys):
    assert main(["analyze", "/does/not/exist"]) == 1
    assert main(["deps", str(FIXTURES / "py-fastapi-shop"), "nope.py"]) == 1


def test_verify_exit_code_follows_result(monkeypatch, capsys):
    from migrator import cli
    from migrator.sandbox import RunStatus, SandboxRun

    def fake_verify(status):
        run = SandboxRun(language="python", image="img", status=status, steps=[])
        return lambda repo, keep_workspace: [run]

    repo = str(FIXTURES / "py-fastapi-shop")
    monkeypatch.setattr(cli, "verify_repo", fake_verify(RunStatus.PASSED))
    assert main(["verify", repo]) == 0
    monkeypatch.setattr(cli, "verify_repo", fake_verify(RunStatus.INCOMPLETE))
    assert main(["verify", repo]) == 1
    assert "Result: INCOMPLETE" in capsys.readouterr().out
