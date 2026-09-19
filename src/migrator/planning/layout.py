"""Convention layout for a Python + FastAPI target. Used as the default, and as the starting
proposal that the LLM may improve."""

import posixpath
import re

from migrator.concepts.keys import snake_case
from migrator.planning.models import FileRole

ROLE_SUFFIXES = (
    ".controller",
    ".service",
    ".entity",
    ".dto",
    ".module",
    ".guard",
    ".spec",
    ".test",
    ".e2e-spec",
    ".model",
    ".schema",
    ".router",
)
SOURCE_ROOTS = ("src/", "lib/", "app/")
VALID_TARGET = re.compile(r"^(app|tests)/([a-z_][a-z0-9_]*/)*[a-z_][a-z0-9_]*\.py$")


def fastapi_target(role: FileRole, source: str) -> tuple[str | None, str]:
    """(target path, reason) for one source file."""
    relative = next((source[len(r) :] for r in SOURCE_ROOTS if source.startswith(r)), source)
    folders = posixpath.dirname(relative).split("/") if "/" in relative else []
    package = (
        f"app/{_python_name(folders[0])}"
        if folders and folders[0] not in ("test", "tests")
        else "app"
    )
    stem = _stem(source)

    by_role = {
        FileRole.ENTRYPOINT: ("app/main.py", "FastAPI app entry point"),
        FileRole.CONFIG: ("app/config.py", "settings read from env vars"),
        FileRole.MODEL: (f"{package}/models.py", "SQLAlchemy models"),
        FileRole.SCHEMA: (f"{package}/schemas.py", "Pydantic request models"),
        FileRole.API: (f"{package}/router.py", "FastAPI router"),
        FileRole.GUARD: (f"{package}/dependencies.py", "auth check becomes a FastAPI dependency"),
        FileRole.SERVICE: (f"{package}/service.py", "business logic"),
        FileRole.TEST: (f"tests/test_{stem}.py", "pytest tests"),
        FileRole.UTILITY: (f"{package}/{stem}.py", "helper module"),
    }
    if role == FileRole.WIRING:
        return None, "module wiring is done by imports and app/main.py in FastAPI"
    return by_role[role]


def _stem(path: str) -> str:
    name = posixpath.basename(path).rsplit(".", 1)[0]
    for suffix in ROLE_SUFFIXES:
        name = name.removesuffix(suffix)
    return _python_name(name)


def _python_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]", "_", snake_case(name).replace("-", "_"))
    return cleaned if cleaned and not cleaned[0].isdigit() else f"m_{cleaned}"
