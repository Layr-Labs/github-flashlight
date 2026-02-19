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
    Extract a section from markdown by heading.

    Finds content from the given heading until the next heading at the same
    or higher level. Returns None if the section is not found.
    """
    prefix = "#" * level
    # Match the heading line (e.g. "## System Flows")
    pattern = rf'^{prefix}\s+{re.escape(heading)}\s*$'
    match = re.search(pattern, markdown, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None

    start = match.end()

    # Find the next heading at same or higher level
    next_heading = re.search(
        rf'^#{{{1},{level}}}\s+',
        markdown[start:],
        re.MULTILINE,
    )
    if next_heading:
        end = start + next_heading.start()
    else:
        end = len(markdown)

    content = markdown[start:end].strip()
    return content if content else None


def get_header(markdown: str) -> str:
    """Return the markdown content before the first ## heading."""
    match = re.search(r'^##\s+', markdown, re.MULTILINE)
    return markdown[:match.start()] if match else markdown


def extract_metadata_field(markdown: str, field: str) -> str | None:
    """Extract a **Field**: Value line from the markdown header area (before first ## heading)."""
    header = get_header(markdown)
    pattern = rf'\*\*{re.escape(field)}\*\*:\s*(.+)'
    match = re.search(pattern, header)
    return match.group(1).strip() if match else None


def extract_description(markdown: str) -> str:
    """
    Extract a brief description from the Overview or Architecture section.
    Takes the first non-empty paragraph.
    """
    for section_name in ("Overview", "Architecture"):
        section = extract_section(markdown, section_name)
        if section:
            # Strip subsection headings to get clean paragraph text
            clean = re.sub(r'^#{1,6}\s+.*$', '', section, flags=re.MULTILINE)
            paragraphs = re.split(r'\n\s*\n', clean)
            for para in paragraphs:
                text = para.strip()
                # Skip empty, horizontal rules, code blocks
                if text and text != '---' and not text.startswith('```'):
                    # Truncate to first 2-3 sentences for brevity
                    sentences = re.split(r'(?<=[.!?])\s+', text)
                    return ' '.join(sentences[:3])
    return ""


# ---------------------------------------------------------------------------
# Component parsing (service_analyses/*.md)
# ---------------------------------------------------------------------------

def parse_component(md_path: Path) -> dict:
    """Parse a single component markdown file into a component dict."""
    markdown = md_path.read_text(encoding='utf-8')
    name = md_path.stem

    # Extract metadata
    classification = extract_metadata_field(markdown, "Classification")
    if not classification:
        # Try alternative field names
        lib_type = extract_metadata_field(markdown, "Library Type")
        app_type = extract_metadata_field(markdown, "Application Type")
        if lib_type:
            classification = "library"
        elif app_type:
            classification = "application"
        else:
            classification = "unknown"
    classification = classification.lower() if classification else "unknown"
    # Normalize: "service" → "application"
    if classification in ("service",):
        classification = "application"

    comp_type = (
        extract_metadata_field(markdown, "Type")
        or extract_metadata_field(markdown, "Library Type")
        or extract_metadata_field(markdown, "Application Type")
        or "unknown"
    )

    description = extract_description(markdown)

    # Extract dedicated sections
    system_flows = extract_section(markdown, "System Flows")
    data_flows = extract_section(markdown, "Data Flows")
    api_surface = extract_section(markdown, "API Surface")

    # Dependencies — try multiple heading variants
    external_deps = (
        extract_section(markdown, "External Dependencies", level=3)
        or extract_section(markdown, "External Applications", level=3)
    )
    internal_deps = (
        extract_section(markdown, "Internal Dependencies", level=3)
        or extract_section(markdown, "Internal Applications", level=3)
    )

    component = {
        "name": name,
        "classification": classification,
        "type": comp_type,
        "description": description,
    }

    # Only include non-None optional fields
    if system_flows:
        component["systemFlows"] = system_flows
    if data_flows:
        component["dataFlows"] = data_flows
    if external_deps:
        component["externalDependencies"] = external_deps
    if internal_deps:
        component["internalDependencies"] = internal_deps
    if api_surface:
        component["apiSurface"] = api_surface

    component["markdownContent"] = markdown

    return component


def load_components(service_analyses_dir: Path) -> list[dict]:
    """Load all component markdown files from service_analyses/."""
    components = []
    if not service_analyses_dir.is_dir():
        print(f"Warning: service_analyses directory not found: {service_analyses_dir}", file=sys.stderr)
        return components

    # Collect all .md files, skip subdirectories with duplicate analyses
    md_files = sorted(service_analyses_dir.glob("*.md"))
    print(f"  Found {len(md_files)} service analysis files")

    for md_path in md_files:
        print(f"    Processing: {md_path.name}")
        component = parse_component(md_path)
        components.append(component)

    # Sort by name for deterministic output
    components.sort(key=lambda c: c["name"])
    return components


# ---------------------------------------------------------------------------
# Graph parsing (dependency_graphs/*.json)
# ---------------------------------------------------------------------------

def transform_edges(edges: list[dict]) -> list[dict]:
    """Transform graph edges: 'from'→'source', 'to'→'target' for D3.js."""
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
        transformed.append(new_edge)
    return transformed


def load_graph(json_path: Path) -> dict | None:
    """Load a dependency graph JSON file and transform edges."""
    if not json_path.is_file():
        return None

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    # Transform edges
    if "edges" in data:
        data["edges"] = transform_edges(data["edges"])

    # Remove analysis_order (internal detail, not needed in website)
    data.pop("analysis_order", None)
    data.pop("graph_type", None)

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
        result["libraryGraph"] = lib_graph
        print(f"  Loaded library_graph.json: {len(lib_graph.get('nodes', []))} nodes, {len(lib_graph.get('edges', []))} edges")

    app_graph = load_graph(dependency_graphs_dir / "application_graph.json")
    if app_graph:
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
    match = re.match(r'^#\s+(.+?)(?:\s*[-–—]\s*Architecture.*)?$', markdown, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def load_architecture(architecture_docs_dir: Path) -> dict:
    """Load architecture documentation."""
    result = {}

    arch_path = architecture_docs_dir / "architecture.md"
    if not arch_path.is_file():
        print(f"Warning: architecture.md not found: {arch_path}", file=sys.stderr)
        return result

    markdown = arch_path.read_text(encoding='utf-8')
    print(f"  Loaded architecture.md ({len(markdown)} bytes)")

    # Extract overview from first major section
    overview_section = extract_section(markdown, "1. System Overview") or extract_section(markdown, "System Overview")
    if overview_section:
        # Strip subsection headings (### lines) to get clean paragraph text
        clean = re.sub(r'^#{1,6}\s+.*$', '', overview_section, flags=re.MULTILINE)
        paragraphs = re.split(r'\n\s*\n', clean)
        overview_parts = []
        for para in paragraphs:
            text = para.strip()
            # Skip empty, horizontal rules, code blocks, bullet-only blocks
            if text and text != '---' and not text.startswith('```'):
                overview_parts.append(text)
            if len(overview_parts) >= 3:
                break
        result["overview"] = '\n\n'.join(overview_parts)

    # Extract patterns
    patterns_section = extract_section(markdown, "Architectural Patterns") or extract_section(markdown, "4. Architectural Patterns")
    if patterns_section:
        # Extract bullet points with bold labels
        patterns = re.findall(r'^[-*]\s+\*\*(.+?)\*\*(?:\s*[-:]?\s*(.+))?$', patterns_section, re.MULTILINE)
        if patterns:
            result["patterns"] = [f"{name} - {desc}".rstrip(' -') if desc else name for name, desc in patterns]

    # Extract tech stack from markdown subsections
    tech_section = extract_section(markdown, "Technology Stack") or extract_section(markdown, "5. Technology Stack")
    if tech_section:
        tech_stack = {}

        # Try subsection-based extraction (### 5.1 Languages, ### 5.2 Frameworks)
        lang_section = extract_section(tech_section, "Languages", level=3) or extract_section(tech_section, "5.1 Languages", level=3)
        if lang_section:
            tech_stack["languages"] = extract_bullet_items(lang_section) or []

        fw_section = (
            extract_section(tech_section, "Frameworks & Libraries", level=3)
            or extract_section(tech_section, "5.2 Frameworks & Libraries", level=3)
            or extract_section(tech_section, "Frameworks", level=3)
        )
        if fw_section:
            tech_stack["frameworks"] = extract_bullet_items(fw_section) or []

        db_section = extract_section(tech_section, "Databases", level=3) or extract_section(tech_section, "Data Storage", level=3)
        if db_section:
            tech_stack["databases"] = extract_bullet_items(db_section) or []

        # Fallback: try single-line "Key: value, value" format
        if not tech_stack.get("languages"):
            lang_match = re.findall(r'(?:language|runtime).*?:\s*(.+)', tech_section, re.IGNORECASE)
            if lang_match:
                tech_stack["languages"] = [l.strip() for l in lang_match[0].split(',')]

        if not tech_stack.get("frameworks"):
            fw_match = re.findall(r'framework.*?:\s*(.+)', tech_section, re.IGNORECASE)
            if fw_match:
                tech_stack["frameworks"] = [f.strip() for f in fw_match[0].split(',')]

        # Ensure all expected keys exist with defaults
        tech_stack.setdefault("languages", [])
        tech_stack.setdefault("frameworks", [])
        tech_stack.setdefault("databases", [])

        result["techStack"] = tech_stack

    # Ensure techStack exists even if section wasn't found
    result.setdefault("techStack", {"languages": [], "frameworks": [], "databases": []})
    # Ensure patterns exists
    result.setdefault("patterns", [])

    result["markdownContent"] = markdown

    return result


# ---------------------------------------------------------------------------
# JavaScript output generation
# ---------------------------------------------------------------------------

def escape_js_template_literal(s: str) -> str:
    """Escape a string for embedding in a JavaScript template literal (backticks)."""
    s = s.replace('\\', '\\\\')  # Escape backslashes first
    s = s.replace('`', '\\`')    # Escape backticks
    s = s.replace('${', '\\${')  # Escape template interpolation
    return s


def format_js_value(value, indent: int = 4) -> str:
    """
    Format a Python value as a JavaScript literal.

    Strings use template literals (backticks) to preserve multiline content.
    Other types use JSON serialization.
    """
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # For multiline strings (markdown), use template literals
        if '\n' in value or '`' in value or len(value) > 120:
            return f'`{escape_js_template_literal(value)}`'
        # For short strings, use double quotes
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        if not value:
            return '[]'
        items = []
        for item in value:
            items.append(format_js_value(item, indent + 2))
        inner_indent = ' ' * (indent + 2)
        items_str = ',\n'.join(f'{inner_indent}{item}' for item in items)
        outer_indent = ' ' * indent
        return f'[\n{items_str}\n{outer_indent}]'
    if isinstance(value, dict):
        if not value:
            return '{}'
        items = []
        for key, val in value.items():
            js_key = key if re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$', key) else f'"{key}"'
            items.append(f'{js_key}: {format_js_value(val, indent + 2)}')
        inner_indent = ' ' * (indent + 2)
        items_str = ',\n'.join(f'{inner_indent}{item}' for item in items)
        outer_indent = ' ' * indent
        return f'{{\n{items_str}\n{outer_indent}}}'
    # Fallback
    return json.dumps(value)


def generate_analysis_data_js(components: list[dict], graphs: dict,
                               architecture: dict, metadata: dict) -> str:
    """Generate the full analysisData.js file content."""
    data = {
        "components": components,
        "libraryGraph": graphs["libraryGraph"],
        "applicationGraph": graphs["applicationGraph"],
        "architecture": architecture,
        "metadata": metadata,
    }

    lines = [
        "// Auto-generated by build_analysis_data.py - DO NOT EDIT MANUALLY",
        f"// Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"const analysisData = {format_js_value(data, 0)};",
        "",
        "export default analysisData;",
        "",
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build analysisData.js from analysis output files"
    )
    parser.add_argument(
        "project_dir",
        help="Path to project output directory (e.g., /tmp/my-project)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output path for analysisData.js (default: <project_dir>/website/src/data/analysisData.js)"
    )

    args = parser.parse_args()
    project_dir = Path(args.project_dir)

    if not project_dir.is_dir():
        print(f"Error: Project directory not found: {project_dir}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else project_dir / "website" / "src" / "data" / "analysisData.js"

    print(f"Building analysisData.js from {project_dir}")
    print()

    # 1. Load service analyses
    print("Loading service analyses...")
    components = load_components(project_dir / "service_analyses")
    n_apps = sum(1 for c in components if c["classification"] == "application")
    n_libs = sum(1 for c in components if c["classification"] == "library")
    print(f"  Total: {len(components)} components ({n_apps} applications, {n_libs} libraries)")
    print()

    # 2. Load dependency graphs
    print("Loading dependency graphs...")
    graphs = load_graphs(project_dir / "dependency_graphs")
    print()

    # 3. Load architecture docs
    print("Loading architecture documentation...")
    architecture = load_architecture(project_dir / "architecture_docs")
    print()

    # 4. Build metadata
    # Extract project name from architecture doc heading
    arch_md = architecture.get("markdownContent", "")
    project_name = extract_project_name(arch_md) if arch_md else None
    # Fallback: derive from project directory name
    if not project_name:
        project_name = project_dir.name.replace('-', ' ').replace('_', ' ').title()

    # Extract description from overview
    description = architecture.get("overview", "").split('\n')[0] if architecture.get("overview") else ""

    metadata = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "projectName": project_name,
        "description": description,
        "totalComponents": len(components),
        "totalApplications": n_apps,
        "totalLibraries": n_libs,
    }

    # 5. Generate output
    print("Generating analysisData.js...")
    js_content = generate_analysis_data_js(components, graphs, architecture, metadata)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(js_content, encoding='utf-8')

    print(f"  Wrote {output_path} ({len(js_content)} bytes)")
    print()
    print(f"Done. {len(components)} components loaded ({n_apps} applications, {n_libs} libraries)")


if __name__ == "__main__":
    main()
