"""Real Docker tests: each one tries to break out of, or overload, the sandbox."""

import subprocess

import pytest

from migrator.adapters.languages.python.toolchain import PYTHON_IMAGE
from migrator.sandbox import DockerSandbox, Limits
from migrator.sandbox.docker import LABEL

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module", autouse=True)
def pull_image():
    DockerSandbox().ensure_image(PYTHON_IMAGE)


def run_python(tmp_path, code: str, limits: Limits | None = None):
    return DockerSandbox(limits).run(PYTHON_IMAGE, ["python", "-c", code], tmp_path)


def test_runs_as_non_root(tmp_path):
    result = run_python(tmp_path, "import os; print(os.getuid())")
    assert result.ok
    assert result.output.strip() != "0"


def test_no_network(tmp_path):
    code = "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)"
    assert not run_python(tmp_path, code).ok


def test_root_filesystem_is_read_only_but_workspace_is_writable(tmp_path):
    assert not run_python(tmp_path, "open('/etc/hacked', 'w')").ok
    assert run_python(tmp_path, "open('/workspace/ok.txt', 'w').write('hi')").ok
    assert (tmp_path / "ok.txt").read_text() == "hi"


def test_host_paths_are_not_visible(tmp_path):
    code = f"import os, sys; sys.exit(1 if os.path.exists({str(tmp_path)!r}) else 0)"
    assert run_python(tmp_path, code).ok


def test_host_env_vars_do_not_leak(tmp_path, monkeypatch):
    monkeypatch.setenv("MIGRATOR_TEST_SECRET", "leaked")
    result = run_python(tmp_path, "import os; print(os.environ.get('MIGRATOR_TEST_SECRET'))")
    assert result.output.strip() == "None"


def test_memory_limit(tmp_path):
    result = run_python(tmp_path, "x = b'x' * (512 * 1024 * 1024)", Limits(memory="128m"))
    assert not result.ok
    assert result.oom_killed or result.exit_code == 137


def test_process_limit(tmp_path):
    code = (
        "import threading, time\n"
        "for _ in range(200): threading.Thread(target=time.sleep, args=(5,)).start()"
    )
    assert not run_python(tmp_path, code, Limits(pids=32)).ok


def test_timeout_kills_and_removes_container(tmp_path):
    result = run_python(tmp_path, "import time; time.sleep(120)", Limits(timeout_s=3))
    assert result.timed_out
    assert result.exit_code is None
    assert result.duration_s < 30
    left = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label={LABEL}"], capture_output=True, text=True
    )
    assert left.stdout.strip() == ""


def test_output_is_capped(tmp_path):
    result = run_python(tmp_path, "print('a' * 100_000 + 'END')", Limits(max_output_bytes=1000))
    assert result.output_truncated
    assert len(result.output) <= 1000
    assert "END" in result.output
