"""Check the columns we read from ORM code against the real database schema (from `baseline`).

Static reading of code can be wrong (unusual ORM options, naming strategies). The running
app is the truth, so any disagreement is reported. We never quietly trust the static side.
"""

import logging

from migrator.concepts.models import ConceptKind, ConceptModel

log = logging.getLogger(__name__)


def check_against_runtime(model: ConceptModel, schema: dict) -> list[str]:
    runtime = {f"{c['table_name']}.{c['column_name']}": c for c in schema.get("columns", [])}
    single_column = {
        (k["type"], f"{k['table_name']}.{k['columns']}")
        for k in schema.get("constraints", [])
        if "," not in k["columns"]
    }
    static = {n.key: n.attributes for n in model.of_kind(ConceptKind.COLUMN)}

    problems = [
        f"{key}: found in code, but not in the real database"
        for key in sorted(static.keys() - runtime.keys())
    ]
    problems += [
        f"{key}: in the real database, but not found in code"
        for key in sorted(runtime.keys() - static.keys())
    ]
    for key in sorted(static.keys() & runtime.keys()):
        attrs, real = static[key], runtime[key]
        checks = {
            "nullable": real["is_nullable"] == "YES",
            "unique": ("UNIQUE", key) in single_column,
            "primary_key": ("PRIMARY KEY", key) in single_column,
        }
        for name, real_value in checks.items():
            if attrs.get(name) != real_value:
                problems.append(
                    f"{key}: code says {name}={attrs.get(name)}, database says {real_value}"
                )
    for problem in problems:
        log.warning("Schema check: %s", problem)
    log.info("Schema check against real database: %d problems", len(problems))
    return problems
