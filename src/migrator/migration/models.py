"""Migration state (saved to `.migrator/state.json` in the target repo) and LLM answer shapes."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

STATE_FILE = ".migrator/state.json"


class UnitStatus(StrEnum):
    PENDING = "pending"
    GREEN = "green"  # migrated, build and all tests pass, committed
    BLOCKED = "blocked"  # gave up after max attempts; needs a person
    SKIPPED = "skipped"  # nothing to migrate (e.g. module wiring with no target file)


class Attempt(BaseModel):
    number: int
    kind: str  # "migrate" or "fix"
    model: str
    passed: bool
    stage: str | None = (
        None  # where it failed: policy, syntax, stubs, tests_missing, build, test, llm
    )
    error: str | None = None  # short error text
    input_tokens: int = 0
    output_tokens: int = 0


class UnitState(BaseModel):
    id: str
    status: UnitStatus = UnitStatus.PENDING
    attempts: list[Attempt] = Field(default_factory=list)
    files_written: list[str] = Field(default_factory=list)
    commit: str | None = None
    notes: list[str] = Field(default_factory=list)  # notes from the LLM and from us


class MigrationState(BaseModel):
    units: dict[str, UnitState] = Field(default_factory=dict)

    @staticmethod
    def load(target: Path) -> "MigrationState":
        path = target / STATE_FILE
        return (
            MigrationState.model_validate_json(path.read_text())
            if path.exists()
            else MigrationState()
        )

    def save(self, target: Path) -> None:
        path = target / STATE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n")


class FileContent(BaseModel):
    path: str
    content: str


class UnitChange(BaseModel):
    """What the LLM returns: full content of every file it changes, plus notes."""

    files: list[FileContent]
    notes: list[str]
