"""Dependency graph builder utility."""

from typing import List, Tuple, Dict
from pathlib import Path
from agent.schemas.service import Library, Application
from agent.schemas.dependency_graph import DependencyGraph


class DependencyGraphBuilder:
    """Builds library dependency graphs from service definitions."""

    def __init__(self, libraries: List[Library]):
        """Initialize with list of libraries."""
        self.services = {lib.name: lib for lib in libraries}
        self.graph = DependencyGraph()
        self._build_graph()

    def _build_graph(self):
        """Build the library dependency graph."""
        # Add all library nodes
        for lib_name in self.services:
            self.graph.add_node(lib_name)

        # Add edges for internal library dependencies
        for lib_name, lib in self.services.items():
            for dep in lib.dependencies:
                # Only add edge if dependency is an internal library
                if dep in self.services:
                    self.graph.add_edge(lib_name, dep)

    def build(self) -> DependencyGraph:
        """Return the built dependency graph."""
        return self.graph

    def get_analysis_order(self) -> Tuple[List[str], List[str]]:
        """
        Get two-phase analysis order.

        Returns:
            Tuple of (phase1_libraries, phase2_libraries_ordered)
        """
        return self.graph.get_analysis_order()

    def save_graph_visualization(self, output_path: Path):
        """Save markdown visualization of the library graph."""
        phase1, phase2 = self.get_analysis_order()

        with open(output_path, 'w') as f:
            f.write("# Library Dependency Graph\n\n")
            f.write("## Phase 1: Foundation Libraries (No Dependencies)\n\n")
            if phase1:
                for lib_name in phase1:
                    lib = self.services[lib_name]
                    f.write(f"### `{lib_name}`\n\n")
                    f.write(f"- **Type**: {lib.type}\n")
                    f.write(f"- **Path**: `{lib.root_path}`\n")
                    if lib.description:
                        f.write(f"- **Description**: {lib.description}\n")
                    f.write(f"- **Dependencies**: None\n")
                    if lib.external_dependencies:
                        ext = ', '.join(f"`{d}`" for d in lib.external_dependencies[:5])
                        if len(lib.external_dependencies) > 5:
                            ext += f" (+{len(lib.external_dependencies) - 5} more)"
                        f.write(f"- **External Dependencies**: {ext}\n")
                    f.write("\n")
            else:
                f.write("*(None)*\n\n")

            f.write("## Phase 2: Dependent Libraries (Topological Order)\n\n")
            if phase2:
                for lib_name in phase2:
                    lib = self.services[lib_name]
                    deps = self.graph.get_direct_dependencies(lib_name)
                    f.write(f"### `{lib_name}`\n\n")
                    f.write(f"- **Type**: {lib.type}\n")
                    f.write(f"- **Path**: `{lib.root_path}`\n")
                    if lib.description:
                        f.write(f"- **Description**: {lib.description}\n")
                    if deps:
                        dep_list = ', '.join(f"`{d}`" for d in deps)
                        f.write(f"- **Depends On**: {dep_list}\n")
                    if lib.external_dependencies:
                        ext = ', '.join(f"`{d}`" for d in lib.external_dependencies[:5])
                        if len(lib.external_dependencies) > 5:
                            ext += f" (+{len(lib.external_dependencies) - 5} more)"
                        f.write(f"- **External Dependencies**: {ext}\n")
                    f.write("\n")
            else:
                f.write("*(None)*\n\n")
