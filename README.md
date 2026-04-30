# GitHub Flashlight

Flashlight points an LLM-powered analysis pipeline at a codebase and produces structured, cited documentation of every component — per-component analyses, a unified knowledge graph, and a synthesized architecture doc.

It is built on [Burr](https://github.com/apache/burr) for explicit state-machine orchestration and speaks the OpenAI Chat Completions protocol, so it works with **any OpenAI-compatible endpoint** (OpenAI, OpenRouter, vLLM, LM Studio, Ollama, Together, Groq, …).

## How it works

The pipeline has one deterministic phase and two LLM-driven phases. Nothing is inferred by an LLM until the graph is built.

### 1. Deterministic discovery (zero LLM calls)

[agent/discovery/engine.py](agent/discovery/engine.py) walks the repo and classifies every component via language-specific plugins. Each component is tagged with a `ComponentKind`:

| Kind | Description |
|------|-------------|
| **library** | Reusable code with no entrypoint |
| **service** | Long-running process (HTTP, gRPC, daemon) |
| **cli** | Command-line tool |
| **contract** | Smart contract, ABI, or schema |
| **infra** | IaC / deployment config (Terraform, Helm, K8s) |
| **pipeline** | Data pipeline / workflow (Airflow, dbt, …) |
| **frontend** | UI application (React, Vue, Streamlit, SwiftUI) |
| **unknown** | Could not classify |

Supported manifests: `Cargo.toml` (Rust), `go.mod` (Go), `package.json` (TS/JS), `pyproject.toml` (Python), `foundry.toml` / `hardhat.config.*` (Solidity), `Package.swift` (Swift). Plugins live in [agent/discovery/languages/](agent/discovery/languages/).

The [KnowledgeGraphBuilder](agent/schemas/knowledge_graph.py) then builds a unified dependency graph across all components and runs a topological sort to produce `analysis_order.json` — a list of **depth levels**, where every component at depth `d` only depends (transitively) on components at depths `< d`.

### 2. Depth-level component analysis

The Burr state machine in [agent/burr_app.py](agent/burr_app.py) walks the depth levels in order:

```
receive_input -> read_discovery -> analyze_current_depth (loops over depths) -> synthesize -> respond
```

For each depth level, `analyze_current_depth` spawns one component-analyzer subagent per component at that depth. Subagents at the **same depth** run concurrently on a `ThreadPoolExecutor` bounded by `FLASHLIGHT_MAX_PARALLEL` (default 4). The orchestrator waits for the whole depth to complete before advancing.

Each component-analyzer:
- Receives `upstream_context` — summaries of every direct dependency's analysis (which have already completed at a lower depth)
- Runs its own ReAct loop as an independent Burr `Application` so it shows up in the Burr UI with a parent/child relationship
- Reads the component source with `glob_files`, `grep_files`, `read_file`, `bash`
- Emits a Markdown analysis that ends with two structured JSON blocks: `## Analysis Data` (machine-readable summary) and `## Citations` (file/line provenance for every major claim)

The orchestrator persists every returned analysis to `/tmp/{service_name}/service_analyses/{component}.md` — it doesn't trust the LLM to call `write_file` reliably.

> Older versions of Flashlight had a distinct "depth 0" / "depth 1" split (foundation components vs. the rest). That's gone. The pipeline now treats every depth level uniformly, and there can be any number of levels depending on the graph.

### 3. Synthesis

Once every depth has been analyzed, `synthesize` runs the architecture-documenter subagent over every component summary to produce `architecture.md` and `quick_reference.md`.

### 4. Citation extraction (post-analysis)

[agent/utils/citation_extractor.py](agent/utils/citation_extractor.py) parses every `## Citations` block out of the Markdown analyses, validates each citation against the actual source file (existence, line range), and writes a unified `citations.json` next to the analyses.

## Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -e .

cp .env.example .env      # then edit .env with your endpoint credentials
```

Requires Python 3.10+ and [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) on `PATH` for the grep tool.

## LLM configuration

Flashlight uses the OpenAI Chat Completions API, so any OpenAI-compatible provider works.

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `OPENAI_API_KEY` | yes | — | Bearer token for the target endpoint |
| `OPENAI_BASE_URL` | no | `https://api.openai.com/v1` | Point at OpenAI, OpenRouter, vLLM, LM Studio, Ollama, etc. |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | Any model served by the chosen endpoint |
| `FLASHLIGHT_MAX_PARALLEL` | no | `4` | Max component analyzers run concurrently within a depth. Set to `1` to serialize (recommended for Ollama and small API tiers). |

Example configs:

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# OpenRouter (access to Claude, Llama, etc. via one API)
OPENAI_API_KEY=sk-or-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=anthropic/claude-sonnet-4

# Local vLLM / LM Studio / Ollama
OPENAI_API_KEY=not-needed-but-must-be-set
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=meta-llama/Llama-3.1-70B-Instruct
```

## Usage

The primary entry point is the headless `flashlight` CLI ([agent/cli.py](agent/cli.py)).

### Full analysis

```bash
# Local checkout
flashlight --repo /path/to/repo --output ./artifacts/myservice

# GitHub URL (cloned into /tmp/flashlight-repos)
flashlight --repo https://github.com/org/repo --output ./artifacts/myservice
```

### Incremental (diff-driven) analysis

Given a previous run's artifacts and a new commit SHA, Flashlight will only re-analyze components whose files changed between the last and current SHAs:

```bash
# Explicit SHAs
flashlight --repo /path/to/repo --output ./artifacts/myservice \
    --last-sha abc1234 --head-sha def5678

# Auto-detect last-sha from manifest.json in the output dir
flashlight --repo /path/to/repo --output ./artifacts/myservice \
    --head-sha def5678
```

If the diff doesn't map cleanly to existing components (e.g. brand-new files), Flashlight falls back to a full analysis.

### Interactive chat mode

For ad-hoc exploration with the same tool-using agent:

```bash
code-analysis-agent
```

### Verbose logging

```bash
flashlight --repo ... --output ... --verbose   # INFO-level
flashlight --repo ... --output ... --debug     # full trace including HTTP details
```

### Burr UI

Each run (both the orchestrator and every subagent) is tracked by Burr. Start the Burr UI to inspect state transitions, tool calls, token usage, and subagent trees:

```bash
.burr-ui-venv/bin/python -m uvicorn burr.tracking.server.run:app --port 7241
# then open http://localhost:7241
```

## Output structure

Flashlight writes intermediate artifacts to `/tmp/{service_name}/` during a run and then copies the final artifacts to `--output`:

```
<output>/
├── manifest.json                     # source_repo, source_commit, timestamps
├── service_discovery/
│   └── components.json               # Deterministic component inventory
├── dependency_graphs/
│   ├── graph.json                    # Unified knowledge graph
│   └── analysis_order.json           # Topologically-sorted depth levels
├── service_analyses/
│   ├── {component}.md                # Markdown analysis with inline citations
│   ├── {component}.json              # Parsed `## Analysis Data` block
│   └── citations.json                # Validated, aggregated citations
└── architecture_docs/
    ├── architecture.md               # System-wide synthesis
    └── quick_reference.md            # One-page summary
```

Per-run session logs (transcript + structured tool calls) are written under `logs/session_YYYYMMDD_HHMMSS/`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Key modules:

- [agent/burr_app.py](agent/burr_app.py) — Burr state machine, actions, and subagent runners
- [agent/cli.py](agent/cli.py) — Headless CLI and incremental-analysis logic
- [agent/discovery/](agent/discovery/) — Deterministic component discovery
- [agent/schemas/](agent/schemas/) — Component / knowledge-graph data model
- [agent/prompts/subagents/](agent/prompts/subagents/) — Prompt templates for component-analyzer, architecture-documenter, external-service-analyzer

## License

See parent repository for license information.
