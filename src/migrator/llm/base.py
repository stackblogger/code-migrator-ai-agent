"""Provider interface. The rest of the code never talks to a vendor SDK directly."""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from migrator.llm.models import Usage

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def structured(self, model: str, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        """Return an object of `schema` type, filled by the model, plus token usage."""
