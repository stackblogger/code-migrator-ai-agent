"""Data models for the behaviour baseline: scenarios in, traces and reports out."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScenarioStep(BaseModel):
    """One HTTP request. Same format for every language and framework."""

    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


class Scenario(BaseModel):
    """An ordered flow of requests. Every scenario starts on an empty database."""

    name: str
    steps: list[ScenarioStep]


class ScenarioSuite(BaseModel):
    description: str = ""
    env: dict[str, str] = Field(default_factory=dict)  # extra env vars for the app
    vars: dict[str, str] = Field(default_factory=dict)  # ${NAME} replacements in steps
    scenarios: list[Scenario]


class TableChange(BaseModel):
    added: list[dict[str, Any]] = Field(default_factory=list)
    removed: list[dict[str, Any]] = Field(default_factory=list)


class Observation(BaseModel):
    """What we saw from outside the app after one request."""

    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    db: dict[str, TableChange] = Field(default_factory=dict)  # only tables that changed


class StepTrace(BaseModel):
    request: ScenarioStep
    observed: Observation


class Trace(BaseModel):
    scenario: str
    holdout: bool = False  # hold-out traces are never shown to the agents that write code
    steps: list[StepTrace]


class NormalizationRule(BaseModel):
    """Approved by a human. `path` looks like `body.createdAt` or `db.users.added[*].created_at`."""

    path: str
    action: Literal["ignore", "timestamp"]
    reason: str = ""


class Difference(BaseModel):
    scenario: str
    step: int
    path: str
    first: Any
    second: Any


class BaselineStatus(StrEnum):
    STABLE = "stable"  # every trace gave the same result on every run
    UNSTABLE = "unstable"  # some fields changed between runs; see proposed rules
    FAILED = "failed"  # could not build or start the app


MutantOutcome = Literal["killed", "survived", "invalid"]  # invalid = did not build


class MutantResult(BaseModel):
    file: str
    line: int
    column: int
    original: str
    replacement: str
    outcome: MutantOutcome
    detail: str = ""


class MutationReport(BaseModel):
    tested: int
    killed: int
    survived: int
    invalid: int
    score: float | None  # killed / (killed + survived); None when nothing valid was tested
    mutants: list[MutantResult]


class BaselineReport(BaseModel):
    repo: str
    language: str
    status: BaselineStatus
    runs: int
    scenarios: int
    holdout_scenarios: int
    rules_applied: list[NormalizationRule] = Field(default_factory=list)
    differences: list[Difference] = Field(default_factory=list)
    proposed_rules: list[NormalizationRule] = Field(default_factory=list)
    mutation: MutationReport | None = None
    notes: list[str] = Field(default_factory=list)
