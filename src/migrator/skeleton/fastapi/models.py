"""SQLAlchemy models from table and column concepts. Column names stay exactly as in the
source database, because other systems may read the same tables."""

import re

from migrator.concepts.keys import snake_case
from migrator.concepts.models import ConceptKind, ConceptModel, ConceptNode
from migrator.skeleton.files import FileBuilder

# canonical type -> (python type, SQLAlchemy type, import needed for the python type)
TYPES = {
    "integer": ("int", "Integer", None),
    "bigint": ("int", "BigInteger", None),
    "float": ("float", "Float", None),
    "numeric": ("Decimal", "Numeric", "from decimal import Decimal"),
    "varchar": ("str", "String", None),
    "text": ("str", "Text", None),
    "boolean": ("bool", "Boolean", None),
    "timestamp": ("datetime", "DateTime", "from datetime import datetime"),
    "date": ("date", "Date", "from datetime import date"),
    "uuid": ("uuid.UUID", "Uuid", "import uuid"),
    "json": ("dict", "JSON", None),
}
SIZED = re.compile(r"^(\w+)\((.*)\)$")  # "numeric(10,2)" -> ("numeric", "10,2")


def render_models(
    model: ConceptModel, targets: dict[str, str | None], files: FileBuilder, notes: list[str]
) -> list[str]:
    """Adds model classes; returns the model module paths (main.py imports them)."""
    columns = sorted(model.of_kind(ConceptKind.COLUMN), key=lambda n: (n.file, n.line))
    paths = []
    for table in model.of_kind(ConceptKind.TABLE):
        path = targets.get(table.file) or "app/models.py"
        lines = [f"class {table.name}(Base):", f'    __tablename__ = "{table.key}"', ""]
        imports = {
            "from app.database import Base",
            "from sqlalchemy.orm import Mapped, mapped_column",
        }
        for column in [c for c in columns if c.key.startswith(table.key + ".")]:
            line, needed = _column(column, notes)
            lines.append(line)
            imports.update(needed)
        files.add(path, "\n".join(lines), sorted(imports))
        files.note(
            path, f"Table '{table.key}' from {table.file}. Relationships are not migrated yet (M6)."
        )
        paths.append(path)
    return sorted(set(paths))


def _column(node: ConceptNode, notes: list[str]) -> tuple[str, set[str]]:
    a = node.attributes
    column = node.key.split(".", 1)[1]
    attribute = snake_case(column)
    kind, size = _split_type(a.get("type", "unknown"))
    if kind not in TYPES:
        notes.append(f"skeleton: unknown type '{a.get('type')}' for {node.key}, using String")
        kind = "varchar"
    python_type, sa_type, python_import = TYPES[kind]
    sa_names = {sa_type}
    args = [f'"{column}"'] if attribute != column else []  # keep the exact column name
    args.append(f"{sa_type}({size.replace(',', ', ')})" if size else sa_type)
    if a.get("references"):
        args.append(f'ForeignKey("{a["references"]}.id")')
        sa_names.add("ForeignKey")
    if a.get("primary_key"):
        args.append("primary_key=True")
    else:
        args.append(f"nullable={bool(a.get('nullable'))}")
    if a.get("unique"):
        args.append("unique=True")
    default = a.get("default")
    if default == "now":
        args.append("server_default=func.now()")
        sa_names.add("func")
    elif default is not None:
        args.append(f"server_default={_sql_default(default)}")
        if not isinstance(default, str):
            sa_names.add("text")

    optional = " | None" if a.get("nullable") and not a.get("primary_key") else ""
    imports = {f"from sqlalchemy import {name}" for name in sa_names}
    if python_import:
        imports.add(python_import)
    return (
        f"    {attribute}: Mapped[{python_type}{optional}] = mapped_column({', '.join(args)})",
        imports,
    )


def _split_type(canonical: str) -> tuple[str, str]:
    match = SIZED.match(canonical)
    return (match.group(1), match.group(2)) if match else (canonical, "")


def _sql_default(value) -> str:
    if isinstance(value, bool):
        return 'text("true")' if value else 'text("false")'
    if isinstance(value, int | float):
        return f'text("{value}")'
    return repr(str(value))
