"""How to start a TypeScript/Node app and which services it needs."""

from migrator.core.models import LanguageInventory, LaunchInfo

POSTGRES_DRIVERS = {"pg", "postgres", "pg-promise"}
HTTP_CLIENTS = {"axios", "node-fetch", "got", "undici", "superagent"}
POSTGRES_URL = "postgres://{user}:{password}@{host}:{port}/{database}"


def launch_info(inventory: LanguageInventory) -> LaunchInfo:
    root = next((m for m in inventory.manifests if m.file == "package.json"), None)
    if root is None:
        return LaunchInfo(command=None, notes=["No package.json at repo root"])

    notes: list[str] = []
    command: list[str] | None = None
    if "start" in root.scripts:
        command = ["npm", "start"]
    else:
        notes.append("No 'start' script in package.json, set run.command in .migrator.toml")

    services, url = [], None
    if POSTGRES_DRIVERS & set(root.dependencies):
        services.append("postgres")
        url = POSTGRES_URL

    for client in sorted(HTTP_CLIENTS & set(root.dependencies)):
        notes.append(
            f"Uses '{client}': outbound calls will fail because the app has no network "
            "(record/replay of external services is not supported yet)"
        )
    return LaunchInfo(command=command, services=services, database_url_template=url, notes=notes)
