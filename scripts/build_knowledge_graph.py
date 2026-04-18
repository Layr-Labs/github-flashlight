#!/usr/bin/env python3
"""
Build unified knowledge graph from discovered components.

This script:
1. Reads component discovery data (components.json)
2. Builds a unified KnowledgeGraph with all component kinds
3. Computes depth-ordered analysis buckets
4. Outputs graph.json

Usage:
    python scripts/build_knowledge_graph.py <discovery_dir> <output_dir>
    python scripts/build_knowledge_graph.py /tmp/my-service/service_discovery /tmp/my-service

The output graph.json replaces the old library_graph.json and application_graph.json.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.schemas.core import Component, ComponentKind
from agent.schemas.knowledge_graph import KnowledgeGraph, KnowledgeGraphBuilder


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


def main():
    parser = argparse.ArgumentParser(
        description="Build unified knowledge graph from discovered components"
    )
    parser.add_argument(
        "discovery_dir",
        help="Path to service_discovery directory (containing components.json)",
    )
    parser.add_argument(
        "output_dir",
        help="Directory to write graph.json",
    )
    parser.add_argument(
        "--source-repo",
        default="",
        help="Repository URL for provenance",
    )
    parser.add_argument(
        "--source-commit",
        default="",
        help="Git commit hash for provenance",
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

    # Count by kind
    by_kind = {}
    for kind in ComponentKind:
        count = sum(1 for c in components if c.kind == kind)
        if count > 0:
            by_kind[kind.value] = count
    print(f"  By kind: {by_kind}")

    # Build knowledge graph
    print("\nBuilding knowledge graph...")
    builder = KnowledgeGraphBuilder(components)
    graph = builder.build(
        source_repo=args.source_repo,
        source_commit=args.source_commit,
    )

    # Get analysis order
    depth_order = builder.get_analysis_order()
    print(f"\nAnalysis order ({len(depth_order)} depth levels):")
    for i, level in enumerate(depth_order):
        print(f"  Depth {i}: {len(level)} components")
        if len(level) <= 5:
            print(f"    {', '.join(level)}")
        else:
            print(f"    {', '.join(level[:5])} (+{len(level) - 5} more)")

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)

    # Main graph.json
    graph_path = output_dir / "graph.json"
    with open(graph_path, "w") as f:
        json.dump(graph.to_dict(), f, indent=2)
    print(f"\nWrote {graph_path}")

    # Also write a separate analysis_order.json for the lead agent
    order_path = output_dir / "analysis_order.json"
    order_data = {
        "depth_levels": depth_order,
        "total_components": len(components),
        "level_count": len(depth_order),
    }
    with open(order_path, "w") as f:
        json.dump(order_data, f, indent=2)
    print(f"Wrote {order_path}")

    # Summary
    print(f"\nGraph summary:")
    print(f"  Components: {len(graph.components)}")
    print(f"  Edges: {len(graph.edges)}")
    print(f"  External services: {len(graph.external_services)}")


if __name__ == "__main__":
    main()
