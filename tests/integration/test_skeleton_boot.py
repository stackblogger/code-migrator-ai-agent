"""M5 exit test: the skeleton builds, passes its smoke test, boots with Postgres, has every
source route, and enforces auth where the source did."""

import pytest

from migrator.concepts.extract import build_concept_model
from migrator.planning.planner import build_plan
from migrator.repository import LocalRepository
from migrator.skeleton.check import check_skeleton
from migrator.skeleton.generate import generate_skeleton, write_skeleton
from tests.conftest import FIXTURES

pytestmark = pytest.mark.docker


def test_skeleton_builds_and_boots(tmp_path):
    source = LocalRepository(FIXTURES / "ts-nestjs-shop")
    write_skeleton(generate_skeleton(source, build_plan(source)), tmp_path)
    result = check_skeleton(LocalRepository(tmp_path), build_concept_model(source))
    assert result.ok, result.problems
    assert [s.name for s in result.build.steps] == ["install", "build", "test"]
    assert result.routes == {
        "GET /orders": 401,
        "GET /users/{}": 401,
        "POST /orders": 401,
        "POST /orders/{}/cancel": 401,
        "POST /users": 422,
    }
    assert (tmp_path / "uv.lock").exists()  # later installs are frozen
