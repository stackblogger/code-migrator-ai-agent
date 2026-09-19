import io
from pathlib import Path

import pytest

from migrator.repository import LocalRepository
from migrator.sandbox import CommandNotAllowedError, DockerSandbox, Limits
from migrator.sandbox.docker import _read_tail, check_allowed
from migrator.sandbox.workspace import Workspace


@pytest.mark.parametrize(
    "command", [["npm", "test"], [".venv/bin/python", "-m", "pytest"], ["uv", "sync"]]
)
def test_allowed_commands(command):
    check_allowed(command)


@pytest.mark.parametrize(
    "command",
    [[], ["sh", "-c", "rm -rf /"], ["bash"], ["/bin/sh"], ["curl", "evil.com"], ["npm && sh"]],
)
def test_blocked_commands(command):
    with pytest.raises(CommandNotAllowedError):
        check_allowed(command)


def test_run_checks_allowlist_before_docker(tmp_path):
    sandbox = DockerSandbox(docker="/definitely/not/docker")
    with pytest.raises(CommandNotAllowedError):
        sandbox.run("any-image", ["sh", "-c", "id"], tmp_path)


def test_docker_args_lock_things_down(tmp_path):
    args = DockerSandbox(Limits(memory="1g", pids=64)).docker_args("c1", "img", tmp_path, False)
    joined = " ".join(args)
    for expected in [
        "--read-only",
        "--init",
        "--network none",
        "--memory 1g",
        "--memory-swap 1g",
        "--pids-limit 64",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
    ]:
        assert expected in joined
    assert args[-1] == "img"
    assert f"{tmp_path.resolve()}:/workspace" in args
    install_args = DockerSandbox().docker_args("c2", "img", tmp_path, True)
    assert "--network bridge" in " ".join(install_args)


def test_output_keeps_the_tail():
    output, truncated = _read_tail(io.BytesIO(b"a" * 50 + b"END"), max_bytes=10)
    assert truncated is True
    assert output.endswith("END") and len(output) == 10
    assert _read_tail(io.BytesIO(b"short"), max_bytes=10) == ("short", False)


def test_workspace_is_a_copy_without_secrets(make_repo):
    root = make_repo(
        {
            "src/a.py": "x = 1",
            ".env": "API_KEY=real-secret",
            ".env.example": "API_KEY=",
            "node_modules/x/index.js": "",
        }
    )
    with Workspace(LocalRepository(root)) as workspace:
        copy = workspace.path
        assert (copy / "src/a.py").read_text() == "x = 1"
        assert (copy / ".env.example").exists()
        assert not (copy / ".env").exists()
        assert not (copy / "node_modules").exists()
        assert workspace.skipped == [".env"]
        (copy / "src/a.py").write_text("changed")
    assert (root / "src/a.py").read_text() == "x = 1"  # original untouched
    assert not Path(copy).exists()  # cleaned up
