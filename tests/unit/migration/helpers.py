"""A tiny source repo + target skeleton with a 2-unit plan, used by migration tests."""

import json
from pathlib import Path

from migrator.planning.models import FilePlan, FileRole, MigrationPlan, MigrationUnit

STUB = '"""Migrated from src/calc.ts. MIGRATOR-STUB: logic not migrated yet (M6)."""\n'
GOOD_CODE = "def add(a: int, b: int) -> int:\n    return a + b\n"
PYPROJECT = """[project]
name = "calc"
version = "0"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
"""
GOOD_TEST = "from app.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def plan() -> MigrationPlan:
    return MigrationPlan(
        source_repo="calc",
        source_language="typescript",
        source_frameworks=[],
        target="python-fastapi",
        mapped_by="convention",
        units=[
            MigrationUnit(
                id="u01",
                depends_on=[],
                concepts=["route:GET /sum"],
                risks=["integer overflow"],
                files=[
                    FilePlan(
                        source="src/calc.ts", role=FileRole.UTILITY, target="app/calc.py", reason=""
                    )
                ],
            ),
            MigrationUnit(
                id="u02",
                depends_on=["u01"],
                concepts=[],
                files=[
                    FilePlan(
                        source="src/calc.module.ts", role=FileRole.WIRING, target=None, reason=""
                    )
                ],
            ),
        ],
    )


def make_repos(make_repo) -> tuple[Path, Path]:
    root = make_repo(
        {
            "source/package.json": json.dumps({"name": "calc"}),
            "source/src/calc.ts": "export function add(a: number, b: number) { return a + b; }\n",
            "source/src/calc.module.ts": "export class CalcModule {}\n",
            "target/pyproject.toml": PYPROJECT,
            "target/app/__init__.py": "",
            "target/app/calc.py": STUB,
            "target/tests/test_skeleton.py": "def test_skeleton():\n    assert True\n",
            "target/.migrator/plan.json": plan().model_dump_json(),
        }
    )
    return root / "source", root / "target"


def change(code: str = GOOD_CODE, test: str = GOOD_TEST, extra: dict | None = None) -> dict:
    files = [
        {"path": "app/calc.py", "content": code},
        {"path": "tests/generated/test_u01.py", "content": test},
    ]
    files += [{"path": p, "content": c} for p, c in (extra or {}).items()]
    return {"files": files, "notes": ["fake answer"]}
