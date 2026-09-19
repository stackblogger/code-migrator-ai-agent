"""Project level facts for Python: pyproject/requirements, package manager, tools, entry points."""

import posixpath
import re
import tomllib

from migrator.adapters.languages.base import ToolTable, add_tool, tools_from_dependencies
from migrator.core.models import Manifest, ParsedFile
from migrator.repository import LocalRepository

REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")

LOCKFILES = {"uv.lock": "uv", "poetry.lock": "poetry", "pdm.lock": "pdm", "Pipfile.lock": "pipenv"}

TOOLS: ToolTable = {
    "pytest": [("test", "pytest")],
    "ruff": [("lint", "ruff"), ("format", "ruff")],
    "flake8": [("lint", "flake8")],
    "pylint": [("lint", "pylint")],
    "black": [("format", "black")],
    "mypy": [("typecheck", "mypy")],
    "pyright": [("typecheck", "pyright")],
}

BUILD_BACKENDS = {
    "hatchling": "hatch",
    "setuptools": "setuptools",
    "poetry": "poetry",
    "pdm": "pdm",
    "flit": "flit",
    "uv_build": "uv",
}

ENTRY_FILE_NAMES = {"main.py", "manage.py", "app.py", "asgi.py", "wsgi.py", "__main__.py"}


def normalize(name: str) -> str:
    """PEP 503 style: "Foo_Bar" -> "foo-bar"."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read_manifests(repo: LocalRepository) -> list[Manifest]:
    manifests = []
    for path in repo.files():
        base = posixpath.basename(path)
        if base == "pyproject.toml":
            manifests.append(_from_pyproject(repo, path))
        elif base.startswith("requirements") and base.endswith(".txt"):
            deps = _parse_requirements(repo.read_text(path).splitlines())
            is_dev = any(word in base for word in ("dev", "test"))
            manifests.append(
                Manifest(
                    file=path,
                    package_manager=_package_manager(repo, path, {}),
                    dependencies={} if is_dev else deps,
                    dev_dependencies=deps if is_dev else {},
                )
            )
    return manifests


def detect_tools(repo: LocalRepository, manifests: list[Manifest]) -> dict[str, list[str]]:
    names = {normalize(n) for m in manifests for n in (*m.dependencies, *m.dev_dependencies)}
    tools = tools_from_dependencies(names, TOOLS)
    files = repo.files()
    basenames = {posixpath.basename(f) for f in files}
    if basenames & {"conftest.py", "pytest.ini"}:
        add_tool(tools, "test", "pytest")
    if basenames & {"ruff.toml", ".ruff.toml"}:
        add_tool(tools, "lint", "ruff")
    if "mypy.ini" in basenames:
        add_tool(tools, "typecheck", "mypy")

    for path in files:
        if posixpath.basename(path) == "pyproject.toml":
            data = tomllib.loads(repo.read_text(path))
            _tools_from_pyproject(data, tools)
    return {k: sorted(v) for k, v in sorted(tools.items())}


def find_entry_points(
    manifests: list[Manifest], parsed: list[ParsedFile], module_file
) -> list[str]:
    """Files with a main guard, pyproject scripts, and common names like main.py near the top."""
    entries = {p.path for p in parsed if p.has_main_guard}
    for manifest in manifests:
        for target in manifest.scripts.values():  # "app.cli:main"
            path = module_file(target.split(":")[0])
            if path:
                entries.add(path)
    for p in parsed:
        depth = len(p.path.removeprefix("src/").split("/"))
        if posixpath.basename(p.path) in ENTRY_FILE_NAMES and depth <= 2:
            entries.add(p.path)
    return sorted(entries)


def _from_pyproject(repo: LocalRepository, path: str) -> Manifest:
    data = tomllib.loads(repo.read_text(path))
    project = data.get("project", {})
    deps = _parse_requirements(project.get("dependencies", []))

    dev_lines: list[str] = []
    for group in data.get("dependency-groups", {}).values():
        dev_lines += [item for item in group if isinstance(item, str)]
    for group in project.get("optional-dependencies", {}).values():
        dev_lines += group
    dev = _parse_requirements(dev_lines)

    poetry = data.get("tool", {}).get("poetry", {})
    deps |= {k: str(v) for k, v in poetry.get("dependencies", {}).items() if k != "python"}
    for group in poetry.get("group", {}).values():
        dev |= {k: str(v) for k, v in group.get("dependencies", {}).items()}

    return Manifest(
        file=path,
        package_manager=_package_manager(repo, path, data),
        dependencies=deps,
        dev_dependencies=dev,
        scripts=project.get("scripts", {}),
    )


def _parse_requirements(lines: list[str]) -> dict[str, str]:
    deps: dict[str, str] = {}
    for line in lines:
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue  # skip comments, -r, -e, --index-url
        match = REQUIREMENT_NAME.match(line)
        if match:
            deps[match.group(1)] = match.group(3).strip()
    return deps


def _tools_from_pyproject(data: dict, tools: dict[str, list[str]]) -> None:
    tool_section = data.get("tool", {})
    if "pytest" in tool_section:
        add_tool(tools, "test", "pytest")
    if "ruff" in tool_section:
        add_tool(tools, "lint", "ruff")
    if "mypy" in tool_section:
        add_tool(tools, "typecheck", "mypy")
    backend = data.get("build-system", {}).get("build-backend", "")
    for key, tool in BUILD_BACKENDS.items():
        if backend.startswith(key):
            add_tool(tools, "build", tool)


def _package_manager(repo: LocalRepository, manifest_path: str, data: dict) -> str:
    folder = posixpath.dirname(manifest_path)
    for lockfile, manager in LOCKFILES.items():
        if repo.exists(posixpath.join(folder, lockfile)):
            return manager
    if "poetry" in data.get("tool", {}):
        return "poetry"
    return "pip"
