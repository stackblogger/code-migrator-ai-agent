"""Settings from environment variables and the `.env` file. Empty values use the defaults."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-sol"  # default tier: planning, migration, fixing
    openai_model_cheap: str = "gpt-5.6-luna"  # simple, high volume tasks
    openai_model_strong: str = "gpt-6-astra"  # blocked units, adversarial review
    llm_timeout_s: float = 120
    llm_max_retries: int = 2  # retries for network / rate limit errors (done by the SDK)
    llm_cache_dir: Path = Path(".migrator-cache/llm")

    def model_for(self, tier: str) -> str:
        return {"cheap": self.openai_model_cheap, "strong": self.openai_model_strong}.get(
            tier, self.openai_model
        )
