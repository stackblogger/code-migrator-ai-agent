from migrator.config import Settings
from migrator.llm import LLMClient
from migrator.llm.fake import FakeProvider
from migrator.planning.layout import fastapi_target
from migrator.planning.llm_mapping import MappingAnswer
from migrator.planning.models import FileRole
from migrator.planning.planner import build_plan
from migrator.planning.units import check_order
from migrator.repository import LocalRepository
from tests.conftest import FIXTURES

REPO = LocalRepository(FIXTURES / "ts-nestjs-shop")


def client(tmp_path, answers) -> tuple[LLMClient, FakeProvider]:
    provider = FakeProvider(answers)
    s = Settings(_env_file=None, llm_cache_dir=tmp_path)  # type: ignore[call-arg]
    return LLMClient(provider, s, use_cache=False), provider


def test_convention_plan_for_fixture():
    plan = build_plan(REPO)
    assert plan.mapped_by == "convention"
    assert check_order(plan.units) == []
    targets = {f.source: (f.role, f.target) for f in plan.files()}
    assert targets["src/main.ts"] == (FileRole.ENTRYPOINT, "app/main.py")
    assert targets["src/orders/orders.controller.ts"] == (FileRole.API, "app/orders/router.py")
    assert targets["src/orders/order.entity.ts"] == (FileRole.MODEL, "app/orders/models.py")
    assert targets["src/users/dto/create-user.dto.ts"] == (FileRole.SCHEMA, "app/users/schemas.py")
    assert targets["src/auth/jwt-auth.guard.ts"] == (FileRole.GUARD, "app/auth/dependencies.py")
    assert targets["src/app.module.ts"] == (FileRole.WIRING, None)
    assert targets["test/orders.service.spec.ts"][1] == "tests/test_orders_service.py"
    cycle = next(u for u in plan.units if len(u.files) > 1)
    assert {f.source for f in cycle.files} == {
        "src/orders/order.entity.ts",
        "src/users/user.entity.ts",
    }


def test_units_come_after_their_dependencies():
    plan = build_plan(REPO)
    position = {u.id: i for i, u in enumerate(plan.units)}
    for unit in plan.units:
        assert all(position[d] < position[unit.id] for d in unit.depends_on)


def convention_answer(system: str, user: str) -> MappingAnswer:
    """What a well-behaved model answers: keep the proposed layout, add a risk."""
    plan = build_plan(REPO)
    files = [{"source": f.source, "target": f.target, "reason": f.reason} for f in plan.files()]
    return MappingAnswer.model_validate(
        {"files": files, "unit_risks": [{"unit_id": "u11", "risks": ["201 vs 200"]}]}
    )


def test_llm_mapping_is_used_when_valid(tmp_path):
    llm, provider = client(tmp_path, [convention_answer])
    plan = build_plan(REPO, llm=llm)
    assert plan.mapped_by == "llm:gpt-5.6-sol"
    assert next(u for u in plan.units if u.id == "u11").risks == ["201 vs 200"]
    assert "<repository_data>" in provider.requests[0][2]


def test_invalid_llm_answer_gets_one_retry_with_the_problems(tmp_path):
    bad = {
        "files": [{"source": "src/main.ts", "target": "../../etc/passwd", "reason": "x"}],
        "unit_risks": [],
    }
    llm, provider = client(tmp_path, [bad, convention_answer])
    plan = build_plan(REPO, llm=llm)
    assert plan.mapped_by.startswith("llm:")
    retry_prompt = provider.requests[1][2]
    assert "not a valid path" in retry_prompt and "is missing" in retry_prompt


def test_falls_back_to_convention_when_llm_stays_wrong(tmp_path):
    bad = {"files": [], "unit_risks": []}
    llm, _ = client(tmp_path, [bad, bad])
    plan = build_plan(REPO, llm=llm)
    assert plan.mapped_by == "convention"
    assert any("LLM mapping rejected" in note for note in plan.notes)


def test_falls_back_when_llm_call_fails(tmp_path):
    llm, _ = client(tmp_path, [])  # FakeProvider raises LLMError
    plan = build_plan(REPO, llm=llm)
    assert plan.mapped_by == "convention"
    assert any("LLM mapping failed" in note for note in plan.notes)


def test_layout_names_are_valid_python():
    assert (
        fastapi_target(FileRole.UTILITY, "src/common/date-utils.ts")[0]
        == "app/common/date_utils.py"
    )
    assert fastapi_target(FileRole.UTILITY, "src/2fa.ts")[0] == "app/m_2fa.py"
    assert fastapi_target(FileRole.TEST, "test/users.e2e-spec.ts")[0] == "tests/test_users.py"
