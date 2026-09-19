"""Read-only access to a repository on local disk.

All paths going in and out are repo-relative POSIX strings. Anything trying to go
outside the repo root is rejected, because repo content is untrusted.
"""

from pathlib import Path

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    "out",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".idea",
    ".vscode",
}

MAX_FILE_BYTES = 1_000_000


class UnsafePathError(ValueError):
    pass


class LocalRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"Repository folder not found: {root}")

    @property
    def name(self) -> str:
        return self.root.name

    def files(self) -> list[str]:
        """All files in the repo, sorted, skipping build/vendor folders and symlinks."""
        found: list[str] = []
        for path in self.root.rglob("*"):
            rel = path.relative_to(self.root)
            if any(part in IGNORED_DIRS for part in rel.parts):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            found.append(rel.as_posix())
        return sorted(found)

    def exists(self, rel_path: str) -> bool:
        return self._safe_path(rel_path).is_file()

    def read_bytes(self, rel_path: str) -> bytes:
        path = self._safe_path(rel_path)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"File too big to read: {rel_path}")
        return path.read_bytes()

    def read_text(self, rel_path: str) -> str:
        return self.read_bytes(rel_path).decode("utf-8", errors="replace")

    def _safe_path(self, rel_path: str) -> Path:
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root):
            raise UnsafePathError(f"Path goes outside the repository: {rel_path}")
        return path
