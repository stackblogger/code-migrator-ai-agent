"""FastAPI: routers and routes, auth dependencies, Pydantic request models, HTTPException."""

from tree_sitter import Node

from migrator.adapters.frameworks.base import Extraction, FrameworkAdapter, SourceFile
from migrator.adapters.frameworks.py_syntax import (
    Call,
    base_names,
    call,
    class_assignments,
    classes,
    decorated_functions,
    find_all,
    literal,
)
from migrator.adapters.languages.treesitter import text
from migrator.concepts.keys import display_path, error_key, input_key, route_key
from migrator.concepts.models import ConceptKind

ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
ROUTER_FACTORIES = {"APIRouter", "FastAPI", "fastapi.APIRouter", "fastapi.FastAPI"}
EXCEPTIONS = {"HTTPException", "fastapi.HTTPException"}
# Python type -> canonical constraints (same words as the NestJS adapter uses)
TYPES = {
    "str": ["string"],
    "EmailStr": ["email", "string"],
    "int": ["int"],
    "float": ["number"],
    "Decimal": ["decimal"],
    "bool": ["boolean"],
    "UUID": ["string", "uuid"],
    "datetime": ["datetime", "string"],
}
FIELD_LIMITS = {"min_length": "min_length", "max_length": "max_length", "ge": "min", "le": "max"}


class FastApiAdapter(FrameworkAdapter):
    name = "fastapi"
    language = "python"
    packages = {"fastapi"}

    def extract(self, files: list[SourceFile]) -> Extraction:
        result = Extraction()
        self.models = _pydantic_models(files)
        self.auth = _auth_dependencies(files)
        for file in files:
            routers = self._routers(file, result)
            for function, decorators in decorated_functions(file.root, file.source):
                for deco in decorators:
                    var, _, method = deco.name.rpartition(".")
                    if var in routers and method in ROUTE_METHODS:
                        self._route(file, function, deco, routers[var], method, result)
            self._errors(file, result)
        return result

    def _routers(self, file: SourceFile, result: Extraction) -> dict[str, str]:
        """Module level `router = APIRouter(prefix="/users")` -> {"router": "/users"}."""
        routers = {}
        for statement in file.root.children:
            assignment = statement.named_children[0] if statement.named_children else None
            if statement.type != "expression_statement" or assignment is None:
                continue
            if assignment.type != "assignment":
                continue
            found = call(assignment.child_by_field_name("right"), file.source)
            if found and found.name in ROUTER_FACTORIES:
                name = text(assignment.child_by_field_name("left"), file.source)
                routers[name] = literal(found.kwargs.get("prefix"), file.source) or ""
        for include in find_all(file.root, "call"):
            found = call(include, file.source)
            if found and found.name.endswith(".include_router") and "prefix" in found.kwargs:
                result.notes.append(
                    f"fastapi: include_router(prefix=...) in {file.path} is not supported yet"
                )
        return routers

    def _route(self, file, function, deco, prefix: str, method: str, result: Extraction) -> None:
        path = (
            literal(deco.args[0], file.source)
            if deco.args
            else literal(deco.kwargs.get("path"), file.source)
        )
        status = literal(deco.kwargs.get("status_code"), file.source) or 200
        dependencies = _decorator_dependencies(deco, file.source)
        body = None
        params = function.child_by_field_name("parameters")
        for param in params.named_children if params else []:
            default = param.child_by_field_name("value")
            used = call(default, file.source)
            if used and used.name.endswith("Depends") and used.args:
                dependencies.append(text(used.args[0], file.source))
            annotation = param.child_by_field_name("type")
            is_model = annotation is not None and text(annotation, file.source) in self.models
            if param.type == "typed_parameter" and is_model:
                body = text(annotation, file.source)

        key = route_key(method, prefix, path or "")
        name = text(function.child_by_field_name("name"), file.source)
        guards = sorted(set(dependencies) & self.auth)
        result.nodes.append(
            self.node(
                ConceptKind.ROUTE,
                key,
                name,
                file,
                function,
                method=method.upper(),
                path=display_path(prefix, path or ""),
                status=status,
                auth=bool(guards),
                guards=guards,
                body=body,
            )
        )
        if body:
            self._inputs(key, body, result)

    def _inputs(self, route: str, model: str, result: Extraction) -> None:
        file, cls = self.models[model]
        for name, annotation, value, statement in class_assignments(cls, file.source):
            constraints, optional = _field_rules(annotation, value, file.source)
            result.nodes.append(
                self.node(
                    ConceptKind.INPUT_FIELD,
                    input_key(route, name),
                    f"{model}.{name}",
                    file,
                    statement,
                    constraints=constraints,
                    required=not optional,
                )
            )

    def _errors(self, file: SourceFile, result: Extraction) -> None:
        for node in find_all(file.root, "call"):
            found = call(node, file.source)
            if found is None or found.name not in EXCEPTIONS:
                continue
            status = _status(found, file.source)
            if not isinstance(status, int):
                result.notes.append(f"fastapi: HTTPException with unknown status in {file.path}")
                continue
            result.nodes.append(
                self.node(
                    ConceptKind.ERROR, error_key(status), found.name, file, node, status=status
                )
            )


def _pydantic_models(files: list[SourceFile]) -> dict[str, tuple[SourceFile, Node]]:
    """Classes based on BaseModel, also through other models (A(BaseModel), B(A))."""
    all_classes = [(f, c) for f in files for c in classes(f.root)]
    models: dict[str, tuple[SourceFile, Node]] = {}
    changed = True
    while changed:
        changed = False
        for file, cls in all_classes:
            name = text(cls.child_by_field_name("name"), file.source)
            bases = base_names(cls, file.source)
            if name not in models and any(b in models or b.endswith("BaseModel") for b in bases):
                models[name] = (file, cls)
                changed = True
    return models


def _auth_dependencies(files: list[SourceFile]) -> set[str]:
    """Functions that raise HTTP 401 are treated as auth checks when used with Depends()."""
    names = set()
    for file in files:
        for function in find_all(file.root, "function_definition"):
            for node in find_all(function, "call"):
                found = call(node, file.source)
                if found and found.name in EXCEPTIONS and _status(found, file.source) == 401:
                    names.add(text(function.child_by_field_name("name"), file.source))
    return names


def _status(exception: Call, source: bytes) -> int | None:
    """Status of `HTTPException(status_code=404)` or `HTTPException(404)`."""
    node = exception.kwargs.get("status_code") or (exception.args[0] if exception.args else None)
    value = literal(node, source)
    return value if isinstance(value, int) else None


def _decorator_dependencies(deco, source: bytes) -> list[str]:
    """`dependencies=[Depends(check_auth)]` on the decorator."""
    listed = deco.kwargs.get("dependencies")
    found = []
    for item in listed.named_children if listed is not None else []:
        used = call(item, source)
        if used and used.name.endswith("Depends") and used.args:
            found.append(text(used.args[0], source))
    return found


def _field_rules(
    annotation: str | None, value: Node | None, source: bytes
) -> tuple[list[str], bool]:
    """Canonical constraints and whether the field is optional."""
    annotation = annotation or ""
    optional = "None" in annotation or annotation.startswith("Optional[")
    base = annotation.removeprefix("Optional[").removesuffix("]").split("|")[0].strip()
    constraints = set(TYPES.get(base, []))

    field = call(value, source)
    if field and field.name.endswith("Field"):
        for keyword, canonical in FIELD_LIMITS.items():
            if keyword in field.kwargs:
                constraints.add(f"{canonical}={literal(field.kwargs[keyword], source)}")
        has_default = "default" in field.kwargs or (field.args and field.args[0].type != "ellipsis")
        optional = optional or bool(has_default)
    elif value is not None:
        optional = True  # plain default value like `= None` or `= "x"`
    return sorted(constraints), optional
