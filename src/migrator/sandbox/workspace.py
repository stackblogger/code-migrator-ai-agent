"""A throwaway copy of the repo that the sandbox is allowed to write into.

The original repo is never mounted into a container. Real `.env` files are not copied,
because install scripts run with network on and could send secrets out.
`.env.example` style files are copied, they only have sample values.
"""

import logging
import posixpath
import shutil
import tempfile
from pathlib import Path
from types import TracebackType

from migrator.repository import LocalRepository

log = logging.getLogger(__name__)

SECRET_FILES = {".env", ".env.local", ".env.production", ".env.development", ".env.test"}


class Workspace:
    def __init__(self, repo: LocalRepository, keep: bool = False) -> None:
        self.repo = repo
        self.keep = keep
        self.path = Path(tempfile.mkdtemp(prefix=f"migrator-{repo.name}-"))
        self.skipped: list[str] = []

    def __enter__(self) -> "Workspace":
        copied = 0
        for rel in self.repo.files():
            if posixpath.basename(rel) in SECRET_FILES:
                self.skipped.append(rel)
                continue
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.repo.root / rel, target)
            copied += 1
        log.info("Workspace ready at %s (%d files copied)", self.path, copied)
        if self.skipped:
            log.warning("Not copied to sandbox, may have secrets: %s", ", ".join(self.skipped))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.keep:
            log.info("Keeping workspace at %s", self.path)
        else:
            shutil.rmtree(self.path, ignore_errors=True)
            log.debug("Workspace %s deleted", self.path)
