from tree_sitter import Tree

from migrator.adapters.languages.base import LanguageAdapter
from migrator.adapters.languages.typescript import project
from migrator.adapters.languages.typescript.launch import launch_info
from migrator.adapters.languages.typescript.parser import parse_typescript, typescript_tree
from migrator.adapters.languages.typescript.resolver import NODE_BUILTINS, resolve_import
from migrator.adapters.languages.typescript.toolchain import build_toolchain
from migrator.core.models import (
    ImportRef,
    LanguageInventory,
    LaunchInfo,
    Manifest,
    ParsedFile,
    Toolchain,
)
from migrator.repository import LocalRepository

TEST_SUFFIXES = (".spec.ts", ".test.ts", ".spec.tsx", ".test.tsx", ".e2e-spec.ts")


class TypeScriptAdapter(LanguageAdapter):
    name = "typescript"
    extensions = (".ts", ".tsx", ".mts", ".cts")

    def owns(self, path: str) -> bool:
        return super().owns(path) and not path.endswith(".d.ts")

    def is_test_file(self, path: str) -> bool:
        return path.endswith(TEST_SUFFIXES) or "/__tests__/" in f"/{path}"

    def parse_file(self, path: str, source: bytes) -> ParsedFile:
        return parse_typescript(path, source)

    def syntax_tree(self, path: str, source: bytes) -> Tree:
        return typescript_tree(path, source)

    def resolve_imports(self, imports: list[ImportRef], files: set[str]) -> list[ImportRef]:
        return [resolve_import(imp, files) for imp in imports]

    def read_manifests(self, repo: LocalRepository) -> list[Manifest]:
        return project.read_manifests(repo)

    def detect_tools(
        self, repo: LocalRepository, manifests: list[Manifest]
    ) -> dict[str, list[str]]:
        return project.detect_tools(repo, manifests)

    def find_entry_points(
        self, repo: LocalRepository, manifests: list[Manifest], parsed: list[ParsedFile]
    ) -> list[str]:
        return project.find_entry_points(repo, manifests)

    def toolchain(self, repo: LocalRepository, inventory: LanguageInventory) -> Toolchain:
        return build_toolchain(repo, inventory)

    def launch_info(self, repo: LocalRepository, inventory: LanguageInventory) -> LaunchInfo:
        return launch_info(inventory)

    def is_builtin(self, package: str) -> bool:
        return package in NODE_BUILTINS


__all__ = ["TypeScriptAdapter"]
