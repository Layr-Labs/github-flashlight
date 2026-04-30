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
from agent.schemas.knowledge_graph import KnowledgeGraphBuilder

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
    """Load components from service_discovery in an existing artifacts directory."""
    combined = artifacts_dir / "service_discovery" / "components.json"
    if not combined.exists():
        return []

    with open(combined) as f:
        data = json.load(f)

    if isinstance(data, dict):
        return data.get("components", [])
    if isinstance(data, list):
        return data
    return []


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
    graph_file = work_dir / "dependency_graphs" / "graph.json"
    analysis_order_file = work_dir / "dependency_graphs" / "analysis_order.json"

    if discovery_file.exists():
        prompt += (
            "\n\nDISCOVERY_COMPLETE: Component discovery has already been done deterministically."
            f"\nRead the component inventory at: {discovery_file}"
        )
        if graph_file.exists():
            prompt += f"\nRead the unified knowledge graph at: {graph_file}"
        if analysis_order_file.exists():
            prompt += f"\nRead the analysis order at: {analysis_order_file}"
        prompt += (
            "\n\nSKIP discovery phases — components.json and graph.json are already populated."
            "\nStart directly with component analysis using the depth order from analysis_order.json."
            "\nSpawn component-analyzer subagents for each component, processing depth levels in order."
            "\nAll components at the same depth level can be analyzed in parallel."
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


def analyze(
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
    # Late imports for heavy deps
    from dotenv import load_dotenv

    from agent.burr_app import build_interactive_agent, build_analysis_pipeline
    from agent.utils.transcript import setup_session, TranscriptWriter
    from agent.utils.template_loader import TemplateLoader

    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found.", file=sys.stderr)
        print(
            "Flashlight uses any OpenAI-compatible endpoint. Set OPENAI_API_KEY "
            "and (optionally) OPENAI_BASE_URL + OPENAI_MODEL.",
            file=sys.stderr,
        )
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

    # Expose the repo at /tmp/{service_name}/project/ — every subagent prompt
    # references this path as the source root, so without it analyzers can't
    # read any code and end up hallucinating. Symlink (no disk copy) so large
    # repos stay cheap and the view always tracks the current clone.
    _setup_project_dir(repo, work_dir)

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

    # Build unified knowledge graph (all components, not just libraries)
    print("\n  Building unified knowledge graph...")
    graph_builder = KnowledgeGraphBuilder(components)
    knowledge_graph = graph_builder.build(
        source_repo=str(repo),
        source_commit=head_sha,
    )
    depth_order = graph_builder.get_analysis_order()

    # Validate graph
    graph_errors = validate_graph(components, depth_order)
    if graph_errors:
        print(f"  Graph warnings: {len(graph_errors)}")

    # Write graph
    graph_dir.mkdir(parents=True, exist_ok=True)

    # Write unified graph.json
    with open(graph_dir / "graph.json", "w") as f:
        json.dump(knowledge_graph.to_dict(), f, indent=2)

    # Also write analysis_order.json for the lead agent
    analysis_order = {
        "depth_levels": depth_order,
        "total_components": len(components),
        "level_count": len(depth_order),
        "by_kind": {
            kind.value: sum(1 for c in components if c.kind == kind)
            for kind in ComponentKind
            if any(c.kind == kind for c in components)
        },
    }
    with open(graph_dir / "analysis_order.json", "w") as f:
        json.dump(analysis_order, f, indent=2)

    print(
        f"  Knowledge graph: {len(components)} components, {len(knowledge_graph.edges)} edges"
    )
    print(f"  Analysis order: {len(depth_order)} depth levels")
    for i, level in enumerate(depth_order):
        by_kind = {}
        for name in level:
            comp = knowledge_graph.components.get(name)
            if comp:
                by_kind.setdefault(comp.kind.value, []).append(name)
        kind_summary = ", ".join(f"{k}:{len(v)}" for k, v in sorted(by_kind.items()))
        print(f"    depth {i}: {len(level)} components ({kind_summary})")

    print()

    # Setup session for transcript
    transcript_file, session_dir = setup_session()
    transcript = TranscriptWriter(transcript_file)

    # Build the Burr analysis pipeline (structured multi-agent workflow)
    # The pipeline loads prompts internally based on component kind
    app = build_analysis_pipeline(
        service_name=service_name,
        project_name=f"flashlight-{service_name}",
    )

    print(f"\nStarting {mode_label} analysis of {service_name}...")
    print(f"  Repo: {repo}")
    print(f"  Output: {output}")
    if last_sha:
        print(f"  Last SHA: {last_sha}")
    if head_sha:
        print(f"  Head SHA: {head_sha}")
    print(
        "  Burr UI: http://localhost:7241  (run '.burr-ui-venv/bin/python -m uvicorn burr.tracking.server.run:app --port 7241' to start)"
    )
    print()

    try:
        transcript.write_to_file(f"\nAnalyzing {service_name}...\n")

        # Run the Burr analysis pipeline
        # The pipeline: receive_input -> read_discovery -> analyze_current_depth (loop) -> synthesize -> respond
        action, result, state = app.run(
            halt_after=["respond"],
            inputs={
                "task": f"Analyze {service_name}",
                "service_name": service_name,
            },
        )

        # Get the response
        response = state.get("final_response", "")
        transcript.write_to_file(f"\nResponse: {response}\n")

        # Count tokens from component analyses
        analyses = state.get("component_analyses", {})
        total_components = len(analyses)

        transcript.write("\n")
        print(f"\nAnalysis complete ({total_components} components analyzed)")

    finally:
        transcript.close()

    # Copy artifacts from /tmp/{service_name}/ to output_dir
    tmp_artifacts = Path(f"/tmp/{service_name}")
    if not tmp_artifacts.exists():
        print(
            f"Warning: expected output at {tmp_artifacts} but not found",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---------------------------------------------------------------
    # Post-analysis: Extract structured citations from Markdown
    # ---------------------------------------------------------------
    from agent.utils.citation_extractor import build_citations_index

    analyses_dir = tmp_artifacts / "service_analyses"
    if analyses_dir.exists():
        print("\nExtracting citations from analysis files...")

        # Load manifest for source_repo/source_commit if available
        manifest_data = load_manifest(tmp_artifacts)
        cite_source_repo = ""
        cite_source_commit = ""
        if manifest_data:
            cite_source_repo = manifest_data.get("source_repo", "")
            cite_source_commit = manifest_data.get("source_commit", "")

        # The project source is at /tmp/{service_name}/project/
        project_root = tmp_artifacts / "project"
        cite_repo_root = project_root if project_root.exists() else None

        # Build {component_name: root_path} map so the extractor can retry
        # component-relative citation paths (e.g. when the LLM emits
        # "base_model.py" for the models component, we want to fall back to
        # "omlx/models/base_model.py"). Reads from the full unified graph
        # since components.json may only list the repo-root entry for
        # single-manifest Python packages.
        component_roots: dict[str, str] = {}
        graph_file = tmp_artifacts / "dependency_graphs" / "graph.json"
        if graph_file.exists():
            try:
                with open(graph_file) as f:
                    graph_data = json.load(f)
                nodes = graph_data.get("nodes", {}).get("components", {})
                for name, comp in nodes.items():
                    root = comp.get("root_path", "")
                    if root and root != ".":
                        component_roots[name] = root
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not load component roots from graph: %s", exc)

        cite_index = build_citations_index(
            analyses_dir=analyses_dir,
            repo_root=cite_repo_root,
            source_repo=cite_source_repo,
            source_commit=cite_source_commit,
            component_roots=component_roots,
        )

        meta = cite_index.get("metadata", {})
        total = meta.get("total_citations", 0)
        components = meta.get("components_with_citations", 0)
        errors = meta.get("total_validation_errors", 0)
        print(f"  Extracted {total} citations across {components} components")
        if errors:
            print(f"  ({errors} validation warnings)")

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


def _setup_project_dir(repo: Path, work_dir: Path) -> Path:
    """Ensure `<work_dir>/project` points at the repo the subagents analyze.

    Subagent prompts all reference `/tmp/{service_name}/project/` as the
    source root. This function makes that path resolve to ``repo``.

    Prefers a symlink (no disk copy, always consistent with the clone); falls
    back to copying if the platform can't create the symlink.

    Idempotent: safe to call across re-runs.

    Args:
        repo: Resolved path to the repository root (clone or local checkout)
        work_dir: `/tmp/{service_name}` working directory

    Returns:
        Path to the project directory (``work_dir / "project"``)
    """
    project_dir = work_dir / "project"
    repo = repo.resolve()
    work_dir_resolved = work_dir.resolve()

    # Refuse to alias a work_dir-rooted path onto itself (would create a cycle
    # like /tmp/foo/project/project/project/...).
    if repo == work_dir_resolved or work_dir_resolved in repo.parents:
        raise ValueError(
            f"Refusing to link {project_dir} -> {repo}: the repo lives inside "
            f"the work_dir ({work_dir_resolved}). Move the clone outside "
            f"{work_dir_resolved} or use a different service name."
        )

    # If project/ already points at the right target, keep it.
    if project_dir.is_symlink():
        try:
            if project_dir.resolve() == repo:
                return project_dir
        except OSError:
            pass
        project_dir.unlink()
    elif project_dir.exists():
        # Stale real directory from an older run — remove so we can relink.
        shutil.rmtree(project_dir)

    try:
        project_dir.symlink_to(repo, target_is_directory=True)
        return project_dir
    except OSError as exc:
        logger.warning(
            "Could not symlink %s → %s (%s); falling back to copy.",
            project_dir,
            repo,
            exc,
        )
        shutil.copytree(
            repo,
            project_dir,
            symlinks=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"),
        )
        return project_dir


def clone_repo(url: str, target_dir: Path) -> Path:
    """Clone a git repository to a target directory.

    Args:
        url: Git repository URL (https://github.com/org/repo)
        target_dir: Directory to clone into

    Returns:
        Path to the cloned repository
    """
    import subprocess
    import re

    # Extract repo name from URL
    match = re.search(r"/([^/]+?)(?:\.git)?$", url)
    if not match:
        raise ValueError(f"Could not extract repo name from URL: {url}")

    repo_name = match.group(1)
    repo_path = target_dir / repo_name

    if repo_path.exists():
        print(f"  Repository already exists at {repo_path}, pulling latest...")
        subprocess.run(
            ["git", "pull"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
    else:
        print(f"  Cloning {url} to {repo_path}...")
        target_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(repo_path)],
            check=True,
            capture_output=True,
        )

    return repo_path


def main():
    """CLI entry point for headless analysis."""
    parser = argparse.ArgumentParser(
        prog="flashlight",
        description="Headless codebase analysis with github-flashlight",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to local repository OR GitHub URL to clone",
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

    # Handle GitHub URLs - clone to /tmp
    repo_path = args.repo
    if (
        repo_path.startswith("http://")
        or repo_path.startswith("https://")
        or repo_path.startswith("git@")
    ):
        print("Detected repository URL, cloning...")
        clone_dir = Path("/tmp/flashlight-repos")
        repo_path = str(clone_repo(repo_path, clone_dir))

    analyze(
        repo_path=repo_path,
        output_dir=args.output,
        last_sha=args.last_sha,
        head_sha=args.head_sha,
    )


if __name__ == "__main__":
    main()
