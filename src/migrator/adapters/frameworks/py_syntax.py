"""Helpers to read Python calls, decorators and literal values from tree-sitter nodes."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from tree_sitter import Node

from migrator.adapters.languages.treesitter import text

STATUS_CONSTANT = re.compile(r"HTTP_(\d{3})_")


@dataclass
class Call:
    name: str  # "router.get", "Depends", "mapped_column"
    args: list[Node]
    kwargs: dict[str, Node]


def call(node: Node | None, source: bytes) -> Call | None:
    if node is None or node.type != "call":
        return None
    arguments = node.child_by_field_name("arguments")
    args, kwargs = [], {}
    for child in arguments.named_children if arguments else []:
        if child.type == "keyword_argument":
            kwargs[text(child.child_by_field_name("name"), source)] = child.child_by_field_name(
                "value"
            )
        elif child.type != "comment":
            args.append(child)
    return Call(text(node.child_by_field_name("function"), source), args, kwargs)


def decorated_functions(root: Node, source: bytes) -> Iterator[tuple[Node, list[Call]]]:
    for node in root.children:
        if node.type != "decorated_definition":
            continue
        definition = node.child_by_field_name("definition")
        if definition is None or definition.type != "function_definition":
            continue
        decorators = []
        for child in node.children:
            if child.type == "decorator":
                found = call(child.named_children[0] if child.named_children else None, source)
                if found:
                    decorators.append(found)
        yield definition, decorators


def classes(root: Node) -> Iterator[Node]:
    for node in root.children:
        if node.type == "decorated_definition":
            node = node.child_by_field_name("definition") or node
        if node.type == "class_definition":
            yield node


def base_names(class_node: Node, source: bytes) -> list[str]:
    bases = class_node.child_by_field_name("superclasses")
    return [text(b, source) for b in bases.named_children] if bases else []


def class_assignments(
    class_node: Node, source: bytes
) -> Iterator[tuple[str, str | None, Node | None, Node]]:
    """(name, type annotation, value, statement) for each `name: Type = value` in the class body."""
    body = class_node.child_by_field_name("body")
    for statement in body.children if body else []:
        if statement.type != "expression_statement" or not statement.named_children:
            continue
        assignment = statement.named_children[0]
        if assignment.type != "assignment":
            continue
        left = assignment.child_by_field_name("left")
        if left is None or left.type != "identifier":
            continue
        annotation = assignment.child_by_field_name("type")
        yield (
            text(left, source),
            text(annotation, source) if annotation else None,
            assignment.child_by_field_name("right"),
            statement,
        )


def literal(node: Node | None, source: bytes) -> Any:
    """Value of a simple literal. `status.HTTP_201_CREATED` gives 201. Else None."""
    if node is None:
        return None
    if node.type == "string":
        return "".join(text(c, source) for c in node.children if c.type == "string_content")
    if node.type == "integer":
        return int(text(node, source))
    if node.type == "float":
        return float(text(node, source))
    if node.type in ("true", "false"):
        return node.type == "true"
    if node.type == "none":
        return None
    if node.type == "attribute":
        match = STATUS_CONSTANT.search(text(node, source))
        return int(match.group(1)) if match else None
    return None


def find_all(node: Node, node_type: str) -> Iterator[Node]:
    if node.type == node_type:
        yield node
    for child in node.children:
        yield from find_all(child, node_type)
