"""Records of LLM calls, for cost and debugging."""

from pydantic import BaseModel


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMCall(BaseModel):
    task: str  # e.g. "plan_mapping"
    prompt: str  # prompt name and version, e.g. "plan_mapping.v1"
    model: str
    usage: Usage
    latency_s: float
    cached: bool
    ok: bool
    error: str | None = None
    redactions: int = 0


class LLMError(RuntimeError):
    """The LLM call failed or returned something we could not use."""
