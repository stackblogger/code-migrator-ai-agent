"""M2 exit test: both fixture repos install, build and pass their tests inside the sandbox."""

import pytest

from migrator.repository import LocalRepository
from migrator.sandbox import RunStatus, verify_repo
from tests.conftest import FIXTURES

pytestmark = pytest.mark.docker


@pytest.mark.parametrize("name", ["ts-nestjs-shop", "py-fastapi-shop"])
def test_fixture_passes_in_sandbox(name):
    [run] = verify_repo(LocalRepository(FIXTURES / name))
    assert run.status == RunStatus.PASSED, run.notes
    assert [s.name for s in run.steps] == ["install", "build", "test"]
    assert "passed" in run.steps[-1].output


def test_broken_code_fails_in_sandbox(make_repo):
    root = make_repo(
        {
            "pyproject.toml": (
                '[project]\nname = "broken"\nversion = "0"\nrequires-python = ">=3.12"\n'
                'dependencies = []\n[dependency-groups]\ndev = ["pytest"]\n'
            ),
            "tests/test_math.py": "def test_add():\n    assert 1 + 1 == 3\n",
        }
    )
    [run] = verify_repo(LocalRepository(root))
    assert run.status == RunStatus.FAILED
    assert run.steps[-1].name == "test"
    assert "Stopped at 'test' step: exit code 1" in run.notes
