"""Fake provider for tests: returns prepared answers, never calls the network."""

from collections.abc import Callable

from pydantic import BaseModel

from migrator.llm.base import LLMProvider, T
from migrator.llm.models import LLMError, Usage

Answer = BaseModel | dict | Callable[[str, str], BaseModel | dict]


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, answers: list[Answer]) -> None:
        self.answers = list(answers)
        self.requests: list[tuple[str, str, str]] = []  # (model, system, user)

    def structured(self, model: str, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        self.requests.append((model, system, user))
        if not self.answers:
            raise LLMError("FakeProvider has no more answers")
        answer = self.answers.pop(0)
        if callable(answer):
            answer = answer(system, user)
        data = answer.model_dump() if isinstance(answer, BaseModel) else answer
        return schema.model_validate(data), Usage(input_tokens=len(user) // 4, output_tokens=50)
