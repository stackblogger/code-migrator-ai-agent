from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from migrator.config import Settings
from migrator.llm import LLMClient, LLMError, load_prompt
from migrator.llm.fake import FakeProvider
from migrator.llm.openai_provider import OpenAIProvider
from migrator.llm.prompts import DATA_RULE, as_data
from migrator.llm.redact import redact


class Answer(BaseModel):
    value: str


def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, llm_cache_dir=tmp_path / "cache")  # type: ignore[call-arg]


def test_settings_use_defaults_for_empty_values(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_MODEL", "")
    monkeypatch.setenv("OPENAI_MODEL_CHEAP", "cheap-one")
    s = settings(tmp_path)
    assert s.model_for("default") == "gpt-5.6-sol"
    assert s.model_for("cheap") == "cheap-one"
    assert s.model_for("strong") == "gpt-6-astra"


def test_redact_hides_secrets_but_keeps_names():
    text = (
        'password = "hunter22"\nkey = "sk-abcdefghijklmnopqrstuvwxyz123"\n'
        "url = postgres://app:s3cret@db:5432/app\n"
        "token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijkl"
    )
    cleaned, count = redact(text)
    assert count == 4
    for secret in ("hunter22", "sk-abc", "s3cret", "eyJhbGci"):
        assert secret not in cleaned
    assert 'password = "[REDACTED]"' in cleaned


def test_prompt_registry_and_data_rule():
    prompt = load_prompt("plan_mapping")
    assert prompt.id == "plan_mapping.v1"
    system, user = prompt.render(source_stack="A", target_stack="B", units=as_data("{}"))
    assert "from A to B" in system and system.endswith(DATA_RULE)
    assert "<repository_data>" in user
    with pytest.raises(KeyError):
        load_prompt("does_not_exist")


def test_client_caches_and_records_usage(tmp_path):
    provider = FakeProvider([{"value": "first"}])
    client = LLMClient(provider, settings(tmp_path))
    prompt = load_prompt("plan_mapping")
    values = {"source_stack": "A", "target_stack": "B", "units": "[]"}
    assert client.structured("t", prompt, values, Answer).value == "first"
    assert client.structured("t", prompt, values, Answer).value == "first"  # from cache
    assert len(provider.requests) == 1
    assert [c.cached for c in client.calls] == [False, True]
    assert (tmp_path / "cache" / "usage.jsonl").read_text().count("\n") == 2


def test_client_redacts_before_sending_and_records_failures(tmp_path):
    provider = FakeProvider([])  # no answers -> error
    client = LLMClient(provider, settings(tmp_path), use_cache=False)
    prompt = load_prompt("plan_mapping")
    values = {"source_stack": "A", "target_stack": "B", "units": 'password = "hunter22"'}
    with pytest.raises(LLMError):
        client.structured("t", prompt, values, Answer)
    assert "hunter22" not in provider.requests[0][2]
    assert client.calls[0].ok is False and client.calls[0].redactions == 1


def test_openai_provider_parses_answer_and_usage(tmp_path):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    response = SimpleNamespace(output_parsed=Answer(value="ok"), usage=usage)
    fake_sdk = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: response))
    parsed, got = OpenAIProvider(settings(tmp_path), client=fake_sdk).structured(
        "m", "s", "u", Answer
    )
    assert parsed.value == "ok" and (got.input_tokens, got.output_tokens) == (10, 5)

    refusal = SimpleNamespace(output_parsed=None, usage=usage)
    fake_sdk.responses.parse = lambda **kwargs: refusal
    with pytest.raises(LLMError, match="no structured output"):
        OpenAIProvider(settings(tmp_path), client=fake_sdk).structured("m", "s", "u", Answer)


def test_openai_provider_needs_a_key(tmp_path):
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        OpenAIProvider(settings(tmp_path))
