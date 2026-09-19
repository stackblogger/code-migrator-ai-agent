import posixpath

from migrator.adapters.languages.base import LanguageAdapter, declared_packages
from migrator.adapters.languages.python import project
from migrator.adapters.languages.python.parser import parse_python
from migrator.adapters.languages.python.resolver import STDLIB, PythonResolver
from migrator.core.models import ImportRef, Manifest, ParsedFile
from migrator.repository import LocalRepository

# Import name -> package name, where they are different.
IMPORT_TO_PACKAGE = {
    "jwt": "pyjwt",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "multipart": "python-multipart",
    "dateutil": "python-dateutil",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "psycopg2": "psycopg2-binary",
}


class PythonAdapter(LanguageAdapter):
    name = "python"
    extensions = (".py",)

    def is_test_file(self, path: str) -> bool:
        base = posixpath.basename(path)
        return base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py"

    def parse_file(self, path: str, source: bytes) -> ParsedFile:
        return parse_python(path, source)

    def resolve_imports(self, imports: list[ImportRef], files: set[str]) -> list[ImportRef]:
        resolver = PythonResolver(files)
        return [resolver.resolve(imp) for imp in imports]

    def read_manifests(self, repo: LocalRepository) -> list[Manifest]:
        return project.read_manifests(repo)

    def detect_tools(
        self, repo: LocalRepository, manifests: list[Manifest]
    ) -> dict[str, list[str]]:
        return project.detect_tools(repo, manifests)

    def find_entry_points(
        self, repo: LocalRepository, manifests: list[Manifest], parsed: list[ParsedFile]
    ) -> list[str]:
        resolver = PythonResolver({p.path for p in parsed})
        return project.find_entry_points(manifests, parsed, resolver.module_file)

    def is_builtin(self, package: str) -> bool:
        return package in STDLIB

    def is_declared(self, package: str, manifests: list[Manifest]) -> bool:
        declared = {project.normalize(name) for name in declared_packages(manifests)}
        candidates = {project.normalize(package)}
        if package in IMPORT_TO_PACKAGE:
            candidates.add(IMPORT_TO_PACKAGE[package])
        return bool(candidates & declared)


__all__ = ["PythonAdapter"]
