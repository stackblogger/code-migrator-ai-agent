import pytest

from migrator.analysis.graph import CodeGraph
from migrator.core.models import ImportRef


def edge(src: str, dst: str, type_only: bool = False) -> ImportRef:
    return ImportRef(file=src, module=dst, line=1, targets=[dst], type_only=type_only)


def graph() -> CodeGraph:
    # controller -> service -> repo -> entity_a <-> entity_b ; util is alone
    files = ["controller", "service", "repo", "entity_a", "entity_b", "util"]
    imports = [
        edge("controller", "service"),
        edge("service", "repo"),
        edge("repo", "entity_a"),
        edge("entity_a", "entity_b"),
        edge("entity_b", "entity_a", type_only=True),
    ]
    return CodeGraph(files, imports)


def test_cycles_are_grouped():
    assert graph().cycles() == [["entity_a", "entity_b"]]


def test_migration_order_is_dependencies_first():
    assert graph().migration_order() == [
        ["entity_a", "entity_b"],
        ["repo"],
        ["service"],
        ["controller"],
        ["util"],
    ]


def test_queries():
    g = graph()
    assert g.dependencies("service") == ["repo"]
    assert g.dependencies("service", transitive=True) == ["entity_a", "entity_b", "repo"]
    assert g.dependents("repo") == ["service"]
    assert g.dependents("repo", transitive=True) == ["controller", "service"]
    with pytest.raises(KeyError):
        g.dependencies("nope")


def test_edge_is_type_only_only_when_all_imports_are():
    g = CodeGraph(["a", "b"], [edge("a", "b", type_only=True), edge("a", "b")])
    assert g.to_report().edges[0].type_only is False
