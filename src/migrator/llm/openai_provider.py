"""OpenAI provider using the Responses API with structured outputs."""

from typing import Any

import openai

from migrator.config import Settings
from migrator.llm.base import LLMProvider, T
from migrator.llm.models import LLMError, Usage


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings, client: Any = None) -> None:
        if client is None:
            if settings.openai_api_key is None:
                raise LLMError("OPENAI_API_KEY is not set (add it to .env)")
            client = openai.OpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.llm_timeout_s,
                max_retries=settings.llm_max_retries,
            )
        self.client = client

    def structured(self, model: str, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        try:
            response = self.client.responses.parse(
                model=model, instructions=system, input=user, text_format=schema
            )
        except openai.OpenAIError as error:
            raise LLMError(f"OpenAI call failed: {error}") from error
        parsed = response.output_parsed
        if parsed is None:
            raise LLMError("OpenAI returned no structured output (maybe a refusal)")
        usage = response.usage
        return parsed, Usage(
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )
