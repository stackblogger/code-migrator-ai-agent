"""How to start a Python app and which services it needs."""

from migrator.adapters.languages.python.project import normalize
from migrator.adapters.languages.python.toolchain import VENV_PYTHON
from migrator.core.models import LanguageInventory, LaunchInfo

HTTP_CLIENTS = {"httpx", "requests", "aiohttp", "urllib3"}
URL_TAIL = "://{user}:{password}@{host}:{port}/{database}"


def launch_info(inventory: LanguageInventory) -> LaunchInfo:
    notes: list[str] = []
    dependencies = {normalize(name) for m in inventory.manifests for name in m.dependencies}

    command = None
    if inventory.entry_points:
        entry = inventory.entry_points[0]
        if len(inventory.entry_points) > 1:
            notes.append(f"More than one entry point, using {entry}")
        command = [VENV_PYTHON, "-m", _module_name(entry)]
    else:
        notes.append("No entry point found, set run.command in .migrator.toml")

    services, url = [], None
    scheme = _postgres_scheme(dependencies)
    if scheme:
        services.append("postgres")
        url = scheme + URL_TAIL

    for client in sorted(HTTP_CLIENTS & dependencies):
        notes.append(
            f"Uses '{client}': outbound calls will fail because the app has no network "
            "(record/replay of external services is not supported yet)"
        )
    return LaunchInfo(command=command, services=services, database_url_template=url, notes=notes)


def _module_name(path: str) -> str:
    """`src/app/main.py` -> `app.main`, `app/__main__.py` -> `app`."""
    module = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
    return module.removesuffix(".__main__")


def _postgres_scheme(dependencies: set[str]) -> str | None:
    uses_sqlalchemy = "sqlalchemy" in dependencies
    if "psycopg" in dependencies or "psycopg-binary" in dependencies:
        return "postgresql+psycopg" if uses_sqlalchemy else "postgresql"
    if "asyncpg" in dependencies:
        return "postgresql+asyncpg" if uses_sqlalchemy else "postgresql"
    if {"psycopg2", "psycopg2-binary"} & dependencies:
        return "postgresql"
    return None
