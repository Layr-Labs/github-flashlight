"""Dependency graph builder utility."""

from typing import List, Dict
from pathlib import Path
from agent.schemas.core import Component, ExternalDependency
from agent.schemas.dependency_graph import DependencyGraph


class DependencyGraphBuilder:
    """Builds component dependency graphs from discovered components."""

    def __init__(self, components: List[Component]):
        """Initialize with list of components."""
        self.components = {comp.name: comp for comp in components}
        self.graph = DependencyGraph()
        self._build_graph()

    def _build_graph(self):
        """Build the component dependency graph."""
        for name in self.components:
            self.graph.add_node(name)

        for name, comp in self.components.items():
            for dep in comp.internal_dependencies:
                if dep in self.components:
                    self.graph.add_edge(name, dep)

    def build(self) -> DependencyGraph:
        """Return the built dependency graph."""
        return self.graph

    def get_depth_order(self) -> List[List[str]]:
        """Get depth-ordered analysis buckets."""
        return self.graph.get_depth_order()

    def save_graph_visualization(self, output_path: Path):
        """Save markdown visualization of the component graph."""
        depth_order = self.get_depth_order()

        with open(output_path, "w") as f:
            f.write("# Component Dependency Graph\n\n")
            for depth, level in enumerate(depth_order):
                f.write(f"## Depth {depth}\n\n")
                for comp_name in level:
                    comp = self.components[comp_name]
                    deps = self.graph.get_direct_dependencies(comp_name)
                    f.write(f"### `{comp_name}` ({comp.kind.value})\n\n")
                    f.write(f"- **Type**: {comp.type}\n")
                    f.write(f"- **Path**: `{comp.root_path}`\n")
                    if comp.description:
                        f.write(f"- **Description**: {comp.description}\n")
                    if deps:
                        dep_list = ", ".join(f"`{d}`" for d in deps)
                        f.write(f"- **Depends On**: {dep_list}\n")
                    else:
                        f.write(f"- **Dependencies**: None\n")
                    if comp.external_dependencies:
                        ext_parts = []
                        for d in comp.external_dependencies[:5]:
                            if isinstance(d, ExternalDependency):
                                label = f"`{d.name}`"
                                if d.version:
                                    label += f" ({d.version})"
                            else:
                                label = f"`{d}`"
                            ext_parts.append(label)
                        ext = ", ".join(ext_parts)
                        if len(comp.external_dependencies) > 5:
                            ext += f" (+{len(comp.external_dependencies) - 5} more)"
                        f.write(f"- **External Dependencies**: {ext}\n")
                    f.write("\n")
