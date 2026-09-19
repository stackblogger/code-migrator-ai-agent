"""Run a toolchain step by step in the sandbox. Stop at the first failure."""

from pathlib import Path

from migrator.core.models import Toolchain
from migrator.sandbox.docker import DockerSandbox
from migrator.sandbox.models import RunStatus, SandboxRun, StepResult


def run_toolchain(toolchain: Toolchain, workspace: Path, sandbox: DockerSandbox) -> SandboxRun:
    notes = list(toolchain.notes)
    if not toolchain.steps:
        notes.append("Nothing to run, so this repo is not verified")
        return _result(toolchain, RunStatus.INCOMPLETE, [], notes)

    sandbox.ensure_image(toolchain.image)
    results: list[StepResult] = []
    for step in toolchain.steps:
        result = sandbox.run(
            toolchain.image, step.command, workspace, network=step.network, name=step.name
        )
        results.append(result)
        if not result.ok:
            notes.append(f"Stopped at '{step.name}' step: {result.failure_reason}")
            return _result(toolchain, RunStatus.FAILED, results, notes)

    # Passing install and build is not enough. Without tests we cannot call it verified.
    has_tests = any(step.name == "test" for step in toolchain.steps)
    return _result(
        toolchain, RunStatus.PASSED if has_tests else RunStatus.INCOMPLETE, results, notes
    )


def _result(
    toolchain: Toolchain, status: RunStatus, steps: list[StepResult], notes: list[str]
) -> SandboxRun:
    return SandboxRun(
        language=toolchain.language, image=toolchain.image, status=status, steps=steps, notes=notes
    )
