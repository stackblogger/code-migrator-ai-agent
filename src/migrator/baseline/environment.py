"""Run the app with its services in an isolated Docker network.

    host (127.0.0.1:random) ──► gateway (socat) ──► app ──► postgres
                                 └──────── internal network, no internet ────────┘

- The app and database sit on an `--internal` network, so they cannot reach the internet.
- The app container has the same lock-down as sandbox steps (read-only, no caps, limits).
- The gateway only forwards one port and is bound to 127.0.0.1 on the host.
- Everything is removed on exit, even when something fails.
"""

import logging
import subprocess
import time
import uuid
from pathlib import Path
from types import TracebackType

import httpx

from migrator.baseline.database import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_USER,
    POSTGRES_IMAGE,
    Postgres,
)
from migrator.baseline.runspec import RunSpec
from migrator.sandbox.docker import (
    CONTAINER_WORKDIR,
    HARDENED_FLAGS,
    LABEL,
    DockerSandbox,
    check_allowed,
    hardened_options,
    to_args,
)

log = logging.getLogger(__name__)

GATEWAY_IMAGE = "alpine/socat:1.8.0.3"
GATEWAY_PORT = 8080
SUPPORTED_SERVICES = {"postgres"}
LOG_TAIL_LINES = 30


class AppEnvironment:
    def __init__(
        self, spec: RunSpec, workspace: Path, sandbox: DockerSandbox, startup_timeout_s: int = 120
    ) -> None:
        if spec.command is None:
            raise RuntimeError("Do not know how to start the app (no start command)")
        unsupported = set(spec.services) - SUPPORTED_SERVICES
        if unsupported:
            raise RuntimeError(f"Services not supported yet: {sorted(unsupported)}")

        self.spec = spec
        self.workspace = workspace
        self.sandbox = sandbox
        self.startup_timeout_s = startup_timeout_s
        run_id = uuid.uuid4().hex[:10]
        self.network = f"migrator-net-{run_id}"
        self.app = f"migrator-app-{run_id}"
        self.db_container = f"migrator-db-{run_id}"
        self.gateway = f"migrator-gw-{run_id}"
        self.db: Postgres | None = None
        self.base_url = ""
        self.final_app_logs = ""

    def __enter__(self) -> "AppEnvironment":
        try:
            self._start()
        except BaseException:
            self._stop()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop()

    def app_logs(self) -> str:
        result = subprocess.run(
            ["docker", "logs", self.app], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        if result.returncode != 0:
            return ""  # container was never created
        return result.stdout.decode("utf-8", errors="replace")

    # ---- start ----

    def _start(self) -> None:
        started = time.monotonic()
        images = [self.spec.image, GATEWAY_IMAGE]
        if "postgres" in self.spec.services:
            images.append(POSTGRES_IMAGE)
        for image in images:
            self.sandbox.ensure_image(image)

        self._docker("network", "create", "--internal", "--label", LABEL, self.network)
        log.info("Created internal network %s (no internet)", self.network)
        if "postgres" in self.spec.services:
            self._start_postgres()
        self._start_app()
        self._start_gateway()
        self._wait_for_app()
        log.info("Environment ready in %.1fs at %s", time.monotonic() - started, self.base_url)

    def _start_postgres(self) -> None:
        # Official image, not repo code. It needs root at start to set up its data folder.
        options = [
            ("--name", self.db_container),
            ("--label", LABEL),
            ("--network", self.network),
            ("--network-alias", DB_HOST),
            ("--memory", "512m"),
            ("--tmpfs", "/var/lib/postgresql/data"),  # in memory: fast, and gone after the run
            ("--security-opt", "no-new-privileges"),
            ("--env", f"POSTGRES_USER={DB_USER}"),
            ("--env", f"POSTGRES_PASSWORD={DB_PASSWORD}"),
            ("--env", f"POSTGRES_DB={DB_NAME}"),
            ("--env", "TZ=UTC"),
        ]
        self._docker("run", "-d", *to_args(options), POSTGRES_IMAGE)
        log.info("Started Postgres container %s", self.db_container)
        self.db = Postgres(self.db_container, self.sandbox.docker_output)
        self.db.wait_ready()

    def _start_app(self) -> None:
        command = self.spec.command or []
        check_allowed(command)
        options = [
            ("--name", self.app),
            ("--label", LABEL),
            ("--network", self.network),
            ("--network-alias", "app"),
            *hardened_options(self.sandbox.limits),
            *[("--env", f"{key}={value}") for key, value in sorted(self.spec.env.items())],
            ("--volume", f"{self.workspace.resolve()}:{CONTAINER_WORKDIR}"),
            ("--workdir", CONTAINER_WORKDIR),
        ]
        self._docker("run", "-d", *HARDENED_FLAGS, *to_args(options), self.spec.image, *command)
        log.info("Started app container %s: %s", self.app, " ".join(command))

    def _start_gateway(self) -> None:
        network_ip = f'{{{{(index .NetworkSettings.Networks "{self.network}").IPAddress}}}}'
        app_ip = self._docker("inspect", "-f", network_ip, self.app)
        options = [
            ("--name", self.gateway),
            ("--label", LABEL),
            ("--user", "65534"),
            ("--memory", "64m"),
            ("--cap-drop", "ALL"),
            ("--security-opt", "no-new-privileges"),
            ("--publish", f"127.0.0.1::{GATEWAY_PORT}"),  # random free port on the host
        ]
        forward = [f"TCP-LISTEN:{GATEWAY_PORT},fork,reuseaddr", f"TCP:{app_ip}:{self.spec.port}"]
        self._docker("run", "-d", "--read-only", *to_args(options), GATEWAY_IMAGE, *forward)
        self._docker("network", "connect", self.network, self.gateway)
        host_port = self._docker("port", self.gateway, f"{GATEWAY_PORT}/tcp").splitlines()[0]
        self.base_url = f"http://{host_port}"
        log.info("Gateway %s forwards %s -> app port %d", self.gateway, host_port, self.spec.port)

    def _wait_for_app(self) -> None:
        url = self.base_url + self.spec.health_path
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if not self._app_running():
                raise RuntimeError(f"App stopped during startup. Last logs:\n{self._log_tail()}")
            try:
                response = httpx.get(url, timeout=2)
                log.info("App answered %s with status %d", url, response.status_code)
                return
            except httpx.TransportError:
                time.sleep(0.5)
        raise RuntimeError(
            f"App did not answer within {self.startup_timeout_s}s. Last logs:\n{self._log_tail()}"
        )

    def _app_running(self) -> bool:
        return self.sandbox.docker_output("inspect", "-f", "{{.State.Running}}", self.app) == "true"

    # ---- stop ----

    def _stop(self) -> None:
        self.final_app_logs = self.app_logs()
        for container in (self.gateway, self.app, self.db_container):
            self.sandbox.docker_output("rm", "-f", container)
        self.sandbox.docker_output("network", "rm", self.network)
        log.info("Environment removed (network %s)", self.network)

    def _log_tail(self) -> str:
        return "\n".join(self.app_logs().splitlines()[-LOG_TAIL_LINES:])

    def _docker(self, *args: str) -> str:
        output = self.sandbox.docker_output(*args)
        if output is None:
            raise RuntimeError(f"docker {' '.join(args[:3])} ... failed")
        return output
