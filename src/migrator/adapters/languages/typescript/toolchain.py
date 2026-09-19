"""Sandbox commands for a TypeScript repo: install, build, test."""

from migrator.core.models import LanguageInventory, Manifest, Toolchain, ToolchainStep
from migrator.repository import LocalRepository

NODE_IMAGE = "node:22-bookworm-slim"
NPM_PLACEHOLDER_TEST = "no test specified"  # default `npm init` test script


def build_toolchain(repo: LocalRepository, inventory: LanguageInventory) -> Toolchain:
    notes: list[str] = []
    root = next((m for m in inventory.manifests if m.file == "package.json"), None)
    if root is None:
        notes.append("No package.json at repo root, so we cannot install or build")
        return Toolchain(language="typescript", image=NODE_IMAGE, steps=[], notes=notes)
    if len(inventory.manifests) > 1:
        notes.append("More than one package.json found; only the root one is used for now")

    steps = [_step("install", *_install_command(repo, root, notes), network=True)]

    dependencies = {**root.dependencies, **root.dev_dependencies}
    if "build" in root.scripts:
        steps.append(_step("build", "npm", "run", "build"))
    elif "typescript" in dependencies:
        steps.append(_step("build", "npx", "--no-install", "tsc", "--noEmit"))
    else:
        notes.append("No build command found")

    test_script = root.scripts.get("test", "")
    if test_script and NPM_PLACEHOLDER_TEST not in test_script:
        steps.append(_step("test", "npm", "test"))
    else:
        notes.append("No test command found")

    return Toolchain(language="typescript", image=NODE_IMAGE, steps=steps, notes=notes)


def _install_command(repo: LocalRepository, manifest: Manifest, notes: list[str]) -> list[str]:
    manager = manifest.package_manager
    if manager == "pnpm":
        return ["corepack", "pnpm", "install", "--frozen-lockfile"]
    if manager == "yarn":
        return ["corepack", "yarn", "install"]
    if manager != "npm":
        notes.append(f"Package manager '{manager}' is not supported yet, using npm instead")
    if repo.exists("package-lock.json"):
        return ["npm", "ci", "--no-audit", "--no-fund"]
    notes.append("No package-lock.json, so install is not reproducible")
    return ["npm", "install", "--no-audit", "--no-fund"]


def _step(name: str, *command: str, network: bool = False) -> ToolchainStep:
    return ToolchainStep(name=name, command=list(command), network=network)
