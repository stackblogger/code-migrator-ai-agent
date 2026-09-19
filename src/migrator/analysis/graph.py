"""File-level dependency graph built from resolved imports.

Edges go from the importing file to the imported file. Cycles are grouped into
strongly connected components (SCCs); each group must be migrated together.
"""

import networkx as nx

from migrator.core.models import Edge, GraphReport, ImportRef


class CodeGraph:
    def __init__(self, files: list[str], imports: list[ImportRef]) -> None:
        self.graph = nx.DiGraph()
        self.graph.add_nodes_from(files)
        for imp in imports:
            for target in imp.targets:
                if target == imp.file:
                    continue
                if self.graph.has_edge(imp.file, target):
                    # Edge is type-only only if every import between the pair is type-only.
                    edge = self.graph.edges[imp.file, target]
                    edge["type_only"] = edge["type_only"] and imp.type_only
                else:
                    self.graph.add_edge(imp.file, target, type_only=imp.type_only)

    def dependencies(self, file: str, transitive: bool = False) -> list[str]:
        """Files that `file` imports."""
        self._check(file)
        found = nx.descendants(self.graph, file) if transitive else self.graph.successors(file)
        return sorted(found)

    def dependents(self, file: str, transitive: bool = False) -> list[str]:
        """Files that import `file`."""
        self._check(file)
        found = nx.ancestors(self.graph, file) if transitive else self.graph.predecessors(file)
        return sorted(found)

    def cycles(self) -> list[list[str]]:
        groups = [sorted(c) for c in nx.strongly_connected_components(self.graph) if len(c) > 1]
        return sorted(groups)

    def migration_order(self) -> list[list[str]]:
        """Groups of files, dependencies first. Files in one group depend on each other."""
        condensed = nx.condensation(self.graph)
        members = {n: sorted(condensed.nodes[n]["members"]) for n in condensed.nodes}
        # Condensed edges point importer -> dependency, so reverse to get dependencies first.
        order = nx.lexicographical_topological_sort(
            condensed.reverse(), key=lambda n: members[n][0]
        )
        return [members[n] for n in order]

    def to_report(self) -> GraphReport:
        edges = [
            Edge(source=s, target=t, type_only=data["type_only"])
            for s, t, data in sorted(self.graph.edges(data=True))
        ]
        return GraphReport(
            nodes=sorted(self.graph.nodes),
            edges=edges,
            cycles=self.cycles(),
            migration_order=self.migration_order(),
        )

    def _check(self, file: str) -> None:
        if file not in self.graph:
            raise KeyError(f"File is not in the graph: {file}")
