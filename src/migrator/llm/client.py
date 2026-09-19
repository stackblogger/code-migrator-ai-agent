"""The only way the rest of the code calls an LLM.

Every call: render versioned prompt -> redact secrets -> check cache -> call provider
-> validate structured output -> record tokens and time -> save to cache and usage log.
"""

import hashlib
import json
import logging
import time
from pathlib import Path

from pydantic import ValidationError

from migrator.config import Settings
from migrator.llm.base import LLMProvider, T
from migrator.llm.models import LLMCall, LLMError, Usage
from migrator.llm.prompts import Prompt
from migrator.llm.redact import redact

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, provider: LLMProvider, settings: Settings, use_cache: bool = True) -> None:
        self.provider = provider
        self.settings = settings
        self.use_cache = use_cache
        self.calls: list[LLMCall] = []

    def structured(
        self,
        task: str,
        prompt: Prompt,
        values: dict[str, str],
        schema: type[T],
        tier: str = "default",
    ) -> T:
        system, user = prompt.render(**values)
        user, redactions = redact(user)
        if redactions:
            log.warning("Redacted %d secret(s) from the '%s' prompt", redactions, task)
        model = self.settings.model_for(tier)
        cache_file = self._cache_file(model, prompt, system, user, schema)
        base = {"task": task, "prompt": prompt.id, "model": model, "redactions": redactions}

        if self.use_cache and cache_file.exists():
            try:
                result = schema.model_validate_json(cache_file.read_text())
                self._record(LLMCall(**base, usage=Usage(), latency_s=0, cached=True, ok=True))
                return result
            except ValidationError:
                log.warning("Cached answer for '%s' does not fit the schema, calling again", task)

        started = time.monotonic()
        try:
            result, usage = self.provider.structured(model, system, user, schema)
        except LLMError as error:
            self._record(
                LLMCall(
                    **base,
                    usage=Usage(),
                    latency_s=time.monotonic() - started,
                    cached=False,
                    ok=False,
                    error=str(error),
                )
            )
            raise
        self._record(
            LLMCall(
                **base, usage=usage, latency_s=time.monotonic() - started, cached=False, ok=True
            )
        )
        if self.use_cache:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(result.model_dump_json())
        return result

    def total_usage(self) -> Usage:
        return Usage(
            input_tokens=sum(c.usage.input_tokens for c in self.calls),
            output_tokens=sum(c.usage.output_tokens for c in self.calls),
        )

    def _cache_file(self, model: str, prompt: Prompt, system: str, user: str, schema: type) -> Path:
        schema_text = json.dumps(schema.model_json_schema(), sort_keys=True)
        parts = [self.provider.name, model, prompt.id, system, user, schema_text]
        digest = hashlib.sha256("\x00".join(parts).encode()).hexdigest()
        return self.settings.llm_cache_dir / f"{digest}.json"

    def _record(self, call: LLMCall) -> None:
        call.latency_s = round(call.latency_s, 2)
        self.calls.append(call)
        log.info(
            "LLM %s: task=%s prompt=%s model=%s tokens=%d/%d time=%.1fs%s",
            "ok" if call.ok else "FAILED",
            call.task,
            call.prompt,
            call.model,
            call.usage.input_tokens,
            call.usage.output_tokens,
            call.latency_s,
            " (cached)" if call.cached else "",
        )
        if self.use_cache:
            self.settings.llm_cache_dir.mkdir(parents=True, exist_ok=True)
            with (self.settings.llm_cache_dir / "usage.jsonl").open("a") as file:
                file.write(call.model_dump_json() + "\n")
