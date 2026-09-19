"""Small helpers over tree-sitter so adapters stay short."""

from tree_sitter import Node


def text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def lines(node: Node) -> tuple[int, int]:
    """1-based start and end line."""
    return node.start_point[0] + 1, node.end_point[0] + 1


def decorator_name(node: Node, source: bytes) -> str:
    """`@Controller("x")` -> "Controller", `@app.get("/")` -> "app.get"."""
    return text(node, source).lstrip("@").split("(")[0].strip()
