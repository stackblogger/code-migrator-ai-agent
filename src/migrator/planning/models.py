"""Migration plan: ordered units, and for every source file its target file."""

from enum import StrEnum

from pydantic import BaseModel, Field

from migrator.llm.models import LLMCall


class FileRole(StrEnum):
    TEST = "test"
    ENTRYPOINT = "entrypoint"  # starts the app
    API = "api"  # routes / controllers
    MODEL = "model"  # database tables
    SCHEMA = "schema"  # request / response shapes with validation
    GUARD = "guard"  # auth or permission check
    SERVICE = "service"  # business logic
    WIRING = "wiring"  # module / dependency setup (often not needed in the target)
    CONFIG = "config"  # reads env vars
    UTILITY = "utility"  # anything else


class FilePlan(BaseModel):
    source: str
    role: FileRole
    target: str | None  # None = no own file in target (reason says why)
    reason: str


class MigrationUnit(BaseModel):
    id: str  # "u01"
    files: list[FilePlan]  # more than one file = an import cycle, migrate together
    depends_on: list[str]  # unit ids, always earlier in the plan
    concepts: list[str]  # concept keys found in these files
    risks: list[str] = Field(default_factory=list)


class MigrationPlan(BaseModel):
    source_repo: str
    source_language: str
    source_frameworks: list[str]
    target: str  # e.g. "python-fastapi"
    units: list[MigrationUnit]
    mapped_by: str  # "convention" or "llm:<model>"
    llm_calls: list[LLMCall] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def files(self) -> list[FilePlan]:
        return [f for unit in self.units for f in unit.files]
