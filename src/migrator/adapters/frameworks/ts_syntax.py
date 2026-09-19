"""Helpers to read TypeScript decorators and literal values from tree-sitter nodes."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from tree_sitter import Node

from migrator.adapters.languages.treesitter import text


@dataclass
class Decorator:
    name: str  # "Get", "Column", ...
    args: list[Node]  # argument nodes, read them with `literal()`


@dataclass
class ClassInfo:
    node: Node
    name: str
    decorators: list[Decorator]


@dataclass
class Member:
    node: Node
    kind: str  # "method" | "field"
    name: str
    decorators: list[Decorator]


def decorator(node: Node, source: bytes) -> Decorator:
    call = next((c for c in node.children if c.type == "call_expression"), None)
    if call is None:  # plain `@Global`
        return Decorator(text(node, source).lstrip("@").strip(), [])
    name = text(call.child_by_field_name("function"), source)
    arguments = call.child_by_field_name("arguments")
    args = [a for a in arguments.named_children if a.type != "comment"] if arguments else []
    return Decorator(name, args)


def classes(root: Node, source: bytes) -> Iterator[ClassInfo]:
    """Top-level classes with their decorators (also when they are exported)."""
    for node in root.children:
        outer = [decorator(c, source) for c in node.children if c.type == "decorator"]
        target = node
        if node.type == "export_statement":
            target = next((c for c in node.children if "class" in c.type), node)
        if target.type in ("class_declaration", "abstract_class_declaration"):
            own = [decorator(c, source) for c in target.children if c.type == "decorator"]
            name = text(target.child_by_field_name("name"), source)
            yield ClassInfo(target, name, outer + own)


def members(class_node: Node, source: bytes) -> Iterator[Member]:
    body = class_node.child_by_field_name("body")
    pending: list[Decorator] = []
    for child in body.children if body else []:
        if child.type == "decorator":
            pending.append(decorator(child, source))
            continue
        kind = {"method_definition": "method", "public_field_definition": "field"}.get(child.type)
        if kind is None:
            continue
        own = [decorator(c, source) for c in child.children if c.type == "decorator"]
        yield Member(child, kind, text(child.child_by_field_name("name"), source), pending + own)
        pending = []


def literal(node: Node | None, source: bytes) -> Any:
    """Value of a simple literal. Returns None for anything that is not a plain literal."""
    if node is None:
        return None
    if node.type in ("string", "template_string"):
        return "".join(text(c, source) for c in node.children if c.type == "string_fragment")
    if node.type == "number":
        value = text(node, source)
        return float(value) if "." in value else int(value)
    if node.type in ("true", "false"):
        return node.type == "true"
    if node.type == "object":
        pairs = [c for c in node.children if c.type == "pair"]
        return {
            text(p.child_by_field_name("key"), source).strip("'\""): literal(
                p.child_by_field_name("value"), source
            )
            for p in pairs
        }
    if node.type == "array":
        return [literal(c, source) for c in node.named_children]
    return None


def type_name(node: Node | None, source: bytes) -> str | None:
    """Type from a `: Type` annotation, e.g. "CreateOrderDto"."""
    if node is None:
        return None
    annotation = node.child_by_field_name("type")
    return text(annotation, source).lstrip(":").strip() if annotation else None


def find_all(node: Node, node_type: str) -> Iterator[Node]:
    if node.type == node_type:
        yield node
    for child in node.children:
        yield from find_all(child, node_type)
