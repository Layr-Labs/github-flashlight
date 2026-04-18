#!/usr/bin/env python3
"""
Build dependency graph from discovered components.

This script:
1. Reads component discovery data (components.json)
2. Builds a component dependency graph using DependencyGraphBuilder
3. Computes depth-ordered analysis buckets
4. Outputs graph.json and markdown visualization

Usage:
    python scripts/build_dependency_graph.py <discovery_dir> <output_dir>
    python scripts/build_dependency_graph.py /tmp/my-service/service_discovery /tmp/my-service/dependency_graphs
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.schemas.core import Component, ExternalDependency
from agent.utils.dependency_graph import DependencyGraphBuilder


def load_components(discovery_dir: Path) -> list[Component]:
    """Load components from discovery directory."""
    components_file = discovery_dir / "components.json"
    if not components_file.exists():
        raise FileNotFoundError(f"components.json not found in {discovery_dir}")

    with open(components_file) as f:
        data = json.load(f)

    if isinstance(data, dict):
        comp_list = data.get("components", [])
    elif isinstance(data, list):
        comp_list = data
    else:
        raise ValueError(f"Unknown components.json format in {discovery_dir}")

    return [Component.from_dict(c) for c in comp_list]


def build_graph_json(builder: DependencyGraphBuilder) -> dict:
    """Build graph.json output structure."""
    graph = builder.graph
    depth_order = builder.get_depth_order()

    # Build depth map for each component
    depth_map: dict[str, int] = {}
    for depth, level in enumerate(depth_order):
        for name in level:
            depth_map[name] = depth

    nodes = []
    for comp_name in graph.nodes:
        comp = builder.components[comp_name]
        node = {
            "id": comp_name,
            "kind": comp.kind.value,
            "type": comp.type,
            "depth": depth_map.get(comp_name, 0),
        }
        if comp.external_dependencies:
            node["external_dependencies"] = [
                d.to_dict() if isinstance(d, ExternalDependency) else d
                for d in comp.external_dependencies
            ]
        nodes.append(node)

    edges = []
    for from_node, to_nodes in graph.edges.items():
        for to_node in to_nodes:
            edges.append({"from": from_node, "to": to_node})

    return {
        "graph_type": "component_dependencies",
        "nodes": nodes,
        "edges": edges,
        "depth_order": depth_order,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build dependency graph and compute analysis order"
    )
    parser.add_argument(
        "discovery_dir",
        help="Path to service_discovery directory (containing components.json)",
    )
    parser.add_argument(
        "output_dir",
        help="Directory to write graph outputs",
    )

    args = parser.parse_args()

    discovery_dir = Path(args.discovery_dir)
    output_dir = Path(args.output_dir)

    if not discovery_dir.exists():
        print(f"Error: Discovery directory not found: {discovery_dir}", file=sys.stderr)
        sys.exit(1)

    # Load components
    print(f"Loading components from {discovery_dir}...")
    components = load_components(discovery_dir)
    print(f"Found {len(components)} components")

    # Build dependency graph
    print("\nBuilding component dependency graph...")
    builder = DependencyGraphBuilder(components)
    depth_order = builder.get_depth_order()

    for i, level in enumerate(depth_order):
        print(f"  Depth {i}: {len(level)} components")

    # Build JSON output
    graph_json = build_graph_json(builder)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write graph
    graph_path = output_dir / "graph.json"
    with open(graph_path, "w") as f:
        json.dump(graph_json, f, indent=2)
    print(f"\nWrote {graph_path}")

    # Write markdown visualization
    md_path = output_dir / "graph.md"
    builder.save_graph_visualization(md_path)
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
