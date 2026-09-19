"""Extract symbols, imports and env vars from one Python file using tree-sitter."""

import re

import tree_sitter_python as py_grammar
from tree_sitter import Language, Node, Parser, Tree

from migrator.adapters.languages.treesitter import decorator_name, lines, text
from migrator.core.models import ImportRef, ParsedFile, Symbol

PY_LANGUAGE = Language(py_grammar.language())

ENV_PATTERNS = [
    re.compile(r"os\.environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
]
MAIN_GUARD = re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]")


def python_tree(source: bytes) -> Tree:
    return Parser(PY_LANGUAGE).parse(source)


def parse_python(path: str, source: bytes) -> ParsedFile:
    root = python_tree(source).root_node
    visitor = _Visitor(path, source)
    for node in root.children:
        visitor.visit_top_level(node)
    visitor.collect_imports(root, type_only=False)

    decoded = source.decode("utf-8", errors="replace")
    return ParsedFile(
        path=path,
        symbols=visitor.symbols,
        imports=visitor.imports,
        env_vars=sorted({m for pattern in ENV_PATTERNS for m in pattern.findall(decoded)}),
        has_main_guard=bool(MAIN_GUARD.search(decoded)),
        parse_errors=root.has_error,
    )


class _Visitor:
    def __init__(self, path: str, source: bytes) -> None:
        self.path = path
        self.source = source
        self.symbols: list[Symbol] = []
        self.imports: list[ImportRef] = []

    # ---- symbols ----

    def visit_top_level(self, node: Node) -> None:
        definition, decorators = self._unwrap_decorators(node)
        if definition.type == "class_definition":
            name = self._add_symbol(definition, "class", decorators)
            self._add_members(definition, name)
        elif definition.type == "function_definition":
            self._add_symbol(definition, "function", decorators)
        elif definition.type == "expression_statement":
            for name_node in self._assigned_names(definition):
                self._add_symbol(definition, "variable", [], name=text(name_node, self.source))

    def _add_members(self, class_node: Node, class_name: str) -> None:
        body = class_node.child_by_field_name("body")
        for member in body.children if body else []:
            definition, decorators = self._unwrap_decorators(member)
            if definition.type == "function_definition":
                self._add_symbol(definition, "method", decorators, parent=class_name)
            elif definition.type == "expression_statement":
                for name_node in self._assigned_names(definition):
                    name = text(name_node, self.source)
                    self._add_symbol(definition, "field", [], name=name, parent=class_name)

    def _unwrap_decorators(self, node: Node) -> tuple[Node, list[str]]:
        if node.type != "decorated_definition":
            return node, []
        decorators = [
            decorator_name(c, self.source) for c in node.children if c.type == "decorator"
        ]
        return node.child_by_field_name("definition") or node, decorators

    def _assigned_names(self, statement: Node) -> list[Node]:
        names = []
        for child in statement.children:
            left = child.child_by_field_name("left") if child.type == "assignment" else None
            if left is not None and left.type == "identifier":
                names.append(left)
        return names

    def _add_symbol(
        self,
        node: Node,
        kind: str,
        decorators: list[str],
        name: str | None = None,
        parent: str | None = None,
    ) -> str:
        name = name or text(node.child_by_field_name("name"), self.source)
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
                exported=not name.startswith("_"),
            )
        )
        return name

    # ---- imports (walks the whole tree, so lazy imports inside functions count too) ----

    def collect_imports(self, node: Node, type_only: bool) -> None:
        for child in node.children:
            if child.type == "import_statement":
                for name_node in child.children_by_field_name("name"):
                    self._add_import(child, self._dotted(name_node), [], type_only)
            elif child.type == "import_from_statement":
                module = text(child.child_by_field_name("module_name"), self.source)
                names = [self._dotted(n) for n in child.children_by_field_name("name")]
                if any(c.type == "wildcard_import" for c in child.children):
                    names.append("*")
                self._add_import(child, module, names, type_only)
            elif child.type == "if_statement" and self._is_type_checking(child):
                consequence = child.child_by_field_name("consequence")
                for part in child.children:
                    is_consequence = consequence is not None and part.id == consequence.id
                    self.collect_imports(part, type_only or is_consequence)
            else:
                self.collect_imports(child, type_only)

    def _add_import(self, node: Node, module: str, names: list[str], type_only: bool) -> None:
        self.imports.append(
            ImportRef(
                file=self.path,
                module=module,
                names=names,
                line=node.start_point[0] + 1,
                type_only=type_only,
            )
        )

    def _dotted(self, node: Node) -> str:
        """`a.b as c` -> "a.b"."""
        if node.type == "aliased_import":
            return text(node.child_by_field_name("name"), self.source)
        return text(node, self.source)

    def _is_type_checking(self, if_node: Node) -> bool:
        return "TYPE_CHECKING" in text(if_node.child_by_field_name("condition"), self.source)
