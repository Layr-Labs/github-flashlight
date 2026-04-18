# GitHub Flashlight

GitHub Flashlight is a repository analysis pipeline that combines deterministic component discovery with a Burr-orchestrated multi-agent workflow. It scans a local repo or GitHub URL, classifies components across multiple languages, builds a unified dependency graph, analyzes components depth-by-depth through OpenRouter-backed models, and emits structured artifacts for documentation, RAG ingestion, and architecture visualization.

## Highlights

- **Deterministic discovery first**: manifest parsing and component classification happen before any LLM call
- **Flat component inventory**: all discovered components live in one `components.json` file instead of separate libraries/applications splits
- **Eight component kinds**: `library`, `service`, `cli`, `contract`, `infra`, `pipeline`, `frontend`, `unknown`
- **Unified knowledge graph**: `graph.json` is the source of truth for dependencies and analysis order
- **Depth-ordered parallel analysis**: Burr runs component analyzers level-by-level so direct dependencies are available as context
- **Incremental mode**: existing artifacts plus git SHAs let Flashlight re-analyze only changed components
- **Citation extraction**: Markdown analyses are post-processed into per-component and aggregated citation indexes
- **Built-in observability**: Burr tracking UI, session transcripts, and optional live monitoring scripts

## Requirements

- Python 3.10+
- `git` available on your machine
- An OpenRouter API key
- Access to the repository you want to analyze

## Installation

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the package
pip install -e .

# Configure environment
cp .env.example .env
```

Set at least:

```bash
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=anthropic/claude-sonnet-4
```

`OPENROUTER_MODEL` is optional; the default is `anthropic/claude-sonnet-4`.

## Quick Start

Run a full analysis of a local repository:

```bash
flashlight --repo /path/to/repo --output ./artifacts/my-repo
```

Analyze a GitHub repository URL directly:

```bash
flashlight --repo https://github.com/org/repo --output ./artifacts/repo
```

When you pass a URL, Flashlight clones or updates the repo under `/tmp/flashlight-repos/<repo>` before analysis.

Equivalent module invocation:

```bash
python -m agent.cli --repo /path/to/repo --output ./artifacts/my-repo
```

## Incremental Analysis

If `manifest.json` already exists in the output directory, Flashlight can reuse its `source_commit` as the previous baseline and only re-analyze changed components.

Auto-detect the previous SHA from the existing manifest:

```bash
flashlight \
  --repo /path/to/repo \
  --output ./artifacts/my-repo \
  --head-sha "$(git -C /path/to/repo rev-parse HEAD)"
```

Or provide both SHAs explicitly:

```bash
flashlight \
  --repo /path/to/repo \
  --output ./artifacts/my-repo \
  --last-sha <previous_commit> \
  --head-sha <current_commit>
```

Incremental mode uses git diff output plus the prior `service_discovery/components.json` to map changed files back to owning components.

## Observability

### Burr Tracking UI

The active runtime is Burr. Start the Burr tracking server with:

```bash
.burr-ui-venv/bin/python -m uvicorn burr.tracking.server.run:app --port 7241
```

During analysis, Flashlight prints the tracking URL:

```text
http://localhost:7241
```

### Verbose and Debug Logging

```bash
flashlight --repo /path/to/repo --output ./artifacts/my-repo --verbose
flashlight --repo /path/to/repo --output ./artifacts/my-repo --debug
```

These modes surface OpenRouter calls, tool usage, subagent lifecycle, and more detailed pipeline logging.

### Live Session Monitor

```bash
./observability/live_monitor.sh
```

This launches the local observability dashboard in `observability/` for real-time session monitoring.

## Artifact Layout

Artifacts are generated under `/tmp/<repo-name>/` during execution and copied into your `--output` directory at the end of the run.

```text
artifacts/<repo>/
├── manifest.json
├── service_discovery/
│   └── components.json
├── dependency_graphs/
│   ├── graph.json
│   └── analysis_order.json
├── service_analyses/
│   ├── <component>.md
│   ├── <component>.citations.json
│   └── all_citations.json
└── architecture_docs/
    ├── architecture.md
    └── quick_reference.md

logs/
└── session_YYYYMMDD_HHMMSS/
    ├── transcript.txt
    └── tool_calls.jsonl
```

Notes:

- `components.json` is a flat inventory of every discovered component plus metadata counts.
- `graph.json` is the unified knowledge graph that replaces the old fragmented graph outputs.
- `analysis_order.json` contains depth buckets used by the orchestrator.
- `manifest.json` is used for provenance and incremental re-analysis.
- Citation files are derived from the Markdown reports after the analysis phase completes.

## Pipeline Architecture

Flashlight runs in six stages:

1. **Deterministic discovery**
   - Scans manifests such as `Cargo.toml`, `go.mod`, `package.json`, `pyproject.toml`, `foundry.toml`, and `Package.swift`
   - Produces `service_discovery/components.json` with zero LLM calls

2. **Knowledge graph construction**
   - Builds a unified graph for all component kinds
   - Computes depth-ordered analysis buckets and writes `analysis_order.json`

3. **Lead orchestration with Burr**
   - The main state machine is `receive_input -> read_discovery -> analyze_current_depth (loop) -> synthesize -> respond`
   - Each depth level is analyzed in parallel where possible

4. **Component analysis**
   - Component analyzers inspect architecture, APIs, data flows, dependencies, and external integrations
   - Direct dependency analyses are passed forward as context

5. **Architecture synthesis**
   - An architecture documenter synthesizes cross-component patterns, system flows, and technology inventory
   - Produces `architecture.md` and `quick_reference.md`

6. **Citation extraction and packaging**
   - Extracts structured citations from component analyses
   - Writes per-component citation files and `all_citations.json`
   - Copies final artifacts into the requested output directory

## Component Kinds

GitHub Flashlight classifies every discovered component into one of eight `ComponentKind` values:

| Kind | Description |
|------|-------------|
| **Library** | Reusable code with no entrypoint |
| **Service** | Long-running process such as an API server, daemon, or worker |
| **CLI** | Command-line tool |
| **Contract** | Smart contract, API definition, or schema |
| **Infra** | Infrastructure-as-code or deployment config |
| **Pipeline** | Workflow or data-pipeline definition |
| **Frontend** | UI application such as React, Next.js, Streamlit, Gradio, or SwiftUI |
| **Unknown** | Could not be classified deterministically |

## Supported Ecosystems

Discovery is currently implemented for:

- **Go** via `go.mod`
- **Rust** via `Cargo.toml`
- **Python** via `pyproject.toml`
- **TypeScript / JavaScript** via `package.json`
- **Solidity** via `foundry.toml` and Hardhat config files
- **Swift** via `Package.swift`

Each language plugin applies language-specific entrypoint, dependency, naming, and file-structure heuristics to classify components and resolve internal dependencies.

## Detection Pipeline

Classification follows this deterministic sequence:

1. Manifest discovery
2. Manifest analysis
3. File-structure checks for entrypoints
4. Dependency scanning for framework signals
5. Targeted source scanning for runtime indicators
6. Name-based heuristics
7. Safe fallback classification

This keeps repo inventory fast, reproducible, and cheap before the LLM-driven phases begin.

## Design Principles

- **Discovery before analysis**: the LLM never invents the repo inventory
- **Direct-dependency context only**: analyzers receive upstream context from direct dependencies, not the full transitive graph
- **Depth-ordered parallelism**: maximize parallel work without violating dependency ordering
- **Structured artifacts first**: machine-readable outputs are first-class, with Markdown as a derived human-facing view
- **Provenance matters**: manifests, source commits, and code citations are preserved for downstream indexing and review

## Utilities

Two helper scripts are available for deterministic graph building from an existing discovery output:

```bash
python scripts/build_dependency_graph.py /tmp/my-repo/service_discovery /tmp/my-repo/dependency_graphs
python scripts/build_knowledge_graph.py /tmp/my-repo/service_discovery /tmp/my-repo/dependency_graphs
```

`build_knowledge_graph.py` writes the current unified `graph.json` format and `analysis_order.json`.

## Legacy Note

The active production path is the Burr-based pipeline in `agent/burr_app.py`. The `*_langgraph_legacy.py` files remain in the repository as migration-era references and are not the primary execution path.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## License

See parent repository for license information.
