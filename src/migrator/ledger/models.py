"""Traceability ledger: every source item must end up mapped, waived, or reported missing."""

from enum import StrEnum

from pydantic import BaseModel, Field

from migrator.concepts.models import ConceptKind


class LedgerStatus(StrEnum):
    MAPPED = "mapped"  # found in target, same attributes (behaviour not verified yet, see M7)
    MISMATCH = "mismatch"  # found in target, but some attribute is different
    MISSING = "missing"  # not found in target
    WAIVED = "waived"  # missing or mismatch, but a human accepted it with a reason


class Place(BaseModel):
    name: str
    file: str
    line: int


class LedgerRow(BaseModel):
    kind: ConceptKind
    key: str
    status: LedgerStatus
    source: list[Place]
    target: list[Place] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)  # e.g. "status: 201 vs 200"
    hint: str | None = None  # e.g. "maybe orders.user_id"
    waiver: str | None = None  # reason, when waived


class Waiver(BaseModel):
    key: str
    reason: str
    approved_by: str


class Ledger(BaseModel):
    source_repo: str
    target_repo: str | None
    rows: list[LedgerRow]
    extra_in_target: list[LedgerRow] = Field(default_factory=list)  # only in target
    unused_waivers: list[Waiver] = Field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True when every source item is mapped or waived."""
        return all(r.status in (LedgerStatus.MAPPED, LedgerStatus.WAIVED) for r in self.rows)

    def count(self, status: LedgerStatus) -> int:
        return sum(r.status == status for r in self.rows)
