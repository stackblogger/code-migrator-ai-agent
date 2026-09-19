"""Data models shared across the analyzer. Everything is plain Pydantic so it can go to JSON."""

from pydantic import BaseModel, Field


class Symbol(BaseModel):
    """A named thing in the code: class, function, method, interface, etc."""

    name: str
    kind: str  # class | function | method | field | interface | enum | type | variable
    file: str
    start_line: int
    end_line: int
    parent: str | None = None  # class name for methods/fields
    decorators: list[str] = Field(default_factory=list)
    exported: bool = False


class ImportRef(BaseModel):
    """One import statement, as written in source, plus where it points inside the repo."""

    file: str  # file that has the import
    module: str  # module text as written, e.g. "./users.service" or "app.orders.models"
    names: list[str] = Field(default_factory=list)
    line: int
    type_only: bool = False  # `import type` in TS, `if TYPE_CHECKING:` in Python
    targets: list[str] = Field(default_factory=list)  # resolved repo files, empty = external
    external_package: str | None = None  # set when import is not inside the repo


class ParsedFile(BaseModel):
    """What a language adapter extracts from one source file."""

    path: str
    symbols: list[Symbol] = Field(default_factory=list)
    imports: list[ImportRef] = Field(default_factory=list)
    env_vars: list[str] = Field(default_factory=list)
    has_main_guard: bool = False  # e.g. `if __name__ == "__main__"`
    parse_errors: bool = False


class Manifest(BaseModel):
    """A package manifest like package.json or pyproject.toml."""

    file: str
    package_manager: str
    dependencies: dict[str, str] = Field(default_factory=dict)
    dev_dependencies: dict[str, str] = Field(default_factory=dict)
    scripts: dict[str, str] = Field(default_factory=dict)


class LanguageInventory(BaseModel):
    """Everything we found for one language in the repo."""

    language: str
    source_files: list[str]
    test_files: list[str]
    manifests: list[Manifest]
    tools: dict[str, list[str]]  # build/test/lint/format/typecheck -> tool names
    entry_points: list[str]
    external_packages: list[str]


class Inventory(BaseModel):
    repo_name: str
    total_files: int
    languages: list[LanguageInventory]
    config_files: list[str]
    env_vars: dict[str, list[str]]  # env var -> files where it is used or declared


class Edge(BaseModel):
    source: str  # importer
    target: str  # imported file
    type_only: bool = False


class GraphReport(BaseModel):
    nodes: list[str]
    edges: list[Edge]
    cycles: list[list[str]]  # strongly connected groups with more than one file
    migration_order: list[list[str]]  # groups in dependency-first order


class RepoReport(BaseModel):
    inventory: Inventory
    symbols: list[Symbol]
    imports: list[ImportRef]
    graph: GraphReport
    warnings: list[str]
