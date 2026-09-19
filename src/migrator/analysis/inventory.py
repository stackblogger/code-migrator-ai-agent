"""Language-neutral repo facts: config files and env var names from .env files."""

import posixpath
import re
from fnmatch import fnmatch

from migrator.repository import LocalRepository

CONFIG_PATTERNS = [
    "package.json",
    "tsconfig*.json",
    "nest-cli.json",
    "*.config.js",
    "*.config.ts",
    "*.config.mjs",
    "*.config.cjs",
    "ormconfig.*",
    ".eslintrc*",
    ".prettierrc*",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "requirements*.txt",
    "*.ini",
    "Pipfile",
    ".env",
    ".env.*",
    "Dockerfile",
    "*.dockerfile",
    "docker-compose*.y*ml",
    "compose*.y*ml",
    "Makefile",
]
CONFIG_FOLDER_EXTENSIONS = (".json", ".yml", ".yaml", ".toml")
ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)


def find_config_files(files: list[str]) -> list[str]:
    found = []
    for path in files:
        base = posixpath.basename(path)
        in_config_folder = "/config/" in f"/{path}" and path.endswith(CONFIG_FOLDER_EXTENSIONS)
        if in_config_folder or any(fnmatch(base, pattern) for pattern in CONFIG_PATTERNS):
            found.append(path)
    return found


def env_keys_from_env_files(repo: LocalRepository, files: list[str]) -> dict[str, list[str]]:
    """Only the key names are read. Values may be secrets, so we never keep them."""
    keys: dict[str, list[str]] = {}
    for path in files:
        base = posixpath.basename(path)
        if base == ".env" or base.startswith(".env."):
            for key in ENV_KEY.findall(repo.read_text(path)):
                keys.setdefault(key, []).append(path)
    return keys
