"""Run one command inside a locked-down Docker container.

Every command gets a fresh container with:
- no network (unless the step is an install step)
- memory, CPU, process count and time limits
- read-only root filesystem; only /workspace and a small /tmp are writable
- no Linux capabilities, no privilege escalation, and a non-root user
- no host environment variables

Commands are argument lists, never shell strings, and the executable must be in the allowlist.
"""

import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import IO

from migrator.sandbox.models import Limits, StepResult

NODE_TOOLS = {"node", "npm", "npx", "corepack", "yarn", "pnpm"}
PYTHON_TOOLS = {"uv", "python", "python3", "pip", "pytest"}
ALLOWED_EXECUTABLES = frozenset(NODE_TOOLS | PYTHON_TOOLS)
LABEL = "migrator.sandbox=1"
CONTAINER_WORKDIR = "/workspace"


class CommandNotAllowedError(ValueError):
    pass


class DockerSandbox:
    def __init__(self, limits: Limits | None = None, docker: str = "docker") -> None:
        self.limits = limits or Limits()
        self.docker = docker

    def run(
        self,
        image: str,
        command: list[str],
        workspace: Path,
        network: bool = False,
        name: str = "step",
    ) -> StepResult:
        check_allowed(command)
        container = f"migrator-{uuid.uuid4().hex[:12]}"
        args = self.docker_args(container, image, workspace, network) + command

        started = time.monotonic()
        timed_out = False
        with tempfile.TemporaryFile() as output_file:
            process = subprocess.Popen(args, stdout=output_file, stderr=subprocess.STDOUT)
            try:
                process.wait(timeout=self.limits.timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._docker("kill", container)
                process.wait()
            duration = round(time.monotonic() - started, 2)
            output, truncated = _read_tail(output_file, self.limits.max_output_bytes)

        oom_killed = self._docker("inspect", "-f", "{{.State.OOMKilled}}", container) == "true"
        self._docker("rm", "-f", container)
        return StepResult(
            name=name,
            command=command,
            network=network,
            exit_code=None if timed_out else process.returncode,
            duration_s=duration,
            timed_out=timed_out,
            oom_killed=oom_killed,
            output=output,
            output_truncated=truncated,
        )

    def docker_args(self, container: str, image: str, workspace: Path, network: bool) -> list[str]:
        limits = self.limits
        options = [
            ("--name", container),
            ("--label", LABEL),
            ("--network", "bridge" if network else "none"),
            ("--memory", limits.memory),
            ("--memory-swap", limits.memory),  # same as memory, so no extra swap
            ("--cpus", str(limits.cpus)),
            ("--pids-limit", str(limits.pids)),
            ("--tmpfs", f"/tmp:rw,exec,nosuid,size={limits.tmp_size}"),
            ("--cap-drop", "ALL"),
            ("--security-opt", "no-new-privileges"),
            ("--user", f"{os.getuid()}:{os.getgid()}"),
            ("--env", "HOME=/tmp"),
            ("--env", "CI=true"),
            ("--env", "npm_config_cache=/tmp/.npm"),
            ("--env", "UV_CACHE_DIR=/tmp/.uv-cache"),
            ("--volume", f"{workspace.resolve()}:{CONTAINER_WORKDIR}"),
            ("--workdir", CONTAINER_WORKDIR),
        ]
        # --init adds a tiny init process that cleans up child processes.
        args = [self.docker, "run", "--init", "--read-only"]
        for flag, value in options:
            args += [flag, value]
        return args + [image]

    def ensure_image(self, image: str) -> None:
        """Pull the image on the host first, so pull time does not eat the step timeout."""
        if self._docker("image", "inspect", image) is None:
            result = subprocess.run([self.docker, "pull", image], capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Cannot pull image {image}: {result.stderr.strip()}")

    def cleanup_stale(self) -> None:
        """Remove containers left behind by a crashed earlier run."""
        ids = self._docker("ps", "-aq", "--filter", f"label={LABEL}")
        if ids:
            self._docker("rm", "-f", *ids.split())

    def _docker(self, *args: str) -> str | None:
        result = subprocess.run([self.docker, *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None


def check_allowed(command: list[str]) -> None:
    if not command:
        raise CommandNotAllowedError("Empty command")
    executable = Path(command[0]).name
    if executable not in ALLOWED_EXECUTABLES:
        raise CommandNotAllowedError(f"Command not allowed in sandbox: {command[0]}")


def _read_tail(file: IO[bytes], max_bytes: int) -> tuple[str, bool]:
    """Last `max_bytes` of the output. Errors are usually at the end, so we keep the tail."""
    size = file.seek(0, os.SEEK_END)
    truncated = size > max_bytes
    file.seek(max(0, size - max_bytes))
    return file.read().decode("utf-8", errors="replace"), truncated
