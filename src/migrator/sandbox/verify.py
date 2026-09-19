"""Install, build and test a repo inside the sandbox, for every language found in it."""

from migrator.adapters.languages import default_adapters
from migrator.analysis import analyze
from migrator.repository import LocalRepository
from migrator.sandbox.docker import DockerSandbox
from migrator.sandbox.models import SandboxRun
from migrator.sandbox.runner import run_toolchain
from migrator.sandbox.workspace import Workspace


def verify_repo(
    repo: LocalRepository, sandbox: DockerSandbox | None = None, keep_workspace: bool = False
) -> list[SandboxRun]:
    sandbox = sandbox or DockerSandbox()
    adapters = {adapter.name: adapter for adapter in default_adapters()}
    report = analyze(repo)

    runs = []
    with Workspace(repo, keep=keep_workspace) as workspace:
        for inventory in report.inventory.languages:
            toolchain = adapters[inventory.language].toolchain(repo, inventory)
            run = run_toolchain(toolchain, workspace.path, sandbox)
            if workspace.skipped:
                run.notes.append(f"Not copied to sandbox (may have secrets): {workspace.skipped}")
            if keep_workspace:
                run.notes.append(f"Workspace kept at {workspace.path}")
            runs.append(run)
    return runs
