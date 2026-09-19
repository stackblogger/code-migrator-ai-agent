"""Canonical Concept Model (CCM): language-neutral facts about an app.

Framework adapters turn source code into concept nodes. Two apps written in different
languages give the same `key` for the same thing, so the ledger can match them.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConceptKind(StrEnum):
    ROUTE = "route"  # HTTP endpoint
    TABLE = "table"  # database table (from ORM entity/model)
    COLUMN = "column"  # database column
    INPUT_FIELD = "input_field"  # field of a request body, with validation constraints
    ERROR = "error"  # HTTP error the code raises on purpose
    ENV_VAR = "env_var"  # config value read from the environment
    PROVIDER = "provider"  # injectable service/class (info only, not in the ledger)


class ConceptNode(BaseModel):
    kind: ConceptKind
    key: str  # canonical id used for matching, e.g. "GET /users/{}" or "users.email"
    name: str  # name in the code, e.g. "UsersController.findOne"
    file: str
    line: int
    framework: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class ConceptModel(BaseModel):
    repo: str
    frameworks: list[str]
    nodes: list[ConceptNode]
    notes: list[str] = Field(default_factory=list)  # things we saw but could not understand

    def of_kind(self, kind: ConceptKind) -> list[ConceptNode]:
        return [n for n in self.nodes if n.kind == kind]
