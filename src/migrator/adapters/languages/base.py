"""Contract every language adapter must follow.

The core analyzer only talks to this interface. To add a new language, write a new
adapter and register it in `adapters/languages/__init__.py`. No change needed in the core.
"""

from abc import ABC, abstractmethod

from migrator.core.models import ImportRef, LanguageInventory, Manifest, ParsedFile, Toolchain
from migrator.repository import LocalRepository

ToolTable = dict[str, list[tuple[str, str]]]  # dependency -> [(category, tool name)]


class LanguageAdapter(ABC):
    name: str
    extensions: tuple[str, ...]

    def owns(self, path: str) -> bool:
        return path.endswith(self.extensions)

    @abstractmethod
    def is_test_file(self, path: str) -> bool: ...

    @abstractmethod
    def parse_file(self, path: str, source: bytes) -> ParsedFile: ...

    @abstractmethod
    def resolve_imports(self, imports: list[ImportRef], files: set[str]) -> list[ImportRef]:
        """Fill `targets` for imports inside the repo, `external_package` for the rest."""

    @abstractmethod
    def read_manifests(self, repo: LocalRepository) -> list[Manifest]: ...

    @abstractmethod
    def detect_tools(
        self, repo: LocalRepository, manifests: list[Manifest]
    ) -> dict[str, list[str]]: ...

    @abstractmethod
    def find_entry_points(
        self, repo: LocalRepository, manifests: list[Manifest], parsed: list[ParsedFile]
    ) -> list[str]: ...

    @abstractmethod
    def is_builtin(self, package: str) -> bool:
        """True for standard library modules (these need no dependency entry)."""

    @abstractmethod
    def toolchain(self, repo: LocalRepository, inventory: LanguageInventory) -> Toolchain:
        """Image and fixed commands to install, build and test this repo in the sandbox."""

    def is_declared(self, package: str, manifests: list[Manifest]) -> bool:
        """True if the package is listed in any manifest."""
        return package in declared_packages(manifests)


def declared_packages(manifests: list[Manifest]) -> set[str]:
    names: set[str] = set()
    for manifest in manifests:
        names.update(manifest.dependencies)
        names.update(manifest.dev_dependencies)
    return names


def tools_from_dependencies(dependency_names: set[str], table: ToolTable) -> dict[str, list[str]]:
    """Map known dependencies to tool categories, e.g. "jest" -> test: ["jest"]."""
    tools: dict[str, list[str]] = {}
    for dep, entries in table.items():
        if dep in dependency_names:
            for category, tool in entries:
                add_tool(tools, category, tool)
    return tools


def add_tool(tools: dict[str, list[str]], category: str, tool: str) -> None:
    tools.setdefault(category, [])
    if tool not in tools[category]:
        tools[category].append(tool)
