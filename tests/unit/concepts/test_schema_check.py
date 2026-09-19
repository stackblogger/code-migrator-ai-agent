from migrator.concepts.models import ConceptKind, ConceptModel, ConceptNode
from migrator.concepts.schema_check import check_against_runtime


def column(key: str, **attributes) -> ConceptNode:
    return ConceptNode(
        kind=ConceptKind.COLUMN,
        key=key,
        name=key,
        file="f",
        line=1,
        framework="x",
        attributes=attributes,
    )


SCHEMA = {
    "columns": [
        {"table_name": "users", "column_name": "id", "is_nullable": "NO"},
        {"table_name": "users", "column_name": "email", "is_nullable": "NO"},
        {"table_name": "users", "column_name": "bio", "is_nullable": "YES"},
    ],
    "constraints": [
        {"table_name": "users", "type": "PRIMARY KEY", "columns": "id"},
        {"table_name": "users", "type": "UNIQUE", "columns": "email"},
    ],
}


def test_matching_code_has_no_problems():
    model = ConceptModel(
        repo="r",
        frameworks=[],
        nodes=[
            column("users.id", nullable=False, unique=False, primary_key=True),
            column("users.email", nullable=False, unique=True, primary_key=False),
            column("users.bio", nullable=True, unique=False, primary_key=False),
        ],
    )
    assert check_against_runtime(model, SCHEMA) == []


def test_disagreements_are_reported():
    model = ConceptModel(
        repo="r",
        frameworks=[],
        nodes=[
            column("users.id", nullable=False, unique=False, primary_key=True),
            column("users.email", nullable=True, unique=False, primary_key=False),
            column("users.ghost", nullable=True, unique=False, primary_key=False),
        ],
    )
    problems = check_against_runtime(model, SCHEMA)
    assert "users.ghost: found in code, but not in the real database" in problems
    assert "users.bio: in the real database, but not found in code" in problems
    assert "users.email: code says nullable=True, database says False" in problems
    assert "users.email: code says unique=False, database says True" in problems
