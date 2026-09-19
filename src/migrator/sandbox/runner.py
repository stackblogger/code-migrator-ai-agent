"""Run a toolchain step by step in the sandbox. Stop at the first failure."""

import logging
from pathlib import Path

from migrator.core.models import Toolchain
from migrator.sandbox.docker import DockerSandbox
from migrator.sandbox.models import RunStatus, SandboxRun, StepResult

log = logging.getLogger(__name__)


def run_toolchain(
    toolchain: Toolchain,
    workspace: Path,
    sandbox: DockerSandbox,
    only: set[str] | None = None,
) -> SandboxRun:
    """Run all steps, or only the named ones (e.g. {"install", "build"})."""
    notes = list(toolchain.notes)
    for note in notes:
        log.warning("%s toolchain: %s", toolchain.language, note)

    steps = [s for s in toolchain.steps if only is None or s.name in only]
    if not steps:
        notes.append("Nothing to run, so this repo is not verified")
        log.warning("%s: nothing to run", toolchain.language)
        return _result(toolchain, RunStatus.INCOMPLETE, [], notes)

    sandbox.ensure_image(toolchain.image)
    results: list[StepResult] = []
    for step in steps:
        result = sandbox.run(
            toolchain.image, step.command, workspace, network=step.network, name=step.name
        )
        results.append(result)
        if not result.ok:
            notes.append(f"Stopped at '{step.name}' step: {result.failure_reason}")
            return _result(toolchain, RunStatus.FAILED, results, notes)

    if only is not None:
        status = RunStatus.PASSED  # caller asked for a subset, so missing tests are expected
    else:
        # Passing install and build is not enough. Without tests we cannot call it verified.
        has_tests = any(step.name == "test" for step in steps)
        status = RunStatus.PASSED if has_tests else RunStatus.INCOMPLETE
    return _result(toolchain, status, results, notes)


def _result(
    toolchain: Toolchain, status: RunStatus, steps: list[StepResult], notes: list[str]
) -> SandboxRun:
    log.info("%s run finished: %s", toolchain.language, status.value.upper())
    return SandboxRun(
        language=toolchain.language, image=toolchain.image, status=status, steps=steps, notes=notes
    )
