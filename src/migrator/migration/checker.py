"""Build and test the target repo in the sandbox after every attempt.

Generated code never runs on the host. It runs in a workspace copy, so tests cannot change
the real target repo (for example rewrite themselves). Dependencies are installed once.
"""

import logging
import shutil
from dataclasses import dataclass
from types import TracebackType

from migrator.adapters.languages import PythonAdapter
from migrator.analysis import analyze
from migrator.repository import LocalRepository
from migrator.sandbox import DockerSandbox, RunStatus
from migrator.sandbox.runner import run_toolchain
from migrator.sandbox.workspace import Workspace

log = logging.getLogger(__name__)

OUTPUT_TAIL_CHARS = 6000


@dataclass
class CheckResult:
    ok: bool
    stage: str | None = None  # "build", "typecheck" or "test"
    output: str = ""


class SandboxChecker:
    def __init__(self, target: LocalRepository, sandbox: DockerSandbox | None = None) -> None:
        self.target = target
        self.sandbox = sandbox or DockerSandbox()
        adapter = PythonAdapter()
        [inventory] = analyze(target, [adapter]).inventory.languages
        self.toolchain = adapter.toolchain(target, inventory)
        self.workspace = Workspace(target)

    def __enter__(self) -> "SandboxChecker":
        self.workspace.__enter__()
        install = run_toolchain(self.toolchain, self.workspace.path, self.sandbox, only={"install"})
        if install.status != RunStatus.PASSED:
            self.workspace.__exit__(None, None, None)
            raise RuntimeError(f"Installing target dependencies failed: {install.notes}")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.workspace.__exit__(exc_type, exc, tb)

    def check(self) -> CheckResult:
        self._sync()
        run = run_toolchain(
            self.toolchain, self.workspace.path, self.sandbox, only={"build", "typecheck", "test"}
        )
        if run.status == RunStatus.PASSED:
            return CheckResult(ok=True)
        failed = run.steps[-1] if run.steps else None
        stage = failed.name if failed else "build"
        output = failed.output[-OUTPUT_TAIL_CHARS:] if failed else "; ".join(run.notes)
        return CheckResult(ok=False, stage=stage, output=output)

    def _sync(self) -> None:
        """Make the workspace match the target repo (installed .venv is kept)."""
        wanted = set(self.target.files())
        workspace = LocalRepository(self.workspace.path)
        for path in set(workspace.files()) - wanted:
            (self.workspace.path / path).unlink()
        for path in wanted:
            destination = self.workspace.path / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.target.root / path, destination)
        log.debug("Workspace synced (%d files)", len(wanted))
