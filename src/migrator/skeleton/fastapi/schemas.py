"""Pydantic request models from input field concepts, with the same validation rules."""

from collections import defaultdict

from migrator.concepts.constraints import NUMERIC_STRING_PATTERN
from migrator.concepts.models import ConceptKind, ConceptModel
from migrator.skeleton.files import FileBuilder

# canonical constraint -> (python type, import); first match wins
TYPE_RULES = [
    ("email", "EmailStr", "from pydantic import EmailStr"),
    ("numeric_string", "str", None),
    ("decimal", "Decimal", "from decimal import Decimal"),
    ("int", "int", None),
    ("number", "float", None),
    ("boolean", "bool", None),
    ("uuid", "UUID", "from uuid import UUID"),
    ("datetime", "datetime", "from datetime import datetime"),
    ("string", "str", None),
]
LIMITS = {"min_length": "min_length", "max_length": "max_length", "min": "ge", "max": "le"}


def render_schemas(
    model: ConceptModel, targets: dict[str, str | None], files: FileBuilder
) -> dict[str, str]:
    """Adds request models. Returns class name -> python module (for imports in routers)."""
    by_class = defaultdict(list)
    for node in sorted(model.of_kind(ConceptKind.INPUT_FIELD), key=lambda n: (n.file, n.line)):
        class_name = node.name.split(".", 1)[0]
        if node not in by_class[class_name]:
            by_class[class_name].append(node)

    modules = {}
    for class_name, fields in by_class.items():
        path = targets.get(fields[0].file) or "app/schemas.py"
        imports = {"from pydantic import BaseModel"}
        lines = [f"class {class_name}(BaseModel):"]
        seen = set()
        for node in fields:
            name = node.name.split(".", 1)[1]
            if name in seen:  # same DTO used by two routes
                continue
            seen.add(name)
            line, needed = _field(name, node.attributes)
            lines.append(line)
            imports.update(needed)
        files.add(path, "\n".join(lines), sorted(imports))
        files.note(path, f"Request models from {fields[0].file}.")
        modules[class_name] = path.removesuffix(".py").replace("/", ".")
    return modules


def _field(name: str, attrs: dict) -> tuple[str, set[str]]:
    constraints = set(attrs["constraints"])
    python_type, needed = "str", set()
    for constraint, candidate, import_line in TYPE_RULES:
        if constraint in constraints:
            python_type = candidate
            if import_line:
                needed.add(import_line)
            break
    options = []
    if not attrs["required"]:
        options.append("default=None")
    for constraint in sorted(constraints):
        key, _, value = constraint.partition("=")
        if key in LIMITS:
            options.append(f"{LIMITS[key]}={value}")
    if "numeric_string" in constraints:
        options.append(f'pattern=r"{NUMERIC_STRING_PATTERN}"')
    annotation = python_type + ("" if attrs["required"] else " | None")
    if options == ["default=None"]:
        return f"    {name}: {annotation} = None", needed
    if options:
        needed.add("from pydantic import Field")
        return f"    {name}: {annotation} = Field({', '.join(options)})", needed
    return f"    {name}: {annotation}", needed
