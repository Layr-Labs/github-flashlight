"""
Tool implementations for querying service knowledge artifacts.
"""

import json
import os
import subprocess
from pathlib import Path

ARTIFACTS_DIR = Path(
    os.environ.get(
        "ARTIFACTS_DIR",
        Path(__file__).resolve().parent.parent / "service-knowledge-artifacts",
    )
)

VALID_MERMAID_TYPES = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "gitgraph",
    "mindmap",
    "timeline",
)


def list_services() -> str:
    """List all available services and their artifact structure."""
    services = {}
    for d in sorted(ARTIFACTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        info = {"artifacts": []}
        for item in sorted(d.iterdir()):
            if item.name.startswith(".") or item.name == "website":
                continue
            if item.is_dir():
                files = [
                    f.name
                    for f in sorted(item.iterdir())
                    if f.suffix in (".md", ".json")
                ]
                if files:
                    info["artifacts"].append({"directory": item.name, "files": files})
            elif item.suffix in (".md", ".json"):
                info["artifacts"].append({"file": item.name})
        services[d.name] = info
    return json.dumps(services, indent=2)


def get_architecture(service: str, doc_type: str = "architecture") -> str:
    """Read architecture documentation for a service."""
    service_dir = ARTIFACTS_DIR / service
    if not service_dir.is_dir():
        available = [
            d.name
            for d in ARTIFACTS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        return f"Error: Service '{service}' not found. Available: {available}"

    arch_dir = service_dir / "architecture_docs"
    if arch_dir.is_dir():
        candidates = [
            arch_dir / f"{doc_type}.md",
            arch_dir / "architecture.md",
            arch_dir / "quick_reference.md",
            arch_dir / f"{service}_architecture.md",
            arch_dir / "ANALYSIS_SUMMARY.md",
        ]
        for c in candidates:
            if c.exists():
                return c.read_text()
        md_files = list(arch_dir.glob("*.md"))
        if md_files:
            return md_files[0].read_text()

    flat = service_dir / "architecture.md"
    if flat.exists():
        return flat.read_text()

    return (
        f"Error: No architecture docs found for '{service}'. "
        f"Contents: {[f.name for f in service_dir.iterdir()]}"
    )


def get_service_analysis(service: str, component: str) -> str:
    """Read a specific component's analysis."""
    service_dir = ARTIFACTS_DIR / service
    if not service_dir.is_dir():
        return f"Error: Service '{service}' not found."

    analyses_dir = service_dir / "service_analyses"
    if not analyses_dir.is_dir():
        return (
            f"Error: No service_analyses/ for '{service}'. "
            f"Contents: {[f.name for f in service_dir.iterdir()]}"
        )

    exact = analyses_dir / f"{component}.md"
    if exact.exists():
        return exact.read_text()

    available = sorted(analyses_dir.glob("*.md"))
    for f in available:
        if component.lower() in f.stem.lower():
            return f.read_text()

    return (
        f"Error: Component '{component}' not found. "
        f"Available: {[f.stem for f in available]}"
    )


def get_dependency_graph(service: str, graph_type: str = "library") -> str:
    """Read dependency graph for a service."""
    service_dir = ARTIFACTS_DIR / service
    if not service_dir.is_dir():
        return f"Error: Service '{service}' not found."

    graphs_dir = service_dir / "dependency_graphs"
    if not graphs_dir.is_dir():
        return f"Error: No dependency_graphs/ for '{service}'."

    candidates = [
        graphs_dir / f"{graph_type}_graph.json",
        graphs_dir / f"{graph_type}.json",
        graphs_dir / "dependencies.json",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text()

    json_files = list(graphs_dir.glob("*.json"))
    if json_files:
        return json_files[0].read_text()

    md_files = list(graphs_dir.glob("*.md"))
    if md_files:
        return md_files[0].read_text()

    return f"Error: No graph found. Contents: {[f.name for f in graphs_dir.iterdir()]}"


def list_components(service: str) -> str:
    """List all analyzed components for a service."""
    service_dir = ARTIFACTS_DIR / service
    if not service_dir.is_dir():
        return f"Error: Service '{service}' not found."

    result = {"service": service, "components": []}

    analyses_dir = service_dir / "service_analyses"
    if analyses_dir.is_dir():
        result["components"] = [f.stem for f in sorted(analyses_dir.glob("*.md"))]

    discovery_dir = service_dir / "service_discovery"
    if discovery_dir.is_dir():
        for jf in discovery_dir.glob("*.json"):
            try:
                result[jf.stem] = json.loads(jf.read_text())
            except (json.JSONDecodeError, OSError):
                pass

    for catalog in service_dir.glob("*_catalog.json"):
        try:
            result[catalog.stem] = json.loads(catalog.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    return json.dumps(result, indent=2)


def search_artifacts(query: str, service: str = None) -> str:
    """Keyword search across artifacts. Returns matching file paths."""
    search_dir = ARTIFACTS_DIR / service if service else ARTIFACTS_DIR
    if not search_dir.is_dir():
        return f"Error: Directory not found: {search_dir}"

    try:
        proc = subprocess.run(
            [
                "grep", "-r", "-i", "-l",
                "--include=*.md", "--include=*.json",
                query, str(search_dir),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            files = [
                str(Path(f).relative_to(ARTIFACTS_DIR))
                for f in proc.stdout.strip().split("\n")
                if f
            ]
            return json.dumps({"query": query, "matching_files": files}, indent=2)
        return json.dumps({"query": query, "matching_files": []})
    except subprocess.TimeoutExpired:
        return "Error: Search timed out."


def search_artifacts_with_context(query: str, service: str = None) -> str:
    """Keyword search with surrounding context lines."""
    search_dir = ARTIFACTS_DIR / service if service else ARTIFACTS_DIR
    if not search_dir.is_dir():
        return f"Error: Directory not found: {search_dir}"

    try:
        proc = subprocess.run(
            [
                "grep", "-r", "-i", "-n", "-C", "3",
                "--include=*.md", "--include=*.json",
                query, str(search_dir),
            ],
            capture_output=True, text=True, timeout=10,
        )
        output = proc.stdout.strip()
        if len(output) > 12000:
            output = output[:12000] + "\n... (truncated)"
        return output if output else f"No matches found for '{query}'."
    except subprocess.TimeoutExpired:
        return "Error: Search timed out."


def sketch_knowledge_graph(mermaid_code: str, title: str = "", reasoning: str = "") -> str:
    """Validate and echo back a Mermaid diagram for knowledge-graph reasoning."""
    first_line = mermaid_code.strip().split("\n")[0].strip()
    first_keyword = first_line.split()[0] if first_line else ""
    # Strip version suffix like "stateDiagram-v2"
    base_keyword = first_keyword.split("-")[0]

    if base_keyword not in VALID_MERMAID_TYPES:
        return (
            f"Error: Mermaid code must start with a valid diagram type "
            f"({', '.join(VALID_MERMAID_TYPES)}). Got: '{first_keyword}'"
        )

    header = f"**{title}**\n" if title else ""
    return (
        f"{header}```mermaid\n{mermaid_code.strip()}\n```\n\n"
        "Diagram rendered. Examine the relationships above, verify they are "
        "correct, and continue your analysis."
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    "list_services": lambda p: list_services(),
    "get_architecture": lambda p: get_architecture(
        p["service"], p.get("doc_type", "architecture")
    ),
    "get_service_analysis": lambda p: get_service_analysis(
        p["service"], p["component"]
    ),
    "get_dependency_graph": lambda p: get_dependency_graph(
        p["service"], p.get("graph_type", "library")
    ),
    "list_components": lambda p: list_components(p["service"]),
    "search_artifacts": lambda p: search_artifacts(
        p["query"], p.get("service")
    ),
    "search_artifacts_with_context": lambda p: search_artifacts_with_context(
        p["query"], p.get("service")
    ),
    "sketch_knowledge_graph": lambda p: sketch_knowledge_graph(
        p["mermaid_code"], p.get("title", ""), p.get("reasoning", "")
    ),
}


def execute_tool(name: str, params: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Error: Unknown tool '{name}'"
    return handler(params)


# ---------------------------------------------------------------------------
# Anthropic tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "list_services",
        "description": (
            "List all available services and their artifact structure. "
            "Call this first to understand what data is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_architecture",
        "description": (
            "Read architecture documentation for a service. Returns system design, "
            "component interactions, data flows, and deployment patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name (eigenda, agentkit, symphony, nemoclaw)",
                },
                "doc_type": {
                    "type": "string",
                    "description": "Document type. Defaults to 'architecture'.",
                    "enum": ["architecture", "quick_reference"],
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "get_service_analysis",
        "description": (
            "Read the detailed analysis for a specific component within a service. "
            "Contains architecture, key components, data flows, API reference, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name",
                },
                "component": {
                    "type": "string",
                    "description": (
                        "Component name (e.g. 'disperser', 'core', 'agentkit-cli'). "
                        "Use list_components to see available names."
                    ),
                },
            },
            "required": ["service", "component"],
        },
    },
    {
        "name": "get_dependency_graph",
        "description": (
            "Read the dependency graph (JSON) for a service. Nodes are components, "
            "edges are dependencies. Use 'library' for internal deps, 'application' "
            "for app-level deps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name",
                },
                "graph_type": {
                    "type": "string",
                    "description": "Graph type. Defaults to 'library'.",
                    "enum": ["library", "application"],
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "list_components",
        "description": (
            "List all analyzed components for a service, including metadata "
            "from service discovery."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name",
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "search_artifacts",
        "description": (
            "Search across all artifacts for a keyword or phrase. "
            "Returns matching file paths. Optionally scope to one service."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term or phrase",
                },
                "service": {
                    "type": "string",
                    "description": "Optional: limit search to a specific service",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_artifacts_with_context",
        "description": (
            "Search across artifacts and return matching lines with surrounding "
            "context. Use when you need to see actual content around matches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term or phrase",
                },
                "service": {
                    "type": "string",
                    "description": "Optional: limit search to a specific service",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "sketch_knowledge_graph",
        "description": (
            "Sketch a Mermaid knowledge graph as an intermediate reasoning step. "
            "Call this when you need to visually reason about complex relationships "
            "before producing a final answer. The diagram is rendered live for the "
            "user and echoed back so you can reflect on it.\n\n"
            "Use `graph TD` or `graph LR` for dependency/component maps. "
            "Use `sequenceDiagram` for interaction and data flows between components. "
            "Keep diagrams focused — prefer multiple small diagrams over one giant one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mermaid_code": {
                    "type": "string",
                    "description": (
                        "Valid Mermaid diagram code (must start with a diagram "
                        "type like graph TD, sequenceDiagram, etc.)"
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Short title for the diagram",
                },
                "reasoning": {
                    "type": "string",
                    "description": (
                        "Brief explanation of what you are trying to reason "
                        "about with this diagram"
                    ),
                },
            },
            "required": ["mermaid_code"],
        },
    },
]
