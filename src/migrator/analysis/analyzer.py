"""Repository analyzer: runs every language adapter and builds one report.

This file has no language knowledge. All of that lives in the adapters.
"""

from dataclasses import dataclass, field

from migrator.adapters.languages import LanguageAdapter, default_adapters
from migrator.analysis.graph import CodeGraph
from migrator.analysis.inventory import env_keys_from_env_files, find_config_files
from migrator.core.models import (
    ImportRef,
    Inventory,
    LanguageInventory,
    ParsedFile,
    RepoReport,
)
from migrator.repository import LocalRepository


@dataclass
class _LanguageResult:
    inventory: LanguageInventory
    parsed: list[ParsedFile]
    imports: list[ImportRef]
    warnings: list[str] = field(default_factory=list)


def analyze(repo: LocalRepository, adapters: list[LanguageAdapter] | None = None) -> RepoReport:
    adapters = adapters if adapters is not None else default_adapters()
    files = repo.files()

    results = [r for a in adapters if (r := _analyze_language(repo, a, files)) is not None]

    parsed = [p for r in results for p in r.parsed]
    imports = sorted(
        (i for r in results for i in r.imports), key=lambda i: (i.file, i.line, i.module)
    )
    symbols = sorted(
        (s for p in parsed for s in p.symbols), key=lambda s: (s.file, s.start_line, s.name)
    )
    warnings = [w for r in results for w in r.warnings]
    if not results:
        warnings.append("No supported language found in this repository.")

    inventory = Inventory(
        repo_name=repo.name,
        total_files=len(files),
        languages=[r.inventory for r in results],
        config_files=find_config_files(files),
        env_vars=_env_vars(repo, files, parsed),
    )
    graph = CodeGraph(sorted(p.path for p in parsed), imports)
    return RepoReport(
        inventory=inventory,
        symbols=symbols,
        imports=imports,
        graph=graph.to_report(),
        warnings=sorted(warnings),
    )


def _analyze_language(
    repo: LocalRepository, adapter: LanguageAdapter, files: list[str]
) -> _LanguageResult | None:
    source_files = [f for f in files if adapter.owns(f)]
    if not source_files:
        return None

    warnings: list[str] = []
    parsed: list[ParsedFile] = []
    for path in source_files:
        try:
            result = adapter.parse_file(path, repo.read_bytes(path))
        except ValueError as error:  # file too big etc.
            warnings.append(f"{adapter.name}: skipped {path}: {error}")
            continue
        if result.parse_errors:
            warnings.append(f"{adapter.name}: syntax errors in {path}, results may be partial")
        parsed.append(result)

    imports = adapter.resolve_imports([i for p in parsed for i in p.imports], set(files))
    manifests = adapter.read_manifests(repo)
    if not manifests:
        warnings.append(f"{adapter.name}: no package manifest found")

    external: set[str] = set()
    for imp in imports:
        if imp.external_package is None:
            if not imp.targets:
                warnings.append(
                    f"{adapter.name}: cannot resolve '{imp.module}' in {imp.file}:{imp.line}"
                )
            continue
        if adapter.is_builtin(imp.external_package):
            continue
        external.add(imp.external_package)
        if manifests and not adapter.is_declared(imp.external_package, manifests):
            warnings.append(
                f"{adapter.name}: '{imp.external_package}' is imported in {imp.file} "
                "but not declared in any manifest"
            )

    inventory = LanguageInventory(
        language=adapter.name,
        source_files=[p.path for p in parsed if not adapter.is_test_file(p.path)],
        test_files=[p.path for p in parsed if adapter.is_test_file(p.path)],
        manifests=manifests,
        tools=adapter.detect_tools(repo, manifests),
        entry_points=adapter.find_entry_points(repo, manifests, parsed),
        external_packages=sorted(external),
    )
    return _LanguageResult(inventory, parsed, imports, sorted(set(warnings)))


def _env_vars(
    repo: LocalRepository, files: list[str], parsed: list[ParsedFile]
) -> dict[str, list[str]]:
    env = env_keys_from_env_files(repo, files)
    for p in parsed:
        for name in p.env_vars:
            env.setdefault(name, []).append(p.path)
    return {name: sorted(set(paths)) for name, paths in sorted(env.items())}
