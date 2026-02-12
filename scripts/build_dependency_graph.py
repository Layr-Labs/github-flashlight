#!/usr/bin/env python3
"""
Build dependency graphs using existing graph utilities.

This script:
1. Reads component discovery data (components.json)
2. Builds library and application graphs using existing DependencyGraphBuilder
3. Performs topological sort for library analysis order
4. Outputs library_graph.json and application_graph.json

Usage:
    python scripts/build_dependency_graph.py <components_file> <output_dir>
    python scripts/build_dependency_graph.py files/service_discovery/components.json files/dependency_graphs
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.schemas.service import Library, Application
from agent.utils.dependency_graph import DependencyGraphBuilder


def load_components(components_file: Path) -> tuple[list[Library], list[Application]]:
    """
    Load components and convert to Service objects.

    Returns:
        Tuple of (libraries, applications) as Service objects
    """
    with open(components_file) as f:
        data = json.load(f)

    libraries = []
    for lib in data.get('libraries', []):
        # Create Library objects
        libraries.append(Library(
            name=lib['name'],
            type=lib.get('type', 'unknown'),
            root_path=Path(lib.get('root_path', lib['name'])),
            description=lib.get('description', ''),
            manifest_path=Path(lib['manifest_path']) if lib.get('manifest_path') else None,
            dependencies=lib.get('dependencies', []),  # Other internal libraries
            external_dependencies=lib.get('external_dependencies', []),  # Third-party packages
            key_files=[Path(f) for f in lib.get('key_files', [])]
        ))

    applications = []
    for app in data.get('applications', []):
        # Create Application objects with new dependency fields
        applications.append(Application(
            name=app['name'],
            type=app.get('type', 'unknown'),
            root_path=Path(app.get('root_path', app['name'])),
            description=app.get('description', ''),
            manifest_path=Path(app['manifest_path']) if app.get('manifest_path') else None,
            external_dependencies=app.get('external_dependencies', []),  # Third-party apps
            libraries_used=app.get('libraries_used', []),  # Internal libraries
            caller_dependencies=app.get('caller_dependencies', []),  # Apps that call this one
            callee_dependencies=app.get('callee_dependencies', []),  # Apps this one calls
            key_files=[Path(f) for f in app.get('key_files', [])]
        ))

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
        nodes.append({
            'id': lib_name,
            'type': service.type,
            'classification': 'library',
            'phase': 1 if lib_name in phase1 else 2
        })

    # Build edges (from -> to where 'from' depends on 'to')
    edges = []
    for from_node, to_nodes in graph.edges.items():
        for to_node in to_nodes:
            edges.append({
                'from': from_node,
                'to': to_node
            })

    return {
        'graph_type': 'library_dependencies',
        'nodes': nodes,
        'edges': edges,
        'analysis_order': {
            'phase1': phase1,
            'phase2': phase2
        }
    }


def build_application_graph_json(applications: list[Application], libraries: list[Library]) -> dict:
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
        "external_dependencies": ["third-party apps that interact with application"],
        "caller_dependencies": ["application components that call this one"],
        "callee_dependencies": ["application components this one calls"],
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

        nodes.append({
            'id': app.name,
            'type': app.type,
            'classification': 'application',
            'libraries_used': libraries_used,
            'external_dependencies': app.external_dependencies,  # Third-party apps
            'caller_dependencies': app.caller_dependencies,  # Apps that call this one
            'callee_dependencies': app.callee_dependencies,  # Apps this one calls
            'key_files': [str(f) for f in app.key_files]
        })

    return {
        'graph_type': 'application_interactions',
        'nodes': nodes,
        'edges': []  # Edges discovered and added during application analysis
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build dependency graphs and compute analysis order"
    )
    parser.add_argument(
        "components_file",
        help="Path to components.json file"
    )
    parser.add_argument(
        "output_dir",
        help="Directory to write graph outputs"
    )

    args = parser.parse_args()

    components_file = Path(args.components_file)
    output_dir = Path(args.output_dir)

    if not components_file.exists():
        print(f"Error: Components file not found: {components_file}", file=sys.stderr)
        sys.exit(1)

    # Load components
    print(f"Loading components from {components_file}...")
    libraries, applications = load_components(components_file)

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
    with open(lib_graph_path, 'w') as f:
        json.dump(library_graph_json, f, indent=2)
    print(f"\n✓ Wrote {lib_graph_path}")

    # Write application graph
    app_graph_path = output_dir / "application_graph.json"
    with open(app_graph_path, 'w') as f:
        json.dump(application_graph_json, f, indent=2)
    print(f"✓ Wrote {app_graph_path}")

    # Write markdown visualizations using existing method
    lib_md_path = output_dir / "library_graph.md"
    lib_builder.save_graph_visualization(lib_md_path)
    print(f"✓ Wrote {lib_md_path}")

    # Simple application graph markdown
    app_md_path = output_dir / "application_graph.md"
    with open(app_md_path, 'w') as f:
        f.write("# Application Interaction Graph\n\n")
        f.write("## Applications\n\n")
        for node in application_graph_json['nodes']:
            f.write(f"### `{node['id']}`\n\n")
            f.write(f"- **Type**: {node['type']}\n")
            if node['libraries_used']:
                libs = ', '.join(f"`{lib}`" for lib in node['libraries_used'])
                f.write(f"- **Uses Libraries**: {libs}\n")
            if node['external_dependencies']:
                ext_deps = ', '.join(f"`{dep}`" for dep in node['external_dependencies'][:5])
                if len(node['external_dependencies']) > 5:
                    ext_deps += f" (+{len(node['external_dependencies']) - 5} more)"
                f.write(f"- **External Dependencies**: {ext_deps}\n")
            if node.get('caller_dependencies'):
                callers = ', '.join(f"`{caller}`" for caller in node['caller_dependencies'])
                f.write(f"- **Called By**: {callers}\n")
            if node.get('callee_dependencies'):
                callees = ', '.join(f"`{callee}`" for callee in node['callee_dependencies'])
                f.write(f"- **Calls**: {callees}\n")
            if node.get('key_files'):
                files = ', '.join(f"`{kf}`" for kf in node['key_files'][:3])
                if len(node['key_files']) > 3:
                    files += f" (+{len(node['key_files']) - 3} more)"
                f.write(f"- **Key Files**: {files}\n")
            f.write("\n")
        f.write("## Interactions\n\n")
        if application_graph_json['edges']:
            for edge in application_graph_json['edges']:
                protocols = ', '.join(edge['communication_protocol']) if edge.get('communication_protocol') else 'Unknown'
                f.write(f"- **`{edge['from']}`** → **`{edge['to']}`**\n")
                f.write(f"  - **Protocol**: {protocols}\n")
                if edge.get('description'):
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
        print(f"  Phase 2: none")


if __name__ == "__main__":
    main()
