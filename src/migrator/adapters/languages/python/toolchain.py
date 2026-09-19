"""Sandbox commands for a Python repo: install, build (byte-compile), test."""

import posixpath

from migrator.core.models import LanguageInventory, Toolchain, ToolchainStep
from migrator.repository import LocalRepository

PYTHON_IMAGE = "ghcr.io/astral-sh/uv:python3.12-bookworm-slim"
VENV_PYTHON = ".venv/bin/python"


def build_toolchain(repo: LocalRepository, inventory: LanguageInventory) -> Toolchain:
    notes: list[str] = []
    steps = _install_steps(repo, inventory, notes)
    if not steps:
        return Toolchain(language="python", image=PYTHON_IMAGE, steps=[], notes=notes)

    # Python has no compile step, so byte-compiling is our "build". It catches syntax errors.
    compile_all = [VENV_PYTHON, "-m", "compileall", "-q", "-x", r"\.venv", "."]
    steps.append(_step("build", *compile_all))

    if "pytest" in inventory.tools.get("test", []):
        pytest = [VENV_PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        steps.append(_step("test", *pytest))
    elif inventory.test_files:
        notes.append("pytest not found, using unittest")
        steps.append(_step("test", VENV_PYTHON, "-m", "unittest", "discover"))
    else:
        notes.append("No test command found")

    return Toolchain(language="python", image=PYTHON_IMAGE, steps=steps, notes=notes)


def _install_steps(
    repo: LocalRepository, inventory: LanguageInventory, notes: list[str]
) -> list[ToolchainStep]:
    root_files = {m.file: m for m in inventory.manifests if "/" not in m.file}
    pyproject = root_files.get("pyproject.toml")

    if pyproject and pyproject.package_manager in ("poetry", "pdm"):
        notes.append(f"{pyproject.package_manager} project: dev dependencies may be missing")
        return [
            _step("install", "uv", "venv", network=True),
            _step("install", "uv", "pip", "install", "-e", ".", network=True),
        ]
    if pyproject:
        if repo.exists("uv.lock"):
            return [_step("install", "uv", "sync", "--frozen", network=True)]
        notes.append("No uv.lock, so install is not reproducible")
        return [_step("install", "uv", "sync", network=True)]

    requirements = sorted(f for f in root_files if posixpath.basename(f).startswith("requirements"))
    if requirements:
        notes.append("requirements.txt install is only as reproducible as its pins")
        steps = [_step("install", "uv", "venv", network=True)]
        for file in requirements:
            command = ["uv", "pip", "install", "-r", file]
            steps.append(_step("install", *command, network=True))
        return steps

    notes.append("No pyproject.toml or requirements.txt at repo root, so we cannot install")
    return []


def _step(name: str, *command: str, network: bool = False) -> ToolchainStep:
    return ToolchainStep(name=name, command=list(command), network=network)
