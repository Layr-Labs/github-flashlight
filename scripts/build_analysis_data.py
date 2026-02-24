#!/usr/bin/env python3
"""
Build analysisData.js from analysis output files.

Reads the /tmp/{PROJECT} directory structure and generates a JavaScript
data file for the React website template by directly translating:
- service_analyses/*.md  → components[]
- dependency_graphs/*.json → libraryGraph, applicationGraph
- architecture_docs/architecture.md → architecture

Usage:
    python scripts/build_analysis_data.py <project_dir>
    python scripts/build_analysis_data.py /tmp/my-project
    python scripts/build_analysis_data.py /tmp/my-project --output /tmp/my-project/website/src/data/analysisData.js
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Markdown section extraction
# ---------------------------------------------------------------------------

def extract_section(markdown: str, heading: str, level: int = 2) -> str | None:
    """
    Extract a markdown section by heading (e.g. '## Key Components').

    Returns the content from the heading until the next same-level heading.
    Returns None if the heading is not found.
    """
    # Build a regex pattern for the heading
    pattern = rf'^{"#" * level}\s+{re.escape(heading)}\s*$'
    match = re.search(pattern, markdown, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None

    # Find the start of the section
    start_pos = match.end()

    # Find the next same-level or higher-level heading
    next_heading_pattern = rf'^#{{{1},{level}}}(?!#)\s+.+$'
    next_match = re.search(next_heading_pattern, markdown[start_pos:], re.MULTILINE)

    if next_match:
        end_pos = start_pos + next_match.start()
        return markdown[start_pos:end_pos].strip()
    else:
        return markdown[start_pos:].strip()


def extract_metadata(markdown: str) -> dict:
    """Extract metadata from YAML-like frontmatter or bold key-value pairs."""
    metadata = {}

    # Try to match bold key-value pairs (e.g. **Timestamp**: 2024-01-01)
    pattern = r'^\*\*([^*]+)\*\*:\s*(.+)$'
    for match in re.finditer(pattern, markdown, re.MULTILINE):
        key = match.group(1).strip().lower().replace(' ', '_')
        value = match.group(2).strip()
        metadata[key] = value

    return metadata


def extract_first_paragraph(markdown: str) -> str:
    """
    Extract the first non-empty paragraph from markdown text.

    Skips YAML frontmatter, metadata lines, and headings.
    """
    lines = markdown.split('\n')
    paragraph_lines = []
    in_paragraph = False

    for line in lines:
        stripped = line.strip()

        # Skip empty lines before paragraph starts
        if not in_paragraph and not stripped:
            continue

        # Skip metadata lines (e.g., **Key**: Value)
        if re.match(r'^\*\*[^*]+\*\*:', stripped):
            continue

        # Skip headings
        if stripped.startswith('#'):
            continue

        # Start collecting paragraph
        if not in_paragraph and stripped:
            in_paragraph = True
            paragraph_lines.append(stripped)
        elif in_paragraph:
            if not stripped:
                # End of paragraph
                break
            paragraph_lines.append(stripped)

    return ' '.join(paragraph_lines)


# ---------------------------------------------------------------------------
# Component parsing (service_analyses/*.md)
# ---------------------------------------------------------------------------

def parse_component_markdown(md_path: Path) -> dict | None:
    """Parse a service analysis markdown file into a component object."""
    if not md_path.is_file():
        return None

    with open(md_path, encoding='utf-8') as f:
        markdown = f.read()

    # Extract component name from filename (e.g., 'api.md' → 'api')
    name = md_path.stem

    # Extract metadata
    metadata = extract_metadata(markdown)

    # Extract sections
    architecture = extract_section(markdown, 'Architecture', level=2)
    key_components = extract_section(markdown, 'Key Components', level=2)
    system_flows = extract_section(markdown, 'System Flows', level=2)
    data_flows = extract_section(markdown, 'Data Flows', level=2)
    external_dependencies = extract_section(markdown, 'External Dependencies', level=2)
    internal_dependencies = extract_section(markdown, 'Internal Dependencies', level=2)
    api_surface = extract_section(markdown, 'API Surface', level=2)

    # Extract first paragraph as description
    description = extract_first_paragraph(architecture or markdown)

    # Determine type
    component_type = metadata.get('classification', 'unknown')
    if component_type == 'unknown':
        component_type = metadata.get('application_type', 'unknown')

    return {
        "name": name,
        "type": component_type,
        "description": description if description else f"{name} component",
        "architecture": architecture,
        "keyComponents": key_components,
        "systemFlows": system_flows,
        "dataFlows": data_flows,
        "externalDependencies": external_dependencies,
        "internalDependencies": internal_dependencies,
        "apiSurface": api_surface,
        "markdownContent": markdown,
    }


def load_components(service_analyses_dir: Path) -> list[dict]:
    """Load all component markdown files from service_analyses directory."""
    components = []

    if not service_analyses_dir.is_dir():
        print(f"Warning: service_analyses directory not found: {service_analyses_dir}", file=sys.stderr)
        return components

    md_files = sorted(service_analyses_dir.glob("*.md"))
    print(f"  Found {len(md_files)} service analysis files")

    for md_file in md_files:
        print(f"    Processing: {md_file.name}")
        component = parse_component_markdown(md_file)
        if component:
            components.append(component)

    print(f"  Total: {len(components)} components", end="")

    # Count applications vs libraries vs external services using the shared classifier
    apps = sum(1 for c in components if _classify(c['type']) == 'application')
    libs = sum(1 for c in components if _classify(c['type']) == 'library')
    externals = sum(1 for c in components if _classify(c['type']) == 'external-service')
    unknown = len(components) - apps - libs - externals
    ext_suffix = f", {externals} external services" if externals else ""
    unk_suffix = f", {unknown} unclassified" if unknown else ""
    print(f" ({apps} applications, {libs} libraries{ext_suffix}{unk_suffix})")

    return components


# ---------------------------------------------------------------------------
# Graph parsing (dependency_graphs/*.json)
# ---------------------------------------------------------------------------

def transform_edges_from_adjacency_list(edges_dict: dict) -> list[dict]:
    """Transform adjacency list edges to D3.js edge format.

    Input: {"node1": ["target1", "target2"], "node2": ["target3"]}
    Output: [{"source": "node1", "target": "target1"}, ...]
    """
    edge_list = []
    for source, targets in edges_dict.items():
        for target in targets:
            edge_list.append({"source": source, "target": target})
    return edge_list


_PROTOCOL_TO_TYPE = {
    'grpc':             'gRPC',
    'http':             'http_api',
    'http/rest':        'http_api',
    'aws-sdk':          'external_dependency',
    'oci-sdk':          'external_dependency',
    'aws-sdk/oci-sdk':  'external_dependency',
    'json-rpc':         'external_dependency',
    'local-i/o':        'external_dependency',
    'internal':         'default',
}


def transform_edges_from_list(edges: list[dict]) -> list[dict]:
    """Transform graph edges: 'from'→'source', 'to'→'target' for D3.js.

    Also infers a 'type' field from 'protocol' when absent, so D3 edge
    coloring and arrowhead markers work correctly.
    Self-loop edges (source == target) are dropped — they render as
    zero-length invisible lines in SVG.
    """
    transformed = []
    for edge in edges:
        new_edge = {}
        for key, value in edge.items():
            if key == "from":
                new_edge["source"] = value
            elif key == "to":
                new_edge["target"] = value
            else:
                new_edge[key] = value

        # Drop self-loops
        if new_edge.get("source") == new_edge.get("target"):
            continue

        # Infer type from protocol if not already set
        if "type" not in new_edge and "protocol" in new_edge:
            p = new_edge["protocol"].lower()
            new_edge["type"] = _PROTOCOL_TO_TYPE.get(p, "default")

        transformed.append(new_edge)
    return transformed


def load_graph(json_path: Path) -> dict | None:
    """Load a dependency graph JSON file and transform edges."""
    if not json_path.is_file():
        return None

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    # Transform edges based on format
    if "edges" in data:
        if isinstance(data["edges"], dict):
            # Adjacency list format: {"node1": ["target1", "target2"]}
            data["edges"] = transform_edges_from_adjacency_list(data["edges"])
        elif isinstance(data["edges"], list):
            # List of edge objects: [{"from": "a", "to": "b"}]
            data["edges"] = transform_edges_from_list(data["edges"])

    # Handle library graph format with "graph" key (adjacency list)
    if "graph" in data and isinstance(data["graph"], dict):
        data["edges"] = transform_edges_from_adjacency_list(data["graph"])
        data.pop("graph", None)  # Remove redundant "graph" key

    # Convert dict-format nodes to array: {"id1": {...}, "id2": {...}} → [{id: "id1", ...}, ...]
    # Agents may emit nodes as an object keyed by node ID rather than a flat array.
    if "nodes" in data and isinstance(data["nodes"], dict):
        converted = []
        for node_id, node_data in data["nodes"].items():
            if isinstance(node_data, dict):
                node_obj = dict(node_data)
                if "id" not in node_obj:
                    node_obj["id"] = node_id
            else:
                node_obj = {"id": node_id}
            converted.append(node_obj)
        data["nodes"] = converted

    # For array-format nodes: ensure every node has an `id` field.
    # The architecture_documenter emits external service nodes with `name` but no `id`.
    # D3 forceLink resolves edges by calling `.id(d => d.id)`, so missing ids break the graph.
    if "nodes" in data and isinstance(data["nodes"], list):
        for node in data["nodes"]:
            if isinstance(node, dict) and "id" not in node and "name" in node:
                node["id"] = node["name"]

    # Extract nodes from edges if not already present
    if "nodes" not in data or not data["nodes"]:
        if "edges" in data:
            nodes_set = set()
            for edge in data["edges"]:
                nodes_set.add(edge["source"])
                nodes_set.add(edge["target"])
            data["nodes"] = sorted(list(nodes_set))

    # Merge external_systems into nodes as third-party entries so D3 can
    # resolve all edge targets.  They render as dashed red circles.
    if "external_systems" in data:
        existing_ids = {n["id"] if isinstance(n, dict) else n
                        for n in data.get("nodes", [])}
        for sys in data["external_systems"]:
            if sys["id"] not in existing_ids:
                data["nodes"].append({
                    "id": sys["id"],
                    "type": sys.get("type", "external"),
                    "classification": "third-party",
                    "isThirdParty": True,
                    "description": sys.get("description", f"External: {sys['id']}")
                })
        data.pop("external_systems")

    # Remove internal metadata keys not needed in the website
    data.pop("analysis_order", None)
    data.pop("graph_type", None)
    data.pop("metadata", None)

    return data


def load_graphs(dependency_graphs_dir: Path) -> dict:
    """Load all dependency graph files."""
    result = {
        "libraryGraph": {"nodes": [], "edges": []},
        "applicationGraph": {"nodes": [], "edges": []},
    }

    if not dependency_graphs_dir.is_dir():
        print(f"Warning: dependency_graphs directory not found: {dependency_graphs_dir}", file=sys.stderr)
        return result

    lib_graph = load_graph(dependency_graphs_dir / "library_graph.json")
    if lib_graph:
        # Strip external_dependencies from library nodes — those are third-party crate/package
        # names, not internal nodes.  If left in, DependencyGraph.jsx would add 50+ spurious
        # "third-party" circles to the graph for every external package each library uses.
        for node in lib_graph.get("nodes", []):
            if isinstance(node, dict):
                node.pop("external_dependencies", None)
                node.pop("internal_dependencies", None)
        result["libraryGraph"] = lib_graph
        print(f"  Loaded library_graph.json: {len(lib_graph.get('nodes', []))} nodes, {len(lib_graph.get('edges', []))} edges")

    app_graph = load_graph(dependency_graphs_dir / "application_graph.json")
    if app_graph:
        # Classify application graph nodes that lack a classification field.
        # External service nodes (type="external-service") written by the architecture
        # documenter get isThirdParty=True so D3 renders them as dashed red circles.
        # All other nodes default to "application" (blue).
        for node in app_graph.get("nodes", []):
            if not isinstance(node, dict):
                continue
            if node.get("type") == "external-service" or node.get("isThirdParty"):
                node.setdefault("classification", "third-party")
                node["isThirdParty"] = True
            else:
                node.setdefault("classification", "application")
        result["applicationGraph"] = app_graph
        print(f"  Loaded application_graph.json: {len(app_graph.get('nodes', []))} nodes, {len(app_graph.get('edges', []))} edges")

    return result


# ---------------------------------------------------------------------------
# Architecture docs parsing
# ---------------------------------------------------------------------------

def extract_bullet_items(section: str) -> list[str]:
    """Extract bold-prefixed bullet items from a markdown section.

    Matches patterns like:
      - **TypeScript**: Primary language...
      - **Express.js**: Web framework...
    Returns the bold text (e.g. "TypeScript", "Express.js").
    """
    return re.findall(r'^[-*]\s+\*\*([^*]+)\*\*', section, re.MULTILINE)


def extract_project_name(markdown: str) -> str | None:
    """Extract the project name from the H1 heading (e.g. '# Task Manager System - Architecture Documentation')."""
    match = re.search(r'^#\s+(.+?)\s*(?:-\s*Architecture Documentation)?\s*$', markdown, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def load_architecture(architecture_docs_dir: Path) -> dict:
    """Load architecture documentation from architecture.md."""
    result = {
        "projectName": "Unknown Project",
        "overview": "",
        "patterns": [],
        "techStack": [],
        "markdownContent": ""
    }

    arch_file = architecture_docs_dir / "architecture.md"
    if not arch_file.is_file():
        print(f"Warning: architecture.md not found: {arch_file}", file=sys.stderr)
        return result

    with open(arch_file, encoding='utf-8') as f:
        markdown = f.read()

    # Extract project name
    project_name = extract_project_name(markdown)
    if project_name:
        result["projectName"] = project_name

    # Extract overview — try canonical name first, fall back to common alternatives
    overview = (extract_section(markdown, 'System Overview', level=2) or
                extract_section(markdown, 'Executive Summary', level=2) or
                extract_section(markdown, 'Overview', level=2))
    if overview:
        result["overview"] = overview

    # Extract architecture patterns
    patterns_section = extract_section(markdown, 'Architecture Principles', level=2) or \
                      extract_section(markdown, 'Architectural Patterns', level=3)
    if patterns_section:
        result["patterns"] = extract_bullet_items(patterns_section)

    # Extract tech stack
    tech_section = extract_section(markdown, 'Technology Stack', level=2)
    if tech_section:
        result["techStack"] = extract_bullet_items(tech_section)

    result["markdownContent"] = markdown

    print(f"  Loaded architecture.md: {result['projectName']}")
    return result


# ---------------------------------------------------------------------------
# JavaScript generation
# ---------------------------------------------------------------------------

def escape_js_string(s: str) -> str:
    """Escape a string for use in JavaScript template literal."""
    if not s:
        return ""
    # Escape backticks and backslashes
    s = s.replace('\\', '\\\\')
    s = s.replace('`', '\\`')
    s = s.replace('${', '\\${')
    return s


_APPLICATION_KEYWORDS = ('application', 'service', 'worker', 'daemon', 'gateway', 'server',
                         'cmd', 'binary', 'proxy', 'api-server', 'grpc-service')
_LIBRARY_KEYWORDS = ('library', 'go-package', 'rust-crate', 'package', 'module', 'crate')
_EXTERNAL_KEYWORDS = ('external-service', 'external_service', 'third-party', 'third_party')


def _classify(comp_type: str) -> str:
    """Map a raw component type string to 'application' | 'library' | 'external-service' | 'unknown'.

    Uses substring matching so free-form agent descriptions like
    'service - HTTP REST proxy' or 'storage-library' still resolve correctly.
    """
    t = comp_type.lower()
    if any(kw in t for kw in _EXTERNAL_KEYWORDS):
        return 'external-service'
    if any(kw in t for kw in _LIBRARY_KEYWORDS):
        return 'library'
    if any(kw in t for kw in _APPLICATION_KEYWORDS):
        return 'application'
    return 'unknown'


def generate_component_js(component: dict) -> str:
    """Generate JavaScript object literal for a component."""
    name = component['name']
    comp_type = component['type']
    classification = _classify(comp_type)
    description = escape_js_string(component['description'])
    architecture = escape_js_string(component.get('architecture') or '')
    key_components = escape_js_string(component.get('keyComponents') or '')
    system_flows = escape_js_string(component.get('systemFlows') or '')
    data_flows = escape_js_string(component.get('dataFlows') or '')
    external_deps = escape_js_string(component.get('externalDependencies') or '')
    internal_deps = escape_js_string(component.get('internalDependencies') or '')
    api_surface = escape_js_string(component.get('apiSurface') or '')
    markdown = escape_js_string(component.get('markdownContent') or '')

    return f"""  {{
    name: "{name}",
    type: "{comp_type}",
    classification: "{classification}",
    description: `{description}`,
    architecture: `{architecture}`,
    keyComponents: `{key_components}`,
    systemFlows: `{system_flows}`,
    dataFlows: `{data_flows}`,
    externalDependencies: `{external_deps}`,
    internalDependencies: `{internal_deps}`,
    apiSurface: `{api_surface}`,
    markdownContent: `{markdown}`
  }}"""


def generate_graph_js(graph: dict, indent: int = 2) -> str:
    """Generate JavaScript object literal for a dependency graph."""
    ind = ' ' * indent
    nodes_json = json.dumps(graph.get('nodes', []), indent=2)
    edges_json = json.dumps(graph.get('edges', []), indent=2)

    # Include other graph metadata if present
    extra_fields = ""
    for key, value in graph.items():
        if key not in ('nodes', 'edges'):
            value_json = json.dumps(value, indent=2)
            # Indent all lines of value_json
            value_json = '\n'.join(ind + '  ' + line for line in value_json.split('\n'))
            extra_fields += f",\n{ind}{key}: {value_json}"

    return f"""{ind}nodes: {nodes_json},
{ind}edges: {edges_json}{extra_fields}"""


def generate_architecture_js(architecture: dict) -> str:
    """Generate JavaScript object literal for architecture documentation."""
    project_name = architecture.get('projectName', 'Unknown Project')
    overview = escape_js_string(architecture.get('overview') or '')
    patterns = json.dumps(architecture.get('patterns', []))
    tech_stack = json.dumps(architecture.get('techStack', []))
    markdown = escape_js_string(architecture.get('markdownContent') or '')

    return f"""  projectName: "{project_name}",
  overview: `{overview}`,
  patterns: {patterns},
  techStack: {tech_stack},
  markdownContent: `{markdown}`"""


def generate_analysis_data_js(components: list[dict], graphs: dict, architecture: dict) -> str:
    """Generate the complete analysisData.js file content."""
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

    # Derive classification for each component, then build metadata counts
    classified = [_classify(c['type']) for c in components]
    n_apps = classified.count('application')
    n_libs = classified.count('library')

    # Build a concise project description from the first sentence of the overview
    overview = architecture.get('overview') or ''
    description = overview.split('.')[0].strip() if overview else ''

    metadata_js = json.dumps({
        "projectName": architecture.get('projectName', 'Code Analysis'),
        "description": description,
        "totalComponents": len(components),
        "totalApplications": n_apps,
        "totalLibraries": n_libs,
    }, indent=4)

    components_js = ',\n'.join(generate_component_js(c) for c in components)
    library_graph_js = generate_graph_js(graphs['libraryGraph'], indent=4)
    application_graph_js = generate_graph_js(graphs['applicationGraph'], indent=4)
    architecture_js = generate_architecture_js(architecture)

    return f"""// Generated by build_analysis_data.py
// Timestamp: {timestamp}
// DO NOT EDIT - This file is automatically generated

const analysisData = {{
  metadata: {metadata_js},
  components: [
{components_js}
  ],
  libraryGraph: {{
{library_graph_js}
  }},
  applicationGraph: {{
{application_graph_js}
  }},
  architecture: {{
{architecture_js}
  }}
}};

export default analysisData;
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Build analysisData.js from analysis output files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/build_analysis_data.py /tmp/my-project
  python scripts/build_analysis_data.py /tmp/my-project --output /tmp/my-project/website/src/data/analysisData.js
        """
    )
    parser.add_argument('project_dir', type=Path, help='Project directory (e.g., /tmp/my-project)')
    parser.add_argument('--output', type=Path, help='Output file path (default: {project_dir}/website/src/data/analysisData.js)')
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        print(f"Error: Project directory not found: {project_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\nBuilding analysisData.js from {project_dir}\n")

    # Load components
    print("Loading service analyses...")
    components = load_components(project_dir / "service_analyses")

    # Load graphs
    print("\nLoading dependency graphs...")
    graphs = load_graphs(project_dir / "dependency_graphs")

    # Load architecture
    print("\nLoading architecture documentation...")
    architecture = load_architecture(project_dir / "architecture_docs")

    # Generate JavaScript
    print("\nGenerating analysisData.js...")
    js_content = generate_analysis_data_js(components, graphs, architecture)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = project_dir / "website" / "src" / "data" / "analysisData.js"

    # Guard: ensure the website template was copied before writing data into it
    website_src = output_path.parent.parent  # website/src/
    if not (website_src / "App.js").is_file():
        print(
            f"\nError: website template not found at {website_src}\n"
            "The React template must be copied to {project_dir}/website/ before running this script.\n"
            "Run: cp -r templates/website-template/* {project_dir}/website/",
            file=sys.stderr
        )
        sys.exit(1)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)

    print(f"  Written to: {output_path}")
    print(f"  File size: {len(js_content):,} bytes")
    print("\n✓ Build complete!\n")


if __name__ == '__main__':
    main()
