"""Results of running commands in the sandbox."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Limits:
    memory: str = "2g"
    cpus: float = 2.0
    pids: int = 512
    timeout_s: int = 600
    tmp_size: str = "1g"  # size of the writable /tmp inside the container
    max_output_bytes: int = 200_000  # we keep only the last part of the output


class StepResult(BaseModel):
    name: str
    command: list[str]
    network: bool
    exit_code: int | None  # None when the step timed out
    duration_s: float
    timed_out: bool = False
    oom_killed: bool = False
    output: str = ""
    output_truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.oom_killed

    @property
    def failure_reason(self) -> str | None:
        if self.timed_out:
            return "timed out"
        if self.oom_killed:
            return "memory limit hit"
        if self.exit_code != 0:
            return f"exit code {self.exit_code}"
        return None


class RunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"  # nothing failed, but something needed was missing (e.g. no tests)


class SandboxRun(BaseModel):
    language: str
    image: str
    status: RunStatus
    steps: list[StepResult]
    notes: list[str] = Field(default_factory=list)
