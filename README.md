# GitHub Flashlight

A sophisticated multi-agent processing pipeline using the Claude Agent SDK that performs dependency-aware codebase analysis and visualization through multi-agent composition.

## Features

- **Automatic Service Discovery**: Identifies services in Rust (Cargo.toml), Go (go.mod), Node.js (package.json), and Python (pyproject.toml) codebases
- **Dependency Graph Analysis**: Builds and visualizes service dependency relationships
- **Two-Phase Analysis**:
  - Phase 1: Analyzes foundation services with no dependencies
  - Phase 2: Analyzes remaining services in dependency order with upstream context
- **Context-Aware**: Code analyzers receive analyses of direct dependencies to understand integration patterns
- **Comprehensive Documentation**: Generates system-wide architecture documentation with patterns, flows, and recommendations
- **Interactive Website**: Automatically generates a React SPA with D3.js interactive dependency graph visualization
- **Multi-Agent Orchestration**: Uses specialized agents for discovery, analysis, documentation synthesis, and website generation

## Component Classification

GitHub Flashlight automatically classifies components as applications or libraries to help distinguish between executable services and reusable packages:

### 🔷 Binaries (Services/Applications)
Executable applications that run as independent services:
- **Rust**: Crates with `[[bin]]` section or `src/main.rs`
- **Python**: Packages with `[project.scripts]` or `__main__.py`
- **Node.js**: Packages with `"bin"` field or server frameworks

Displayed as **rectangles (■)** in the dependency graph.

### 🟢 Libraries (Packages)
Reusable code libraries consumed by services:
- **Rust**: Crates with only `[lib]` section
- **Python**: Packages without entry points
- **Node.js**: Packages without `"bin"` field

Displayed as **circles (●)** in the dependency graph.

### Detection Logic
1. **Manifest analysis**: Checks Cargo.toml, package.json, pyproject.toml for binary indicators
2. **File structure**: Looks for `main.rs` vs `lib.rs`, `__main__.py` presence
3. **Naming patterns**: Keywords like "server", "api" → binary; "core", "utils" → library
4. **Default**: Classifies as "library" when uncertain

### Website Visualization
The generated website offers three view modes:
- **All Components**: Full dependency graph with visual distinction between services and libraries
- **Services Only**: Focus on service architecture and their direct dependencies
- **Libraries Only**: Focus on reusable components and their relationships

## Architecture

The pipeline uses four specialized roles:

1. **Primary Leader** (orchestrator)
   - Discovers services by scanning for manifest files
   - Builds dependency graph and determines analysis order
   - Spawns code analyzer agents with appropriate context
   - Spawns architecture documenter for final synthesis
   - Spawns website generator for interactive visualization

2. **Code Analyzer** (multiple instances)
   - Deep analysis of individual services
   - Examines architecture, components, data flows, dependencies, API surface
   - Receives context from direct dependencies
   - Outputs JSON and Markdown reports

3. **Architecture Documenter** (single instance)
   - Synthesizes all service analyses
   - Identifies system-wide patterns
   - Creates comprehensive architecture documentation

4. **Website Generator** (single instance)
   - Generates interactive React SPA with D3.js
   - Creates searchable service catalog
   - Implements interactive dependency graph visualization
   - Includes service detail pages and architecture overview

## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Set up API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## Usage

```bash
# Run the pipeline
python -m github_flashlight.agent

# Or use the installed command
github-flashlight
```

Then provide a path to analyze:
```
You: Analyze the codebase at /path/to/repo
```

The pipeline will:
1. Scan for services (Cargo.toml, go.mod, package.json, pyproject.toml files)
2. Build dependency graph
3. Analyze services in two phases:
   - Phase 1: Services with no dependencies (parallel)
   - Phase 2: Services with dependencies (in order, with context)
4. Generate architecture documentation
5. Create interactive website with D3.js dependency graph

To view the website:
```bash
cd files/website
npm install
npm start
# Opens at http://localhost:3000
```

## Output Structure

```
files/
├── service_discovery/
│   ├── services.json              # Discovered services metadata
│   └── discovery_log.md           # Human-readable discovery log
├── dependency_graphs/
│   ├── dependency_graph.json      # Machine-readable graph
│   └── dependency_graph.md        # Visualization
├── service_analyses/
│   ├── {service1}.json            # Structured analysis
│   ├── {service1}.md              # Human-readable report
│   └── ... (one pair per service)
├── architecture_docs/
│   ├── architecture.md            # Comprehensive documentation
│   └── quick_reference.md         # One-page summary
└── website/                        # Interactive React SPA
    ├── public/
    │   └── index.html
    ├── src/
    │   ├── components/
    │   │   ├── DependencyGraph.jsx      # D3.js interactive graph
    │   │   ├── ServiceList.jsx          # Service catalog
    │   │   ├── ServiceDetail.jsx        # Service details
    │   │   └── ...
    │   ├── data/
    │   │   └── analysisData.js          # Consolidated data
    │   ├── App.js
    │   └── index.js
    ├── package.json
    └── README.md

logs/
└── session_YYYYMMDD_HHMMSS/
    ├── transcript.txt             # Conversation log
    └── tool_calls.jsonl           # Structured tool usage
```

## Example Analysis Flow

For a Rust codebase with this structure:
```
repo/
├── common-utils/          (no dependencies)
├── config-loader/         (no dependencies)
├── database-layer/        (depends on common-utils)
├── auth-service/          (depends on database-layer)
└── api-gateway/           (depends on auth-service, database-layer)
```

The agent will:
1. **Phase 1**: Analyze `common-utils` and `config-loader` in parallel
2. **Phase 2**:
   - Analyze `database-layer` with context from `common-utils`
   - Analyze `auth-service` with context from `database-layer` only (not common-utils)
   - Analyze `api-gateway` with context from `auth-service` and `database-layer`
3. **Synthesis**: Generate comprehensive architecture documentation
4. **Visualization**: Create interactive React website with D3.js dependency graph

## Key Design Principles

- **Direct Dependencies Only**: Analyzers receive context only from direct dependencies, not transitive ones
- **Dependency Order**: Services are analyzed in topological order to ensure dependencies are analyzed first
- **Parallel Execution**: Services at the same dependency level are analyzed in parallel
- **Structured Output**: Both machine-readable (JSON) and human-readable (Markdown) outputs

## Supported Languages

- **Rust**: Full support (Cargo.toml discovery, dependency extraction)
- **Go**: Full support (go.mod discovery, dependency extraction)
- **Node.js**: Partial support (package.json discovery)
- **Python**: Partial support (pyproject.toml discovery)

## Requirements

- Python 3.10+
- Claude API key
- Access to the codebase to analyze

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (when available)
pytest
```

## How It Works

The primary leader orchestrates a sophisticated multi-phase workflow:

### Discovery Phase
- Uses Glob to find manifest files (Cargo.toml, go.mod, package.json, pyproject.toml)
- Reads each manifest to extract service metadata
- Identifies internal dependencies (path-based in manifests)
- Saves service inventory to JSON

### Graph Building Phase
- Constructs directed dependency graph
- Calculates analysis order using two-phase approach:
  - Phase 1: Services with in-degree 0 (no dependencies)
  - Phase 2: Topological sort of remaining services
- Visualizes graph in both JSON and Markdown

### Analysis Phase
- **Phase 1**: Spawns code-analyzer for each no-dependency service (parallel)
- **Phase 2**: For each remaining service:
  - Waits for its direct dependencies to complete
  - Loads direct dependency analyses
  - Builds context summary (architecture, APIs, components)
  - Spawns code-analyzer with context
  - Ensures proper ordering while maximizing parallelism

### Synthesis Phase
- Spawns architecture-documenter after all analyses complete
- Reads all service analyses and dependency graph
- Identifies system-wide patterns and architectural approaches
- Generates comprehensive documentation with:
  - System overview
  - Service catalog
  - Dependency visualization
  - Architectural patterns
  - Technology stack
  - Major data flows
  - Development guide
  - Recommendations

### Website Generation Phase
- Spawns website-generator after documentation is complete
- Reads all service analyses, dependency graphs, and architecture docs
- Generates complete React SPA with:
  - D3.js interactive force-directed dependency graph
  - Searchable service catalog
  - Service detail pages with full analysis
  - Architecture overview dashboard
  - Zoom, pan, and click-to-navigate functionality
  - Color-coded nodes by phase (Phase 1/2)
- Outputs production-ready application with package.json and build instructions

## Interactive Website Features

The generated React SPA provides an intuitive interface for exploring the codebase analysis:

### Dependency Graph Visualization
- **D3.js force-directed layout**: Services are nodes, dependencies are directed edges
- **Interactive exploration**: Click nodes to navigate to service details, drag to reposition
- **Zoom and pan**: Explore large codebases with smooth zoom/pan controls
- **Color-coded**: Phase 1 (foundation) services in blue, Phase 2 (dependent) services in green
- **Hover tooltips**: See service info on hover
- **Highlight paths**: Visual emphasis on dependency chains

### Service Catalog
- **Search and filter**: Quickly find services by name, type, or technology
- **Grid/list view**: Browse all services with key metadata
- **Dependency badges**: See at-a-glance dependency counts
- **Quick navigation**: Click to jump to service details or graph view

### Service Detail Pages
- **Complete analysis**: Architecture, key components, data flows
- **Dependencies**: Links to direct dependencies and dependents
- **API surface**: Exported functions, endpoints, types
- **Code examples**: Syntax-highlighted snippets
- **Technology stack**: Languages and frameworks used

### Architecture Overview
- **System summary**: High-level architecture description
- **Quick stats**: Service counts, languages, patterns
- **Technology inventory**: Complete tech stack breakdown

### Technical Details
- **Framework**: React 18 with React Router for SPA navigation
- **Visualization**: D3.js v7 for interactive graphs
- **Build system**: Create React App for zero-config setup
- **Deployment**: Static build output for easy hosting

## Contributing

This project showcases the Claude Agent SDK's multi-agent composition capabilities. Feel free to extend it with:
- Additional language support (Java, C#, etc.)
- Enhanced metrics collection (LOC, complexity, test coverage)
- Incremental analysis for large repositories
- Custom analysis plugins
- Additional visualization options

## License

See parent repository for license information.
