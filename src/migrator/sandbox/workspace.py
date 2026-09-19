"""A throwaway copy of the repo that the sandbox is allowed to write into.

The original repo is never mounted into a container. Real `.env` files are not copied,
because install scripts run with network on and could send secrets out.
`.env.example` style files are copied, they only have sample values.
"""

import posixpath
import shutil
import tempfile
from pathlib import Path
from types import TracebackType

from migrator.repository import LocalRepository

SECRET_FILES = {".env", ".env.local", ".env.production", ".env.development", ".env.test"}


class Workspace:
    def __init__(self, repo: LocalRepository, keep: bool = False) -> None:
        self.repo = repo
        self.keep = keep
        self.path = Path(tempfile.mkdtemp(prefix=f"migrator-{repo.name}-"))
        self.skipped: list[str] = []

    def __enter__(self) -> "Workspace":
        for rel in self.repo.files():
            if posixpath.basename(rel) in SECRET_FILES:
                self.skipped.append(rel)
                continue
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.repo.root / rel, target)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.keep:
            shutil.rmtree(self.path, ignore_errors=True)
