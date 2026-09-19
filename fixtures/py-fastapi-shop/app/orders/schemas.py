from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateOrder(BaseModel):
    total: Decimal
    note: str | None = Field(default=None, max_length=200)


class OrderOut(BaseModel):
    id: int
    total: Decimal
    status: str
    note: str | None
    created_at: datetime
