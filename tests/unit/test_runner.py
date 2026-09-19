from pathlib import Path

from migrator.core.models import Toolchain, ToolchainStep
from migrator.sandbox import RunStatus, StepResult
from migrator.sandbox.runner import run_toolchain


class FakeSandbox:
    """Pretends to run commands. Steps named in `fail` return exit code 1."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.ran: list[str] = []

    def ensure_image(self, image: str) -> None:
        pass

    def run(self, image, command, workspace, network=False, name="step") -> StepResult:
        self.ran.append(name)
        code = 1 if name in self.fail else 0
        return StepResult(name=name, command=command, network=network, exit_code=code, duration_s=0)


def toolchain(*names: str) -> Toolchain:
    steps = [ToolchainStep(name=n, command=["npm", n]) for n in names]
    return Toolchain(language="typescript", image="img", steps=steps)


def test_all_steps_pass():
    run = run_toolchain(toolchain("install", "build", "test"), Path("."), FakeSandbox())  # type: ignore[arg-type]
    assert run.status == RunStatus.PASSED


def test_stops_at_first_failure():
    sandbox = FakeSandbox(fail={"build"})
    run = run_toolchain(toolchain("install", "build", "test"), Path("."), sandbox)  # type: ignore[arg-type]
    assert run.status == RunStatus.FAILED
    assert sandbox.ran == ["install", "build"]
    assert "Stopped at 'build' step: exit code 1" in run.notes


def test_no_tests_means_incomplete_not_passed():
    run = run_toolchain(toolchain("install", "build"), Path("."), FakeSandbox())  # type: ignore[arg-type]
    assert run.status == RunStatus.INCOMPLETE


def test_nothing_to_run_is_incomplete():
    run = run_toolchain(toolchain(), Path("."), FakeSandbox())  # type: ignore[arg-type]
    assert run.status == RunStatus.INCOMPLETE
    assert run.steps == []
