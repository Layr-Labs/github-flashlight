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
- **Multi-Agent Orchestration**: Uses specialized agents for discovery, analysis, and documentation synthesis

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

## Architecture

The pipeline uses four specialized roles:

1. **Primary Leader** (orchestrator)
   - Discovers services by scanning for manifest files
   - Builds dependency graph and determines analysis order
   - Spawns code analyzer agents with appropriate context
   - Spawns external service analyzers for runtime integrations
   - Spawns architecture documenter for final synthesis

2. **Code Analyzer** (multiple instances)
   - Deep analysis of individual services
   - Examines architecture, components, data flows, dependencies, API surface
   - Documents all third-party dependencies with version, category, and purpose
   - Receives context from direct dependencies
   - Outputs Markdown reports

3. **External Service Analyzer** (per-service instances)
   - Deep-dives into how external services (databases, cloud platforms, APIs) are integrated
   - Documents client libraries, authentication, API surface, and configuration
   - Produces integration analysis files for architecture synthesis

4. **Architecture Documenter** (single instance)
   - Synthesizes all service analyses
   - Aggregates external dependencies into a complete technology inventory
   - Identifies system-wide patterns
   - Creates comprehensive architecture documentation

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

### Verbose Logging

Enable detailed SDK and API interaction logging:

```bash
# Verbose mode - Shows API calls, agent spawning, and tool usage
AGENT_VERBOSE=true python -m github_flashlight.agent

# Debug mode - Full trace logging including API request/response details
AGENT_DEBUG=true python -m github_flashlight.agent
```

When enabled, you'll see real-time information about:
- 📤 API requests to Claude
- 📥 API responses
- 🚀 Subagent spawning and lifecycle
- 🔧 Tool calls with parameters
- ✅ Tool results and success/failure status
- 📝 Agent context and model information

This is useful for:
- Understanding what the agents are doing in real-time
- Debugging analysis pipeline issues
- Monitoring API usage and performance
- Learning how the multi-agent system orchestrates tasks

### Live Observability Monitor

For real-time visual monitoring of agent execution with interactive profiling:

```bash
./observability/live_monitor.sh
```

This launches a web-based profiler that automatically tracks your current session, displaying tool calls, timing metrics, and agent interactions in real-time. The visualization updates live as your agents work, providing an interactive dashboard for monitoring pipeline execution and performance analysis.

The pipeline will:
1. Scan for services (Cargo.toml, go.mod, package.json, pyproject.toml files)
2. Build dependency graph
3. Analyze services in two phases:
   - Phase 1: Services with no dependencies (parallel)
   - Phase 2: Services with dependencies (in order, with context)
4. Generate architecture documentation

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
└── architecture_docs/
    ├── architecture.md            # Comprehensive documentation
    └── quick_reference.md         # One-page summary

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

## Contributing

This project showcases the Claude Agent SDK's multi-agent composition capabilities. Feel free to extend it with:
- Additional language support (Java, C#, etc.)
- Enhanced metrics collection (LOC, complexity, test coverage)
- Incremental analysis for large repositories
- Custom analysis plugins
- Additional visualization options

## License

See parent repository for license information.
