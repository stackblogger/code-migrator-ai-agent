"""Contract for framework adapters (NestJS, FastAPI, TypeORM, SQLAlchemy, ...).

A framework adapter reads source code and returns concept nodes. It must never guess
silently: anything it sees but cannot understand goes into `notes`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from tree_sitter import Node

from migrator.adapters.languages import LanguageAdapter
from migrator.concepts.models import ConceptKind, ConceptNode
from migrator.core.models import LanguageInventory
from migrator.repository import LocalRepository


@dataclass
class SourceFile:
    path: str
    source: bytes
    root: Node


@dataclass
class Extraction:
    nodes: list[ConceptNode] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class FrameworkAdapter(ABC):
    name: str
    language: str
    packages: set[str]  # the framework is used when any of these is a dependency

    def detect(self, inventory: LanguageInventory) -> bool:
        declared = {n.lower() for m in inventory.manifests for n in m.dependencies}
        return inventory.language == self.language and bool(self.packages & declared)

    @abstractmethod
    def extract(self, files: list[SourceFile]) -> Extraction: ...

    def node(
        self, kind: ConceptKind, key: str, name: str, file: SourceFile, at: Node, **attrs
    ) -> ConceptNode:
        return ConceptNode(
            kind=kind,
            key=key,
            name=name,
            file=file.path,
            line=at.start_point[0] + 1,
            framework=self.name,
            attributes=attrs,
        )


def load_files(
    repo: LocalRepository, paths: list[str], language: LanguageAdapter
) -> list[SourceFile]:
    files = []
    for path in paths:
        source = repo.read_bytes(path)
        files.append(SourceFile(path, source, language.syntax_tree(path, source).root_node))
    return files
