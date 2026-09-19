"""Extract symbols, imports and env vars from one TypeScript file using tree-sitter."""

import re

import tree_sitter_typescript as ts_grammar
from tree_sitter import Language, Node, Parser, Tree

from migrator.adapters.languages.treesitter import decorator_name, lines, text
from migrator.core.models import ImportRef, ParsedFile, Symbol

TS_LANGUAGE = Language(ts_grammar.language_typescript())
TSX_LANGUAGE = Language(ts_grammar.language_tsx())

DECLARATION_KINDS = {
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "type_alias_declaration": "type",
}
VARIABLE_DECLARATIONS = {"lexical_declaration", "variable_declaration"}
MEMBER_KINDS = {
    "method_definition": "method",
    "abstract_method_signature": "method",
    "public_field_definition": "field",
}
FUNCTION_VALUES = {"arrow_function", "function_expression", "function"}

ENV_PATTERNS = [
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
]


def typescript_tree(path: str, source: bytes) -> Tree:
    language = TSX_LANGUAGE if path.endswith(".tsx") else TS_LANGUAGE
    return Parser(language).parse(source)


def parse_typescript(path: str, source: bytes) -> ParsedFile:
    root = typescript_tree(path, source).root_node
    visitor = _Visitor(path, source)
    for node in root.children:
        visitor.visit_top_level(node)

    decoded = source.decode("utf-8", errors="replace")
    env_vars = sorted({m for pattern in ENV_PATTERNS for m in pattern.findall(decoded)})
    return ParsedFile(
        path=path,
        symbols=visitor.symbols,
        imports=visitor.imports,
        env_vars=env_vars,
        parse_errors=root.has_error,
    )


class _Visitor:
    def __init__(self, path: str, source: bytes) -> None:
        self.path = path
        self.source = source
        self.symbols: list[Symbol] = []
        self.imports: list[ImportRef] = []

    def visit_top_level(
        self, node: Node, exported: bool = False, decorators: list[str] | None = None
    ) -> None:
        decorators = decorators or []
        if node.type == "import_statement":
            self._add_import(node)
        elif node.type == "export_statement":
            self._visit_export(node)
        elif node.type in DECLARATION_KINDS:
            self._add_declaration(node, exported, decorators)
        elif node.type in VARIABLE_DECLARATIONS:
            self._add_variables(node, exported)

    def _visit_export(self, node: Node) -> None:
        if node.child_by_field_name("source"):  # export { x } from "./y"
            self._add_import(node)
            return
        decorators = self._decorators(node)
        for child in node.children:
            if child.type in DECLARATION_KINDS or child.type in VARIABLE_DECLARATIONS:
                self.visit_top_level(child, exported=True, decorators=decorators)

    def _add_import(self, node: Node) -> None:
        module = text(node.child_by_field_name("source"), self.source).strip("'\"`")
        names: list[str] = []
        for child in _descendants(node):
            if child.type in ("import_specifier", "export_specifier"):
                names.append(text(child.child_by_field_name("name"), self.source))
            elif child.type == "namespace_import":
                names.append("*")
            elif (
                child.type == "identifier" and child.parent and child.parent.type == "import_clause"
            ):
                names.append(text(child, self.source))  # default import
        self.imports.append(
            ImportRef(
                file=self.path,
                module=module,
                names=names,
                line=node.start_point[0] + 1,
                type_only=any(c.type == "type" for c in node.children),
            )
        )

    def _add_declaration(self, node: Node, exported: bool, decorators: list[str]) -> None:
        name = text(node.child_by_field_name("name"), self.source)
        kind = DECLARATION_KINDS[node.type]
        self._add_symbol(node, name, kind, exported, decorators + self._decorators(node))
        if kind == "class":
            self._add_members(node, name)

    def _add_variables(self, node: Node, exported: bool) -> None:
        for declarator in node.children:
            if declarator.type != "variable_declarator":
                continue
            name_node = declarator.child_by_field_name("name")
            if name_node is None or name_node.type != "identifier":
                continue  # skip destructuring like `const { a } = b`
            value = declarator.child_by_field_name("value")
            kind = "function" if value is not None and value.type in FUNCTION_VALUES else "variable"
            self._add_symbol(declarator, text(name_node, self.source), kind, exported, [])

    def _add_members(self, class_node: Node, class_name: str) -> None:
        body = class_node.child_by_field_name("body")
        if body is None:
            return
        pending: list[str] = []
        for member in body.children:
            if member.type == "decorator":
                pending.append(decorator_name(member, self.source))
                continue
            kind = MEMBER_KINDS.get(member.type)
            if kind is None:
                continue
            name = text(member.child_by_field_name("name"), self.source)
            decorators = pending + self._decorators(member)
            self._add_symbol(member, name, kind, False, decorators, parent=class_name)
            pending = []

    def _add_symbol(
        self,
        node: Node,
        name: str,
        kind: str,
        exported: bool,
        decorators: list[str],
        parent: str | None = None,
    ) -> None:
        start, end = lines(node)
        self.symbols.append(
            Symbol(
                name=name,
                kind=kind,
                file=self.path,
                start_line=start,
                end_line=end,
                parent=parent,
                decorators=decorators,
                exported=exported,
            )
        )

    def _decorators(self, node: Node) -> list[str]:
        return [decorator_name(c, self.source) for c in node.children if c.type == "decorator"]


def _descendants(node: Node):
    for child in node.children:
        yield child
        yield from _descendants(child)
