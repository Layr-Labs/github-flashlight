#!/usr/bin/env python3
"""
Build dependency graphs using existing graph utilities.

This script:
1. Reads component discovery data (libraries.json and applications.json)
2. Builds library and application graphs using existing DependencyGraphBuilder
3. Performs topological sort for library analysis order
4. Outputs library_graph.json and application_graph.json

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

from agent.schemas.core import Library, Application, ExternalDependency
from agent.utils.dependency_graph import DependencyGraphBuilder


def load_components(discovery_dir: Path) -> tuple[list[Library], list[Application]]:
    """
    Load components from discovery directory.

    Reads libraries.json and applications.json from the discovery directory.

    Returns:
        Tuple of (libraries, applications) as typed objects
    """
    libraries = []
    applications = []

    # Load libraries
    libraries_file = discovery_dir / "libraries.json"
    if libraries_file.exists():
        with open(libraries_file) as f:
            data = json.load(f)
        for lib in data.get("libraries", []):
            libraries.append(
                Library(
                    name=lib["name"],
                    type=lib.get("type", "unknown"),
                    root_path=Path(lib.get("root_path", lib["name"])),
                    description=lib.get("description", ""),
                    manifest_path=Path(lib["manifest_path"])
                    if lib.get("manifest_path")
                    else None,
                    internal_dependencies=lib.get("internal_dependencies", []),
                    external_dependencies=[
                        ExternalDependency.from_dict(d)
                        for d in lib.get("external_dependencies", [])
                    ],
                    key_files=[Path(f) for f in lib.get("key_files", [])],
                )
            )

    # Load applications
    applications_file = discovery_dir / "applications.json"
    if applications_file.exists():
        with open(applications_file) as f:
            data = json.load(f)
        for app in data.get("applications", []):
            applications.append(
                Application(
                    name=app["name"],
                    type=app.get("type", "unknown"),
                    root_path=Path(app.get("root_path", app["name"])),
                    description=app.get("description", ""),
                    manifest_path=Path(app["manifest_path"])
                    if app.get("manifest_path")
                    else None,
                    external_dependencies=[
                        ExternalDependency.from_dict(d)
                        for d in app.get("external_dependencies", [])
                    ],
                    libraries_used=app.get("libraries_used", []),
                    internal_applications=app.get("internal_applications", []),
                    key_files=[Path(f) for f in app.get("key_files", [])],
                )
            )

    # Fallback: try loading from a single components.json for backward compatibility
    if not libraries and not applications:
        components_file = discovery_dir / "components.json"
        if components_file.exists():
            with open(components_file) as f:
                data = json.load(f)
            for lib in data.get("libraries", []):
                libraries.append(
                    Library(
                        name=lib["name"],
                        type=lib.get("type", "unknown"),
                        root_path=Path(lib.get("root_path", lib["name"])),
                        description=lib.get("description", ""),
                        manifest_path=Path(lib["manifest_path"])
                        if lib.get("manifest_path")
                        else None,
                        internal_dependencies=lib.get("internal_dependencies", []),
                        external_dependencies=[
                            ExternalDependency.from_dict(d)
                            for d in lib.get("external_dependencies", [])
                        ],
                        key_files=[Path(f) for f in lib.get("key_files", [])],
                    )
                )
            for app in data.get("applications", []):
                applications.append(
                    Application(
                        name=app["name"],
                        type=app.get("type", "unknown"),
                        root_path=Path(app.get("root_path", app["name"])),
                        description=app.get("description", ""),
                        manifest_path=Path(app["manifest_path"])
                        if app.get("manifest_path")
                        else None,
                        external_dependencies=[
                            ExternalDependency.from_dict(d)
                            for d in app.get("external_dependencies", [])
                        ],
                        libraries_used=app.get("libraries_used", []),
                        internal_applications=app.get("internal_applications", []),
                        key_files=[Path(f) for f in app.get("key_files", [])],
                    )
                )

    return libraries, applications


def build_library_graph_json(builder: DependencyGraphBuilder) -> dict:
    """
    Build library_graph.json output structure.

    Matches the data model specified in lead_agent.txt:
    {
      "graph_type": "library_dependencies",
      "nodes": [{
        "id": "library-name",
        "type": "rust-crate" | "nodejs-package" | "python-package",
        "classification": "library",
        "external_dependencies": [{"name": "...", "version": "...", "category": "...", "purpose": "..."}],
        "phase": 1 | 2
      }],
      "edges": [{"from": "library-a", "to": "library-b"}],
      "analysis_order": {
        "phase1": [...],  // Libraries with no dependencies
        "phase2": [...]   // Libraries in topological order
      }
    }
    """
    graph = builder.graph
    phase1, phase2 = builder.get_analysis_order()

    # Build nodes with phase assignments
    nodes = []
    for lib_name in graph.nodes:
        service = builder.services[lib_name]
        node = {
            "id": lib_name,
            "type": service.type,
            "classification": "library",
            "phase": 1 if lib_name in phase1 else 2,
        }
        if service.external_dependencies:
            node["external_dependencies"] = [
                d.to_dict() if isinstance(d, ExternalDependency) else d
                for d in service.external_dependencies
            ]
        nodes.append(node)

    # Build edges (from -> to where 'from' depends on 'to')
    edges = []
    for from_node, to_nodes in graph.edges.items():
        for to_node in to_nodes:
            edges.append(
                {
                    "from": from_node,
                    "to": to_node,
                }
            )

    return {
        "graph_type": "library_dependencies",
        "nodes": nodes,
        "edges": edges,
        "analysis_order": {
            "phase1": phase1,
            "phase2": phase2,
        },
    }


def build_application_graph_json(
    applications: list[Application], libraries: list[Library]
) -> dict:
    """
    Build initial application_graph.json (nodes only, edges added during analysis).

    Matches the data model specified in lead_agent.txt:
    {
      "graph_type": "application_interactions",
      "nodes": [{
        "id": "application-name",
        "type": "rust-crate" | "nodejs-package" | "python-package",
        "classification": "application",
        "libraries_used": ["internal library names"],
        "external_dependencies": [{"name": "...", "version": "...", "category": "...", "purpose": "..."}],
        "internal_applications": ["other apps this one calls"],
        "key_files": ["important source files"]
      }],
      "edges": [
        {
          "from": "calling-application",
          "to": "callee-application",
          "communication_protocol": ["HTTP", "HTTPS"],
          "description": "Few sentence summary of interaction"
        }
      ]
    }

    Note: Edges are populated during application analysis when code-analyzer
    subagents discover application-to-application interactions. See ApplicationEdge
    schema in agent/schemas/dependency_graph.py for edge structure.
    """
    library_names = {lib.name for lib in libraries}

    nodes = []
    for app in applications:
        # Filter libraries_used to only include actual internal libraries
        libraries_used = [dep for dep in app.libraries_used if dep in library_names]

        nodes.append(
            {
                "id": app.name,
                "type": app.type,
                "classification": "application",
                "libraries_used": libraries_used,
                "external_dependencies": [
                    d.to_dict() if isinstance(d, ExternalDependency) else d
                    for d in app.external_dependencies
                ],
                "internal_applications": app.internal_applications,
                "key_files": [str(f) for f in app.key_files],
            }
        )

    return {
        "graph_type": "application_interactions",
        "nodes": nodes,
        "edges": [],  # Edges discovered and added during application analysis
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build dependency graphs and compute analysis order"
    )
    parser.add_argument(
        "discovery_dir",
        help="Path to service_discovery directory (containing libraries.json and applications.json)",
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
    libraries, applications = load_components(discovery_dir)

    print(f"Found {len(libraries)} libraries and {len(applications)} applications")

    # Build library dependency graph
    print("\nBuilding library dependency graph...")
    lib_builder = DependencyGraphBuilder(libraries)
    lib_graph = lib_builder.build()
    phase1, phase2 = lib_builder.get_analysis_order()

    print(f"  Phase 1: {len(phase1)} libraries (no dependencies)")
    print(f"  Phase 2: {len(phase2)} libraries (topological order)")

    # Build JSON outputs
    library_graph_json = build_library_graph_json(lib_builder)
    application_graph_json = build_application_graph_json(applications, libraries)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write library graph
    lib_graph_path = output_dir / "library_graph.json"
    with open(lib_graph_path, "w") as f:
        json.dump(library_graph_json, f, indent=2)
    print(f"\n✓ Wrote {lib_graph_path}")

    # Write application graph
    app_graph_path = output_dir / "application_graph.json"
    with open(app_graph_path, "w") as f:
        json.dump(application_graph_json, f, indent=2)
    print(f"✓ Wrote {app_graph_path}")

    # Write markdown visualizations using existing method
    lib_md_path = output_dir / "library_graph.md"
    lib_builder.save_graph_visualization(lib_md_path)
    print(f"✓ Wrote {lib_md_path}")

    # Simple application graph markdown
    app_md_path = output_dir / "application_graph.md"
    with open(app_md_path, "w") as f:
        f.write("# Application Interaction Graph\n\n")
        f.write("## Applications\n\n")
        for node in application_graph_json["nodes"]:
            f.write(f"### `{node['id']}`\n\n")
            f.write(f"- **Type**: {node['type']}\n")
            if node["libraries_used"]:
                libs = ", ".join(f"`{lib}`" for lib in node["libraries_used"])
                f.write(f"- **Uses Libraries**: {libs}\n")
            if node["external_dependencies"]:
                ext_deps_display = []
                for dep in node["external_dependencies"][:8]:
                    if isinstance(dep, dict):
                        name = dep.get("name", str(dep))
                        version = dep.get("version", "")
                        ext_deps_display.append(
                            f"`{name}`" + (f" ({version})" if version else "")
                        )
                    else:
                        ext_deps_display.append(f"`{dep}`")
                ext_str = ", ".join(ext_deps_display)
                remaining = len(node["external_dependencies"]) - 8
                if remaining > 0:
                    ext_str += f" (+{remaining} more)"
                f.write(f"- **External Dependencies**: {ext_str}\n")
            if node.get("internal_applications"):
                apps = ", ".join(f"`{a}`" for a in node["internal_applications"])
                f.write(f"- **Interacts With**: {apps}\n")
            if node.get("key_files"):
                files = ", ".join(f"`{kf}`" for kf in node["key_files"][:3])
                if len(node["key_files"]) > 3:
                    files += f" (+{len(node['key_files']) - 3} more)"
                f.write(f"- **Key Files**: {files}\n")
            f.write("\n")
        f.write("## Interactions\n\n")
        if application_graph_json["edges"]:
            for edge in application_graph_json["edges"]:
                protocols = (
                    ", ".join(edge["communication_protocol"])
                    if edge.get("communication_protocol")
                    else "Unknown"
                )
                f.write(f"- **`{edge['from']}`** → **`{edge['to']}`**\n")
                f.write(f"  - **Protocol**: {protocols}\n")
                if edge.get("description"):
                    f.write(f"  - **Description**: {edge['description']}\n")
                f.write("\n")
        else:
            f.write("*(Edges will be populated during application analysis)*\n")
    print(f"✓ Wrote {app_md_path}")

    print("\nAnalysis order:")
    print(f"  Phase 1 (parallel): {', '.join(phase1) if phase1 else 'none'}")
    if phase2:
        print(f"  Phase 2 (sequential): {', '.join(phase2)}")
    else:
        print("  Phase 2: none")


if __name__ == "__main__":
    main()
