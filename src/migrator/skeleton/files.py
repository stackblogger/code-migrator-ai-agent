"""Collect generated code per file, then write it out with imports on top."""

import posixpath
from dataclasses import dataclass, field


@dataclass
class _File:
    docstring: list[str] = field(default_factory=list)
    imports: set[str] = field(default_factory=set)
    chunks: list[str] = field(default_factory=list)


class FileBuilder:
    def __init__(self) -> None:
        self.files: dict[str, _File] = {}

    def add(self, path: str, code: str = "", imports: tuple[str, ...] | list[str] = ()) -> None:
        file = self.files.setdefault(path, _File())
        file.imports.update(imports)
        if code:
            file.chunks.append(code.strip("\n"))

    def note(self, path: str, line: str) -> None:
        """A line for the module docstring (where the code came from, what is still a stub)."""
        self.files.setdefault(path, _File()).docstring.append(line)

    def render(self) -> dict[str, str]:
        output = {path: _render(file) for path, file in self.files.items()}
        for path in list(output):  # every folder under app/ is a package
            folder = posixpath.dirname(path)
            while folder.startswith("app"):
                output.setdefault(f"{folder}/__init__.py", "")
                folder = posixpath.dirname(folder)
        return dict(sorted(output.items()))


def _render(file: _File) -> str:
    parts = []
    if file.docstring:
        parts.append('"""' + "\n".join(file.docstring) + '\n"""')
    plain = sorted(i for i in file.imports if i.startswith("import "))
    names: dict[str, set[str]] = {}
    for line in file.imports:
        if line.startswith("from "):
            module, _, imported = line[5:].partition(" import ")
            names.setdefault(module, set()).update(n.strip() for n in imported.split(","))
    from_imports = [f"from {m} import {', '.join(sorted(n))}" for m, n in sorted(names.items())]
    if plain or from_imports:
        parts.append("\n".join(plain + from_imports))
    parts += file.chunks
    return "\n\n\n".join(parts) + "\n" if parts else ""
