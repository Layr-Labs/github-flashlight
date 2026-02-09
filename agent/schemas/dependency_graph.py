"""Dependency graph data structure with topological sorting."""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from collections import defaultdict, deque


@dataclass
class DependencyGraph:
    """Directed graph representing service dependencies."""

    nodes: List[str] = field(default_factory=list)  # Service names
    edges: Dict[str, List[str]] = field(
        default_factory=lambda: defaultdict(list)
    )  # from -> [to]

    def add_node(self, service_name: str):
        """Add a service to the graph."""
        if service_name not in self.nodes:
            self.nodes.append(service_name)

    def add_edge(self, from_service: str, to_service: str):
        """Add a dependency edge: from_service depends on to_service."""
        self.add_node(from_service)
        self.add_node(to_service)
        if to_service not in self.edges[from_service]:
            self.edges[from_service].append(to_service)

    def get_direct_dependencies(self, service_name: str) -> List[str]:
        """Get direct dependencies of a service (immediate edges only)."""
        return self.edges.get(service_name, [])

    def get_dependents(self, service_name: str) -> List[str]:
        """Get services that depend on this service."""
        return [node for node in self.nodes if service_name in self.edges[node]]

    def get_analysis_order(self) -> Tuple[List[str], List[str]]:
        """
        Get the two-phase analysis order.

        Returns:
            Tuple of (phase1_services, phase2_services_ordered)
            - phase1: Services with no dependencies (can be analyzed in parallel)
            - phase2: Remaining services in topological order
        """
        # Calculate in-degree for each node
        in_degree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for dep in self.edges[node]:
                in_degree[dep] += 1

        # Phase 1: Services with no dependencies (in-degree 0)
        phase1 = [node for node in self.nodes if in_degree[node] == 0]

        # Phase 2: Remaining services in topological order using Kahn's algorithm
        remaining_nodes = [node for node in self.nodes if node not in phase1]
        phase2 = self._topological_sort(remaining_nodes, in_degree)

        return (phase1, phase2)

    def _topological_sort(self, nodes: List[str], in_degree: Dict[str, int]) -> List[str]:
        """
        Perform topological sort on a subset of nodes using Kahn's algorithm.

        Args:
            nodes: Subset of nodes to sort
            in_degree: Pre-calculated in-degrees for all nodes

        Returns:
            List of nodes in topological order
        """
        # Create a copy of in_degree for this subset
        local_in_degree = {node: in_degree[node] for node in nodes}

        # Start with nodes that have no incoming edges from within the subset
        queue = deque([node for node in nodes if local_in_degree[node] == 0])
        result = []

        while queue:
            # Take first node with no dependencies
            current = queue.popleft()
            result.append(current)

            # For each dependent, reduce in-degree
            for dependent in self.get_dependents(current):
                if dependent in local_in_degree:
                    local_in_degree[dependent] -= 1
                    if local_in_degree[dependent] == 0:
                        queue.append(dependent)

        # Check for cycles
        if len(result) != len(nodes):
            raise ValueError("Dependency graph contains cycles")

        return result

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "nodes": self.nodes,
            "edges": {k: v for k, v in self.edges.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyGraph":
        """Deserialize from dictionary."""
        graph = cls()
        graph.nodes = data["nodes"]
        graph.edges = defaultdict(list, data["edges"])
        return graph
