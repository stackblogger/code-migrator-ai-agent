"""The migrate -> check -> fix loop with a fake LLM and the real sandbox."""

import subprocess

import pytest

from migrator.config import Settings
from migrator.llm import LLMClient
from migrator.llm.fake import FakeProvider
from migrator.migration.loop import run_migration
from migrator.migration.models import UnitStatus
from migrator.repository import LocalRepository
from tests.unit.migration.helpers import STUB, change, make_repos

pytestmark = pytest.mark.docker


def run(make_repo, tmp_path, answers, max_attempts=3):
    source, target = make_repos(make_repo)
    provider = FakeProvider(answers)
    settings = Settings(_env_file=None, llm_cache_dir=tmp_path / "cache")  # type: ignore[call-arg]
    client = LLMClient(provider, settings, use_cache=False)
    _, state = run_migration(LocalRepository(source), target, client, max_attempts=max_attempts)
    return state, target, provider


def git_log(target) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(target), "log", "--format=%s"], capture_output=True, text=True
    )
    return out.stdout.strip().splitlines()


def test_green_on_first_try_is_committed(make_repo, tmp_path):
    state, target, _ = run(make_repo, tmp_path, [change()])
    unit = state.units["u01"]
    assert unit.status == UnitStatus.GREEN and len(unit.attempts) == 1
    assert state.units["u02"].status == UnitStatus.SKIPPED
    assert "return a + b" in (target / "app/calc.py").read_text()
    assert "u01: migrate src/calc.ts (attempt 1)" in git_log(target)


def test_failing_test_goes_back_to_the_llm_and_gets_fixed(make_repo, tmp_path):
    wrong = change(code="def add(a: int, b: int) -> int:\n    return a - b\n")
    state, _, provider = run(make_repo, tmp_path, [wrong, change()])
    unit = state.units["u01"]
    assert unit.status == UnitStatus.GREEN
    assert [(a.kind, a.passed, a.stage) for a in unit.attempts] == [
        ("migrate", False, "test"),
        ("fix", True, None),
    ]
    fix_prompt = provider.requests[1][2]
    assert "failed at stage: test" in fix_prompt and "assert -1 == 5" in fix_prompt


def test_rule_breaking_answers_never_reach_the_repo(make_repo, tmp_path):
    cheat = change(extra={"tests/test_skeleton.py": "def test_skeleton():\n    assert True\n"})
    stub = change(code=STUB + "def add(a, b):\n    return a + b\n")
    state, target, _ = run(make_repo, tmp_path, [cheat, stub, change()])
    stages = [a.stage for a in state.units["u01"].attempts]
    assert stages == ["policy", "not_done", None]
    assert state.units["u01"].status == UnitStatus.GREEN


def test_blocked_after_max_attempts_restores_files(make_repo, tmp_path):
    wrong = change(code="def add(a: int, b: int) -> int:\n    return 0\n")
    state, target, _ = run(make_repo, tmp_path, [wrong, wrong], max_attempts=2)
    unit = state.units["u01"]
    assert unit.status == UnitStatus.BLOCKED and len(unit.attempts) == 2
    assert unit.attempts[-1].model == "gpt-6-astra"  # last try uses the strong model
    assert (target / "app/calc.py").read_text() == STUB
    assert not (target / "tests/generated/test_u01.py").exists()
    assert "Last failure (test)" in (target / ".migrator/blocked/u01.md").read_text()


def test_resume_skips_green_units(make_repo, tmp_path):
    state, target, _ = run(make_repo, tmp_path, [change()])
    settings = Settings(_env_file=None, llm_cache_dir=tmp_path / "cache2")  # type: ignore[call-arg]
    client = LLMClient(FakeProvider([]), settings, use_cache=False)  # would fail if called
    source = target.parent / "source"
    _, again = run_migration(LocalRepository(source), target, client)
    assert again.units["u01"].status == UnitStatus.GREEN and client.calls == []
