from migrator.config import Settings
from migrator.llm.client import LLMClient
from migrator.llm.models import LLMCall, LLMError, Usage
from migrator.llm.openai_provider import OpenAIProvider
from migrator.llm.prompts import as_data, load_prompt


def default_client(settings: Settings | None = None) -> LLMClient:
    """OpenAI client from `.env` settings."""
    settings = settings or Settings()
    return LLMClient(OpenAIProvider(settings), settings)


__all__ = [
    "LLMCall",
    "LLMClient",
    "LLMError",
    "OpenAIProvider",
    "Settings",
    "Usage",
    "as_data",
    "default_client",
    "load_prompt",
]
