"""Headless CLI for github-flashlight.

Provides a non-interactive entry point for CI pipelines to run
full or incremental (diff-driven) codebase analysis.

Usage:
    # Full analysis (no prior artifacts)
    flashlight --repo /path/to/repo --output ./artifacts/company/eigenda

    # Incremental analysis (existing artifacts with manifest)
    flashlight --repo /path/to/repo --output ./artifacts/company/eigenda \
        --last-sha abc1234 --head-sha def5678

    # Incremental with auto-detected SHAs (reads manifest.json from output dir)
    flashlight --repo /path/to/repo --output ./artifacts/company/eigenda \
        --head-sha def5678
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from agent.discovery.engine import discover_components
from agent.discovery.validator import validate_discovery, validate_graph
from agent.schemas.core import Component, ComponentKind
from agent.schemas.dependency_graph import DependencyGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Diff logic
# ---------------------------------------------------------------------------

def load_manifest(artifacts_dir: Path) -> dict | None:
    """Load manifest.json from an existing artifacts directory."""
    manifest_path = artifacts_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r") as f:
        return json.load(f)


def load_components(artifacts_dir: Path) -> list[dict]:
    """Load components from service_discovery in an existing artifacts directory.

    Merges both 'libraries' and 'applications' arrays from components.json,
    falling back to separate libraries.json / applications.json files.
    """
    components = []

    # Try components.json first (combined format)
    combined = artifacts_dir / "service_discovery" / "components.json"
    if combined.exists():
        with open(combined) as f:
            data = json.load(f)
        components.extend(data.get("libraries", []))
        components.extend(data.get("applications", []))
        return components

    # Fall back to separate files
    for filename in ("libraries.json", "applications.json"):
        path = artifacts_dir / "service_discovery" / filename
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            # Handle both array and object-with-key formats
            if isinstance(data, list):
                components.extend(data)
            elif isinstance(data, dict):
                for key in ("libraries", "applications"):
                    components.extend(data.get(key, []))

    return components


def git_diff_files(repo_path: Path, last_sha: str, head_sha: str) -> list[str]:
    """Get list of changed files between two commits."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{last_sha}..{head_sha}"],
        capture_output=True,
        text=True,
        cwd=repo_path,
    )
    if result.returncode != 0:
        logger.warning(
            "git diff failed (rc=%d): %s — falling back to full analysis",
            result.returncode,
            result.stderr.strip(),
        )
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def map_files_to_components(
    changed_files: list[str],
    components: list[dict],
) -> tuple[set[str], list[str]]:
    """Map changed file paths to their owning components.

    Returns:
        (affected_component_names, unmapped_files)
    """
    affected: set[str] = set()
    unmapped: list[str] = []

    for filepath in changed_files:
        matched = False
        for comp in components:
            root = comp.get("root_path", "")
            if not root:
                continue
            # Prefix match: file is under this component's root
            if filepath == root or filepath.startswith(root.rstrip("/") + "/"):
                affected.add(comp["name"])
                matched = True
                break
        if not matched:
            unmapped.append(filepath)

    return affected, unmapped


def compute_diff_context(
    repo_path: Path,
    artifacts_dir: Path,
    last_sha: str,
    head_sha: str,
) -> dict:
    """Compute the full diff context for incremental analysis.

    Returns a dict with:
        mode: "full" or "incremental"
        changed_components: set of component names (if incremental)
        unmapped_files: files not matching any component
        changed_files: raw list of changed file paths
    """
    if not last_sha:
        return {"mode": "full"}

    components = load_components(artifacts_dir)
    if not components:
        logger.info("No existing components found — running full analysis")
        return {"mode": "full"}

    changed_files = git_diff_files(repo_path, last_sha, head_sha)
    if not changed_files:
        # git diff failed or empty — full analysis as safety fallback
        return {"mode": "full"}

    affected, unmapped = map_files_to_components(changed_files, components)

    if not affected and not unmapped:
        return {"mode": "none"}  # nothing changed

    return {
        "mode": "incremental",
        "changed_components": affected,
        "unmapped_files": unmapped,
        "changed_files": changed_files,
    }


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_analysis_prompt(
    repo_path: Path,
    service_name: str,
    diff_context: dict,
    artifacts_dir: Path | None = None,
    head_sha: str = "",
) -> str:
    """Build the prompt sent to the lead agent."""

    prompt = f"Analyze the codebase at {repo_path}"

    if head_sha:
        prompt += f"\n\nSOURCE_COMMIT: {head_sha}"

    # Tell the LLM that discovery has already been done
    work_dir = Path(f"/tmp/{service_name}")
    discovery_file = work_dir / "service_discovery" / "components.json"
    graph_file = work_dir / "dependency_graphs" / "library_graph.json"

    if discovery_file.exists():
        prompt += (
            "\n\nDISCOVERY_COMPLETE: Component discovery has already been done deterministically."
            f"\nRead the component inventory at: {discovery_file}"
        )
        if graph_file.exists():
            prompt += f"\nRead the dependency graph at: {graph_file}"
        prompt += (
            "\n\nSKIP Phase 0.2 (library discovery) and Phase 1.1 (application discovery)."
            "\nThe components.json and library_graph.json are already populated."
            "\nStart directly with Phase 1.2 (library analysis) using the depth order"
            "\nfrom the graph file. Spawn code-library-analyzer subagents for each library."
        )

    if diff_context["mode"] == "incremental":
        components = diff_context["changed_components"]
        prompt += "\n\nCHANGED_COMPONENTS:"
        for name in sorted(components):
            # Find the files that belong to this component
            related_files = [
                f
                for f in diff_context["changed_files"]
                if any(
                    f.startswith(c.get("root_path", "").rstrip("/") + "/")
                    or f == c.get("root_path", "")
                    for c in load_components(artifacts_dir)
                    if c["name"] == name
                )
            ]
            if related_files:
                prompt += f"\n- {name} (files: {', '.join(related_files[:10])})"
            else:
                prompt += f"\n- {name}"

        if diff_context.get("unmapped_files"):
            prompt += "\n\nNEW_FILES_OUTSIDE_KNOWN_COMPONENTS:"
            for f in diff_context["unmapped_files"][:20]:
                prompt += f"\n- {f}"
            prompt += (
                "\n\n(These files don't match any existing component. "
                "Run discovery to determine if they belong to new components.)"
            )

        if artifacts_dir and artifacts_dir.exists():
            prompt += (
                f"\n\nEXISTING_ARTIFACTS: {artifacts_dir}"
                "\n(Read existing service_analyses/ for unchanged component context. "
                "Only re-analyze the CHANGED_COMPONENTS listed above.)"
            )

    return prompt


# ---------------------------------------------------------------------------
# Headless analysis
# ---------------------------------------------------------------------------

async def analyze(
    repo_path: str,
    output_dir: str,
    last_sha: str = "",
    head_sha: str = "",
):
    """Run headless (non-interactive) codebase analysis.

    Args:
        repo_path: Path to the cloned repository.
        output_dir: Where to write final artifacts.
        last_sha: Previous commit SHA (from manifest). Empty for full analysis.
        head_sha: Current commit SHA being analyzed.
    """
    # Late imports: these require claude-agent-sdk and other heavy deps
    # that aren't needed for discovery/diff logic (and may not be installed in CI).
    from dotenv import load_dotenv
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AgentDefinition,
        HookMatcher,
    )
    from agent.utils.subagent_tracker import SubagentTracker
    from agent.utils.transcript import setup_session, TranscriptWriter
    from agent.utils.message_handler import process_assistant_message
    from agent.utils.template_loader import TemplateLoader

    load_dotenv()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not found.", file=sys.stderr)
        sys.exit(1)

    repo = Path(repo_path).resolve()
    output = Path(output_dir).resolve()
    service_name = repo.name

    if not repo.exists():
        print(f"Error: repo path does not exist: {repo}", file=sys.stderr)
        sys.exit(1)

    # Auto-detect last_sha from existing manifest if not provided
    if not last_sha and output.exists():
        manifest = load_manifest(output)
        if manifest:
            last_sha = manifest.get("source_commit", "")
            logger.info("Loaded last_sha from manifest: %s", last_sha)

    # Compute diff context
    diff_context = compute_diff_context(repo, output, last_sha, head_sha)

    if diff_context["mode"] == "none":
        print("No changes detected — skipping analysis.")
        return

    mode_label = diff_context["mode"]
    if mode_label == "incremental":
        n = len(diff_context["changed_components"])
        print(f"Incremental analysis: {n} component(s) changed")
        for name in sorted(diff_context["changed_components"]):
            print(f"  - {name}")
    else:
        print("Full analysis (no prior state or diff unavailable)")

    # ---------------------------------------------------------------
    # Phase 0: Deterministic discovery (zero LLM calls)
    # ---------------------------------------------------------------
    print("\nRunning deterministic discovery...")
    work_dir = Path(f"/tmp/{service_name}")
    work_dir.mkdir(parents=True, exist_ok=True)
    discovery_dir = work_dir / "service_discovery"
    graph_dir = work_dir / "dependency_graphs"

    # Discover components from source
    components = discover_components(repo, output_dir=discovery_dir)
    print(f"  Discovered {len(components)} components")

    # Log component summary by kind
    by_kind: dict[str, list[str]] = {}
    for comp in components:
        by_kind.setdefault(comp.kind.value, []).append(comp.name)
    for kind, names in sorted(by_kind.items()):
        print(f"    {kind}: {', '.join(sorted(names)[:8])}", end="")
        if len(names) > 8:
            print(f" (+{len(names) - 8} more)")
        else:
            print()

    # Validate discovery output
    errors = validate_discovery(components, repo)
    if errors:
        print(f"  Discovery warnings: {len(errors)}")
        for err in errors[:5]:
            print(f"    - {err}")

    # Build dependency graph
    libraries = [c for c in components if c.is_library]
    if libraries:
        graph = DependencyGraph()
        for lib in libraries:
            graph.add_node(lib.name)
        for lib in libraries:
            for dep in lib.internal_dependencies:
                if dep in {l.name for l in libraries}:
                    graph.add_edge(lib.name, dep)

        depth_order = graph.get_depth_order()
        graph_errors = validate_graph(components, depth_order)
        if graph_errors:
            print(f"  Graph warnings: {len(graph_errors)}")

        # Write graph
        graph_dir.mkdir(parents=True, exist_ok=True)
        phase1, phase2 = graph.get_analysis_order()
        graph_json = {
            "graph_type": "library_dependencies",
            "nodes": [
                {
                    "id": lib.name,
                    "type": lib.type,
                    "kind": lib.kind.value,
                    "phase": 1 if lib.name in phase1 else 2,
                }
                for lib in libraries
            ],
            "edges": [
                {"from": name, "to": dep}
                for name in graph.nodes
                for dep in graph.get_direct_dependencies(name)
            ],
            "depth_order": [list(level) for level in depth_order],
            "analysis_order": {"phase1": phase1, "phase2": phase2},
        }
        with open(graph_dir / "library_graph.json", "w") as f:
            json.dump(graph_json, f, indent=2)

        print(f"  Dependency graph: {len(depth_order)} depth levels")
        for i, level in enumerate(depth_order):
            print(f"    depth {i}: {', '.join(level[:6])}", end="")
            if len(level) > 6:
                print(f" (+{len(level) - 6} more)")
            else:
                print()
    else:
        print("  No libraries found — skipping dependency graph")

    print()

    # Build the prompt
    artifacts_dir = output if output.exists() else None
    prompt = build_analysis_prompt(
        repo, service_name, diff_context, artifacts_dir, head_sha
    )

    # Setup session
    transcript_file, session_dir = setup_session()
    transcript = TranscriptWriter(transcript_file)

    # Load prompts (same as interactive mode)
    prompts_dir = Path(__file__).parent / "prompts"

    def load_prompt(filename: str) -> str:
        with open(prompts_dir / filename, "r", encoding="utf-8") as f:
            return f.read().strip()

    lead_agent_prompt = load_prompt("lead_agent.txt")
    base_code_analyzer_prompt = load_prompt("code_analyzer.txt")
    architecture_documenter_prompt = load_prompt("subagents/architecture_documenter.txt")
    external_service_analyzer_prompt = load_prompt(
        "subagents/external_service_analyzer.txt"
    )

    # Load templates
    templates_dir = Path(__file__).parent.parent / "templates" / "analysis-template"
    template_loader = TemplateLoader(templates_dir)
    template_instructions = template_loader.get_template_instructions()
    application_template = template_loader.get_template("application")
    package_template = template_loader.get_template("package")

    code_analyzer_prompt = f"""{base_code_analyzer_prompt}

{template_instructions}

<application_analysis_template>
{application_template}
</application_analysis_template>

<package_analysis_template>
{package_template}
</package_analysis_template>
"""

    # Initialize tracker
    tracker = SubagentTracker(
        transcript_writer=transcript, session_dir=session_dir, verbose=False
    )

    # Define agents (identical to interactive mode)
    agents = {
        "code-library-analyzer": AgentDefinition(
            description=(
                "Use this agent to perform deep analysis of a specific library code component. "
                "The code-analyzer uses Glob, Grep, Read, and Bash to explore code structure, "
                "identify key components, trace data flows, and document architecture. "
                "Receives upstream dependency context when analyzing library components with dependencies. "
                "Produces structured analysis reports in Markdown format "
                f"in /tmp/{service_name}/service_analyses/. "
                "Each library should get its own code-library-analyzer instance."
            ),
            tools=["Glob", "Grep", "Read", "Bash", "Write"],
            prompt=code_analyzer_prompt,
            model="sonnet",
        ),
        "application-analyzer": AgentDefinition(
            description=(
                "Use this agent to perform deep analysis of an application code component. "
                "The code-analyzer uses Glob, Grep, Read, and Bash to explore code structure, "
                "identify key components, trace data flows, and document architecture. "
                "Receives upstream dependency context when analyzing library components with dependencies. "
                "Produces structured analysis reports in Markdown format "
                f"in /tmp/{service_name}/service_analyses/. "
                "Each application should get its own application-analyzer instance."
            ),
            tools=["Glob", "Grep", "Read", "Bash", "Write"],
            prompt=code_analyzer_prompt,
            model="sonnet",
        ),
        "architecture-documenter": AgentDefinition(
            description=(
                "Use this agent AFTER all application analyses complete to synthesize architecture documentation. "
                "Runs once after analysis phase, reads all completed analyses and graphs, creates comprehensive docs."
            ),
            tools=["Glob", "Read", "Write"],
            prompt=architecture_documenter_prompt,
            model="sonnet",
        ),
        "external-service-analyzer": AgentDefinition(
            description=(
                "Use this agent to analyze how a specific external service (e.g., AWS S3, PostgreSQL, "
                "Stripe, Ethereum RPC) is integrated into the codebase. Produces a dedicated analysis "
                "file documenting the integration architecture, client libraries, API surface, "
                "configuration, and security considerations. Spawn one instance per external service."
            ),
            tools=["Glob", "Grep", "Read", "Bash", "Write"],
            prompt=external_service_analyzer_prompt,
            model="sonnet",
        ),
    }

    hooks = {
        "PreToolUse": [
            HookMatcher(matcher=None, hooks=[tracker.pre_tool_use_hook])
        ],
        "PostToolUse": [
            HookMatcher(matcher=None, hooks=[tracker.post_tool_use_hook])
        ],
        "SubagentStop": [
            HookMatcher(matcher=None, hooks=[tracker.post_subagent_stop_hook])
        ],
    }

    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        setting_sources=["project"],
        system_prompt=lead_agent_prompt,
        allowed_tools=["Task", "Glob", "Read", "Bash", "Write"],
        agents=agents,
        hooks=hooks,
        model="sonnet",
        max_thinking_tokens=9999,
    )

    print(f"\nStarting {mode_label} analysis of {service_name}...")
    print(f"  Repo: {repo}")
    print(f"  Output: {output}")
    if last_sha:
        print(f"  Last SHA: {last_sha}")
    if head_sha:
        print(f"  Head SHA: {head_sha}")
    print()

    try:
        async with ClaudeSDKClient(options=options) as client:
            # Send the analysis prompt
            transcript.write_to_file(f"\nPrompt: {prompt}\n")
            await client.query(prompt=prompt)

            transcript.write("\nAgent: ", end="")

            # Stream the full response to completion
            message_count = 0
            api_call_count = 0
            async for msg in client.receive_response():
                message_count += 1
                msg_type = type(msg).__name__

                if msg_type == "AssistantMessage":
                    api_call_count += 1
                    print(
                        f"\n[CLAUDE CALL #{api_call_count}] AssistantMessage completed",
                        flush=True,
                    )
                    process_assistant_message(msg, tracker, transcript)

            transcript.write("\n")
            print(f"\nAnalysis complete ({api_call_count} API calls)")

    finally:
        transcript.close()
        tracker.close()

    # Copy artifacts from /tmp/{service_name}/ to output_dir
    tmp_artifacts = Path(f"/tmp/{service_name}")
    if not tmp_artifacts.exists():
        print(f"Warning: expected output at {tmp_artifacts} but not found", file=sys.stderr)
        sys.exit(1)

    print(f"\nCopying artifacts from {tmp_artifacts} to {output}...")
    output.mkdir(parents=True, exist_ok=True)

    # Copy each artifact subdirectory (not project/)
    artifact_dirs = [
        "service_discovery",
        "dependency_graphs",
        "service_analyses",
        "architecture_docs",
    ]
    for dirname in artifact_dirs:
        src = tmp_artifacts / dirname
        dst = output / dirname
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Copy manifest.json
    manifest_src = tmp_artifacts / "manifest.json"
    if manifest_src.exists():
        shutil.copy2(manifest_src, output / "manifest.json")

    print(f"Artifacts written to {output}")
    print(f"Session logs: {session_dir}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for headless analysis."""
    parser = argparse.ArgumentParser(
        prog="flashlight",
        description="Headless codebase analysis with github-flashlight",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to the cloned repository to analyze",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for artifacts",
    )
    parser.add_argument(
        "--last-sha",
        default="",
        help=(
            "Previous commit SHA (from last analysis). "
            "If omitted, reads from manifest.json in --output dir."
        ),
    )
    parser.add_argument(
        "--head-sha",
        default="",
        help="Current commit SHA being analyzed",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Configure logging
    if args.debug:
        os.environ["AGENT_DEBUG"] = "true"
        log_level = logging.DEBUG
    elif args.verbose:
        os.environ["AGENT_VERBOSE"] = "true"
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(
        analyze(
            repo_path=args.repo,
            output_dir=args.output,
            last_sha=args.last_sha,
            head_sha=args.head_sha,
        )
    )


if __name__ == "__main__":
    main()
