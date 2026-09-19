"""Project level facts for TypeScript: package.json, package manager, tools, entry points."""

import json
import posixpath

from migrator.adapters.languages.base import ToolTable, add_tool, tools_from_dependencies
from migrator.core.models import Manifest
from migrator.repository import LocalRepository

LOCKFILES = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lockb": "bun",
    "bun.lock": "bun",
    "package-lock.json": "npm",
}

TOOLS: ToolTable = {
    "typescript": [("build", "tsc"), ("typecheck", "tsc")],
    "@nestjs/cli": [("build", "nest")],
    "vite": [("build", "vite")],
    "webpack": [("build", "webpack")],
    "esbuild": [("build", "esbuild")],
    "jest": [("test", "jest")],
    "vitest": [("test", "vitest")],
    "mocha": [("test", "mocha")],
    "eslint": [("lint", "eslint")],
    "@biomejs/biome": [("lint", "biome"), ("format", "biome")],
    "prettier": [("format", "prettier")],
}

ENTRY_FILE_NAMES = [
    "src/main.ts",
    "src/index.ts",
    "src/server.ts",
    "main.ts",
    "index.ts",
    "server.ts",
]


def read_manifests(repo: LocalRepository) -> list[Manifest]:
    manifests = []
    for path in repo.files():
        if posixpath.basename(path) != "package.json":
            continue
        data = json.loads(repo.read_text(path))
        manifests.append(
            Manifest(
                file=path,
                package_manager=_package_manager(repo, path, data),
                dependencies=data.get("dependencies", {}),
                dev_dependencies=data.get("devDependencies", {}),
                scripts=data.get("scripts", {}),
            )
        )
    return manifests


def detect_tools(repo: LocalRepository, manifests: list[Manifest]) -> dict[str, list[str]]:
    names = {n for m in manifests for n in (*m.dependencies, *m.dev_dependencies)}
    tools = tools_from_dependencies(names, TOOLS)
    if any(posixpath.basename(f).startswith("tsconfig") for f in repo.files()):
        add_tool(tools, "build", "tsc")
        add_tool(tools, "typecheck", "tsc")
    return {k: sorted(v) for k, v in sorted(tools.items())}


def find_entry_points(repo: LocalRepository, manifests: list[Manifest]) -> list[str]:
    folders = sorted({posixpath.dirname(m.file) for m in manifests} | {""})
    entries = set()
    for folder in folders:
        for name in ENTRY_FILE_NAMES:
            path = posixpath.join(folder, name)
            if repo.exists(path):
                entries.add(path)
                break  # first match per package is enough
    return sorted(entries)


def _package_manager(repo: LocalRepository, manifest_path: str, data: dict) -> str:
    declared = data.get("packageManager")  # e.g. "pnpm@9.1.0"
    if declared:
        return declared.split("@")[0]
    folder = posixpath.dirname(manifest_path)
    for lockfile, manager in LOCKFILES.items():
        if repo.exists(posixpath.join(folder, lockfile)):
            return manager
    return "npm"
