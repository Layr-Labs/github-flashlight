"""Dependency graph construction and manipulation."""

from typing import List, Dict, Tuple
from pathlib import Path
import json

from code_analysis_agent.schemas.service import Service
from code_analysis_agent.schemas.dependency_graph import DependencyGraph


class DependencyGraphBuilder:
    """Builds dependency graphs from discovered services."""

    def __init__(self, services: List[Service]):
        self.services = {s.name: s for s in services}
        self.graph = DependencyGraph()

    def build(self) -> DependencyGraph:
        """
        Build the dependency graph from services.

        Returns:
            Constructed dependency graph with analysis ordering available.
        """
        # Add all services as nodes
        for service in self.services.values():
            self.graph.add_node(service.name)

        # Add edges based on dependencies
        for service in self.services.values():
            for dep_name in service.dependencies:
                # Only add edge if dependency is an internal service
                if dep_name in self.services:
                    self.graph.add_edge(service.name, dep_name)

        return self.graph

    def get_analysis_order(self) -> Tuple[List[str], List[str]]:
        """
        Get the order in which services should be analyzed.

        Returns:
            Tuple of (phase1_services, phase2_services_ordered)
            - phase1: Services with no dependencies (can be analyzed in parallel)
            - phase2: Remaining services in topological order
        """
        return self.graph.get_analysis_order()

    def save_graph_visualization(self, output_path: Path):
        """
        Save a textual visualization of the dependency graph.
        Creates both markdown and JSON versions.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save markdown visualization
        with open(output_path, "w") as f:
            f.write("# Service Dependency Graph\n\n")

            # Write services
            f.write("## Services\n\n")
            for node in sorted(self.graph.nodes):
                service = self.services.get(node)
                if service:
                    f.write(f"- **{node}** ({service.type})\n")
                    if service.description:
                        f.write(f"  - Description: {service.description}\n")
                    f.write(f"  - Path: {service.root_path}\n\n")

            # Write dependencies
            f.write("## Dependencies\n\n")
            for node in sorted(self.graph.nodes):
                deps = self.graph.get_direct_dependencies(node)
                if deps:
                    f.write(f"- **{node}** depends on:\n")
                    for dep in sorted(deps):
                        f.write(f"  - {dep}\n")
                    f.write("\n")

            # Write analysis order
            f.write("## Analysis Order\n\n")
            phase1, phase2 = self.graph.get_analysis_order()

            f.write("### Phase 1: Services with no dependencies (analyzed in parallel)\n\n")
            for service in sorted(phase1):
                f.write(f"- {service}\n")
            f.write("\n")

            f.write("### Phase 2: Remaining services (analyzed in dependency order)\n\n")
            for i, service in enumerate(phase2, 1):
                deps = self.graph.get_direct_dependencies(service)
                f.write(f"{i}. **{service}**")
                if deps:
                    f.write(f" (depends on: {', '.join(sorted(deps))})")
                f.write("\n")
            f.write("\n")

            # Write dependency graph visualization (simple text-based)
            f.write("## Dependency Graph Visualization\n\n")
            f.write("```\n")
            phase1, phase2 = self.graph.get_analysis_order()

            f.write("PHASE 1 (No Dependencies):\n")
            for service in sorted(phase1):
                f.write(f"  [{service}]\n")

            f.write("\nPHASE 2 (Dependency Order):\n")
            for service in phase2:
                deps = self.graph.get_direct_dependencies(service)
                f.write(f"  [{service}]")
                if deps:
                    f.write(f" ← depends on: {', '.join(sorted(deps))}")
                f.write("\n")
            f.write("```\n")

        # Save JSON version
        json_path = output_path.with_suffix(".json")
        with open(json_path, "w") as f:
            phase1, phase2 = self.graph.get_analysis_order()
            json.dump(
                {
                    "graph": self.graph.to_dict(),
                    "services": {name: svc.to_dict() for name, svc in self.services.items()},
                    "analysis_order": {"phase1": phase1, "phase2": phase2},
                },
                f,
                indent=2,
            )
