"""NestJS: controllers and routes, guards, request DTOs (class-validator), exceptions, providers."""

from migrator.adapters.frameworks.base import Extraction, FrameworkAdapter, SourceFile
from migrator.adapters.frameworks.ts_syntax import (
    ClassInfo,
    Decorator,
    classes,
    find_all,
    literal,
    members,
    type_name,
)
from migrator.adapters.languages.treesitter import text
from migrator.concepts.keys import display_path, error_key, input_key, route_key
from migrator.concepts.models import ConceptKind

HTTP_METHODS = {"Get", "Post", "Put", "Patch", "Delete", "Options", "Head", "All"}
EXCEPTIONS = {
    "BadRequestException": 400,
    "UnauthorizedException": 401,
    "ForbiddenException": 403,
    "NotFoundException": 404,
    "MethodNotAllowedException": 405,
    "NotAcceptableException": 406,
    "RequestTimeoutException": 408,
    "ConflictException": 409,
    "GoneException": 410,
    "PayloadTooLargeException": 413,
    "UnsupportedMediaTypeException": 415,
    "UnprocessableEntityException": 422,
    "InternalServerErrorException": 500,
    "NotImplementedException": 501,
    "BadGatewayException": 502,
    "ServiceUnavailableException": 503,
    "GatewayTimeoutException": 504,
}
# class-validator decorator -> canonical constraints (same words as the FastAPI adapter uses)
VALIDATORS = {
    "IsEmail": ["email", "string"],
    "IsString": ["string"],
    "IsInt": ["int"],
    "IsNumber": ["number"],
    "IsNumberString": ["numeric_string"],
    "IsBoolean": ["boolean"],
    "IsUUID": ["string", "uuid"],
    "IsDateString": ["datetime", "string"],
}
VALUE_VALIDATORS = {
    "MinLength": "min_length",
    "MaxLength": "max_length",
    "Min": "min",
    "Max": "max",
}
IMPLIES_STRING = {"MinLength", "MaxLength"}


class NestJsAdapter(FrameworkAdapter):
    name = "nestjs"
    language = "typescript"
    packages = {"@nestjs/core", "@nestjs/common"}

    def extract(self, files: list[SourceFile]) -> Extraction:
        result = Extraction()
        all_classes = {c.name: (f, c) for f in files for c in classes(f.root, f.source)}
        for file in files:
            for cls in classes(file.root, file.source):
                names = {d.name for d in cls.decorators}
                if "Controller" in names:
                    self._routes(file, cls, all_classes, result)
                if "Injectable" in names:
                    result.nodes.append(
                        self.node(ConceptKind.PROVIDER, cls.name, cls.name, file, cls.node)
                    )
            self._errors(file, result)
        return result

    def _routes(
        self,
        file: SourceFile,
        cls: ClassInfo,
        all_classes: dict[str, tuple[SourceFile, ClassInfo]],
        result: Extraction,
    ) -> None:
        controller = _find(cls.decorators, "Controller")
        prefix = _path_arg(controller, file.source) if controller else ""
        class_guards = _guards(cls.decorators, file.source)
        for member in members(cls.node, file.source):
            http = next((d for d in member.decorators if d.name in HTTP_METHODS), None)
            if member.kind != "method" or http is None:
                continue
            path = _path_arg(http, file.source)
            http_code = _find(member.decorators, "HttpCode")
            status = (
                literal(http_code.args[0], file.source) if http_code and http_code.args else None
            )
            guards = class_guards + _guards(member.decorators, file.source)
            body = _body_type(member.node, file.source)
            key = route_key(http.name, prefix, path)
            result.nodes.append(
                self.node(
                    ConceptKind.ROUTE,
                    key,
                    f"{cls.name}.{member.name}",
                    file,
                    member.node,
                    method=http.name.upper(),
                    path=display_path(prefix, path),
                    status=status or (201 if http.name == "Post" else 200),
                    auth=bool(guards),
                    guards=guards,
                    body=body,
                )
            )
            if body:
                self._inputs(key, body, all_classes, result)

    def _inputs(
        self,
        route: str,
        dto_name: str,
        all_classes: dict[str, tuple[SourceFile, ClassInfo]],
        result: Extraction,
    ) -> None:
        if dto_name not in all_classes:
            result.notes.append(f"nestjs: body type '{dto_name}' of {route} not found")
            return
        file, dto = all_classes[dto_name]
        for field in members(dto.node, file.source):
            if field.kind != "field":
                continue
            constraints, optional = set(), any(c.type == "?" for c in field.node.children)
            for deco in field.decorators:
                constraints.update(VALIDATORS.get(deco.name, []))
                if deco.name in VALUE_VALIDATORS and deco.args:
                    constraints.add(
                        f"{VALUE_VALIDATORS[deco.name]}={literal(deco.args[0], file.source)}"
                    )
                if deco.name in IMPLIES_STRING:
                    constraints.add("string")
                optional = optional or deco.name == "IsOptional"
            result.nodes.append(
                self.node(
                    ConceptKind.INPUT_FIELD,
                    input_key(route, field.name),
                    f"{dto_name}.{field.name}",
                    file,
                    field.node,
                    constraints=sorted(constraints),
                    required=not optional,
                )
            )

    def _errors(self, file: SourceFile, result: Extraction) -> None:
        for new in find_all(file.root, "new_expression"):
            name = text(new.child_by_field_name("constructor"), file.source)
            status = EXCEPTIONS.get(name)
            if name == "HttpException":
                arguments = new.child_by_field_name("arguments")
                args = arguments.named_children if arguments else []
                status = literal(args[1], file.source) if len(args) > 1 else None
                if not isinstance(status, int):
                    result.notes.append(f"nestjs: HttpException with unknown status in {file.path}")
                    continue
            if status:
                result.nodes.append(
                    self.node(
                        ConceptKind.ERROR,
                        error_key(status),
                        name,
                        file,
                        new,
                        status=status,
                    )
                )


def _find(decorators: list[Decorator], name: str) -> Decorator | None:
    return next((d for d in decorators if d.name == name), None)


def _path_arg(deco: Decorator, source: bytes) -> str:
    if not deco.args:
        return ""
    value = literal(deco.args[0], source)
    if isinstance(value, dict):  # @Controller({ path: 'users' })
        value = value.get("path", "")
    return value if isinstance(value, str) else ""


def _guards(decorators: list[Decorator], source: bytes) -> list[str]:
    return [text(arg, source) for d in decorators if d.name == "UseGuards" for arg in d.args]


def _body_type(method, source: bytes) -> str | None:
    params = method.child_by_field_name("parameters")
    for param in params.named_children if params else []:
        decorators = [c for c in param.children if c.type == "decorator"]
        if any(text(d, source).startswith("@Body") for d in decorators):
            return type_name(param, source)
    return None
