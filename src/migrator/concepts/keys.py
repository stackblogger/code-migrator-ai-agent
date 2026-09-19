"""Canonical keys. The same thing must get the same key in every language."""

import re

PATH_PARAM = re.compile(r"(:[A-Za-z_][A-Za-z0-9_]*|\{[^}]*\})")


def route_key(method: str, *path_parts: str) -> str:
    """`route_key("get", "users", ":id")` -> "GET /users/{}". Param names do not matter."""
    return f"{method.upper()} {canonical_path(*path_parts)}"


def canonical_path(*parts: str) -> str:
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return PATH_PARAM.sub("{}", "/" + joined)


def display_path(*parts: str) -> str:
    """Path with param names kept, in {name} style: "/users/{id}"."""
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"{\1}", "/" + joined)


def column_key(table: str, column: str) -> str:
    return f"{table}.{column}"


def input_key(route: str, field: str) -> str:
    return f"{route} body.{field}"


def error_key(status: int) -> str:
    return f"HTTP {status}"


def snake_case(name: str) -> str:
    """Used only for hints: "userId" -> "user_id"."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()
