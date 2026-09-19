"""Resolve Python imports to files inside the repo.

Supports absolute imports (from repo root or a `src/` folder) and relative imports.
"""

import posixpath
import sys

from migrator.core.models import ImportRef

STDLIB = frozenset(sys.stdlib_module_names) | {"__future__"}


class PythonResolver:
    def __init__(self, files: set[str]) -> None:
        self.files = files
        self.modules = _module_index(files)  # "app.orders.models" -> "app/orders/models.py"
        self.top_level = {name.split(".")[0] for name in self.modules}

    def resolve(self, imp: ImportRef) -> ImportRef:
        if imp.module.startswith("."):
            targets = self._resolve_relative(imp)
        else:
            targets = self._resolve_absolute(imp)

        if targets:
            return imp.model_copy(update={"targets": targets})
        top = imp.module.split(".")[0]
        if imp.module.startswith(".") or top in self.top_level:
            return imp  # looks internal but not found, analyzer will warn
        return imp.model_copy(update={"external_package": top})

    def module_file(self, module: str) -> str | None:
        return self.modules.get(module)

    def _resolve_absolute(self, imp: ImportRef) -> list[str]:
        targets = [
            self.modules[f"{imp.module}.{n}"]
            for n in imp.names
            if f"{imp.module}.{n}" in self.modules
        ]
        if not targets and imp.module in self.modules:
            targets = [self.modules[imp.module]]
        return sorted(set(targets))

    def _resolve_relative(self, imp: ImportRef) -> list[str]:
        rest = imp.module.lstrip(".")
        level = len(imp.module) - len(rest)
        folder = posixpath.dirname(imp.file)
        parts = folder.split("/") if folder else []
        if level - 1 > len(parts):
            return []
        base = parts[: len(parts) - (level - 1)] + (rest.split(".") if rest else [])

        targets = [t for n in imp.names if (t := self._file_for(base + [n]))]
        if not targets and (t := self._file_for(base)):
            targets = [t]
        return sorted(set(targets))

    def _file_for(self, parts: list[str]) -> str | None:
        path = "/".join(parts)
        for candidate in (f"{path}.py", f"{path}/__init__.py"):
            if candidate in self.files:
                return candidate
        return None


def _module_index(files: set[str]) -> dict[str, str]:
    roots = [""]
    if any(f.startswith("src/") for f in files):
        roots.append("src/")

    index: dict[str, str] = {}
    for path in sorted(files):
        if not path.endswith(".py"):
            continue
        for root in roots:
            if not path.startswith(root):
                continue
            module = path[len(root) : -3].replace("/", ".")
            module = module.removesuffix(".__init__")
            if module and module != "__init__":
                index.setdefault(module, path)
    return index
