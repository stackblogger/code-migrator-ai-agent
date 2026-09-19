"""Decide how to start the app: command, port, env vars and services.

Adapters give what they can detect. A `.migrator.toml` file in the repo root can override it:

    [run]
    command = ["npm", "run", "start:prod"]
    port = 3000
    health_path = "/health"

    [run.env]
    SOME_FLAG = "1"
"""

import logging
import tomllib

from pydantic import BaseModel, Field

from migrator.baseline.database import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from migrator.core.models import LaunchInfo, Toolchain
from migrator.repository import LocalRepository

log = logging.getLogger(__name__)

OVERRIDE_FILE = ".migrator.toml"
APP_PORT = 8080
PORT_VARS = ("PORT", "APP_PORT", "HTTP_PORT", "SERVER_PORT")
DATABASE_URL_VARS = ("DATABASE_URL", "DB_URL", "DATABASE_URI", "POSTGRES_URL")

# Same settings on every run, so results do not depend on the machine.
DETERMINISM_ENV = {"TZ": "UTC", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"}


class RunSpec(BaseModel):
    language: str
    image: str
    command: list[str] | None
    port: int
    health_path: str = "/"
    env: dict[str, str] = Field(default_factory=dict)
    services: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def build_run_spec(
    repo: LocalRepository,
    toolchain: Toolchain,
    launch: LaunchInfo,
    env_var_names: set[str],
    suite_env: dict[str, str],
) -> RunSpec:
    overrides = _read_overrides(repo)
    notes = list(launch.notes)
    port = int(overrides.get("port", APP_PORT))
    env = dict(DETERMINISM_ENV)

    port_vars = [name for name in PORT_VARS if name in env_var_names]
    for name in port_vars:
        env[name] = str(port)
    if not port_vars and "port" not in overrides:
        notes.append(f"No port env var found, assuming the app listens on {port}")

    if "postgres" in launch.services and launch.database_url_template:
        url = launch.database_url_template.format(
            user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database=DB_NAME
        )
        url_vars = [name for name in DATABASE_URL_VARS if name in env_var_names]
        for name in url_vars:
            env[name] = url
        if not url_vars:
            notes.append("App uses Postgres but no database URL env var was found")

    env.update(suite_env)
    env.update(overrides.get("env", {}))
    spec = RunSpec(
        language=toolchain.language,
        image=toolchain.image,
        command=overrides.get("command") or launch.command,
        port=port,
        health_path=overrides.get("health_path", "/"),
        env=env,
        services=launch.services,
        notes=notes,
    )
    log.info(
        "Run spec: command=%s port=%d services=%s env=%s",
        spec.command,
        spec.port,
        spec.services,
        sorted(spec.env),
    )
    return spec


def _read_overrides(repo: LocalRepository) -> dict:
    if not repo.exists(OVERRIDE_FILE):
        return {}
    log.info("Using overrides from %s", OVERRIDE_FILE)
    return tomllib.loads(repo.read_text(OVERRIDE_FILE)).get("run", {})
