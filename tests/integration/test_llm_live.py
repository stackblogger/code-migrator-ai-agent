"""Calls the real OpenAI API. Skipped unless MIGRATOR_LIVE_LLM=1 (it costs money)."""

import os

import pytest

from migrator.config import Settings
from migrator.llm import LLMClient, OpenAIProvider
from migrator.planning.planner import build_plan
from migrator.planning.units import check_order
from migrator.repository import LocalRepository
from tests.conftest import FIXTURES

pytestmark = pytest.mark.skipif(
    os.environ.get("MIGRATOR_LIVE_LLM") != "1", reason="set MIGRATOR_LIVE_LLM=1 to call OpenAI"
)


def test_live_plan_mapping(tmp_path):
    settings = Settings(llm_cache_dir=tmp_path)  # fresh cache, so it really calls the API
    client = LLMClient(OpenAIProvider(settings), settings)
    plan = build_plan(LocalRepository(FIXTURES / "ts-nestjs-shop"), llm=client)
    assert plan.mapped_by.startswith("llm:"), plan.notes
    assert check_order(plan.units) == []
    assert client.calls[0].usage.input_tokens > 0
