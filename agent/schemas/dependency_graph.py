"""Dependency graph data structure with topological sorting."""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from collections import defaultdict, deque


@dataclass
class ApplicationEdge:
    """Represents an interaction edge between two internal applications.

    Populated during application analysis when code-analyzer subagents
    discover internal application-to-application interactions (i.e. between
    applications within the same codebase). External applications are tracked
    on the Application dataclass itself.
    """

    from_app: str  # Name of the calling application
    to_app: str  # Name of the callee application
    communication_protocol: List[str] = field(default_factory=list)  # e.g., ["HTTP", "HTTPS"], ["gRPC"], ["Message Queue"]
    description: str = ""  # Few sentence summary of the interaction

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "from": self.from_app,
            "to": self.to_app,
            "communication_protocol": self.communication_protocol,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApplicationEdge":
        """Deserialize from dictionary."""
        return cls(
            from_app=data["from"],
            to_app=data["to"],
            communication_protocol=data.get("communication_protocol", []),
            description=data.get("description", ""),
        )


@dataclass
class DependencyGraph:
    """Directed graph representing component dependencies (libraries and applications)."""

    nodes: List[str] = field(default_factory=list)  # Component names
    edges: Dict[str, List[str]] = field(
        default_factory=lambda: defaultdict(list)
    )  # from -> [to]

    def add_node(self, component_name: str):
        """Add a component to the graph."""
        if component_name not in self.nodes:
            self.nodes.append(component_name)

    def add_edge(self, from_component: str, to_component: str):
        """Add a dependency edge: from_component depends on to_component."""
        self.add_node(from_component)
        self.add_node(to_component)
        if to_component not in self.edges[from_component]:
            self.edges[from_component].append(to_component)

    def get_direct_dependencies(self, component_name: str) -> List[str]:
        """Get direct dependencies of a component (immediate edges only)."""
        return self.edges.get(component_name, [])

    def get_dependents(self, component_name: str) -> List[str]:
        """Get components that depend on this component."""
        return [node for node in self.nodes if component_name in self.edges[node]]

    def get_analysis_order(self) -> Tuple[List[str], List[str]]:
        """
        Get the two-phase analysis order.

        Returns:
            Tuple of (phase1_components, phase2_components_ordered)
            - phase1: Components with no dependencies (can be analyzed in parallel)
            - phase2: Remaining components in topological order
        """
        # Calculate out-degree (number of dependencies) for each node
        # In a dependency graph where edges mean "from depends on to",
        # we want to find nodes with NO outgoing edges (no dependencies)

        # Phase 1: Components with no dependencies (no outgoing edges)
        phase1 = [node for node in self.nodes if len(self.edges.get(node, [])) == 0]

        # For topological sort of remaining nodes, we need in-degree
        # (how many nodes depend on this node)
        in_degree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for dep in self.edges.get(node, []):
                in_degree[dep] += 1

        # Phase 2: Remaining components in topological order using Kahn's algorithm
        remaining_nodes = [node for node in self.nodes if node not in phase1]
        phase2 = self._topological_sort(remaining_nodes, in_degree)

        return (phase1, phase2)

    def _topological_sort(self, nodes: List[str], in_degree: Dict[str, int]) -> List[str]:
        """
        Perform topological sort on a subset of nodes using Kahn's algorithm.

        For dependency graphs, we need to analyze dependencies before dependents.
        So we process nodes with fewest dependencies first.

        Args:
            nodes: Subset of nodes to sort
            in_degree: Pre-calculated in-degrees for all nodes

        Returns:
            List of nodes in topological order (dependencies before dependents)
        """
        # Calculate out-degree (number of dependencies) for nodes in this subset
        out_degree = {}
        for node in nodes:
            # Count how many of this node's dependencies are in the remaining set
            deps_in_subset = [dep for dep in self.edges.get(node, []) if dep in nodes]
            out_degree[node] = len(deps_in_subset)

        # Start with nodes that have no dependencies within this subset
        queue = deque([node for node in nodes if out_degree[node] == 0])
        result = []

        while queue:
            # Take first node with no dependencies
            current = queue.popleft()
            result.append(current)

            # For each node that depends on current, reduce its out-degree
            for dependent in nodes:
                if current in self.edges.get(dependent, []):
                    out_degree[dependent] -= 1
                    if out_degree[dependent] == 0:
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