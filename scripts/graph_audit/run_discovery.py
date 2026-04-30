"""Clone each repo in corpus.json and run Flashlight deterministic discovery.

Writes per-repo artifacts under audit_out/{slug}/:
  - components.json
  - edges.json
  - analysis_order.json
  - project/  (shallow clone of the repo)

No LLM calls.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from agent.discovery.engine import discover_components
from agent.schemas.knowledge_graph import KnowledgeGraphBuilder


def slugify(full_name: str) -> str:
    return full_name.replace("/", "__")


def clone_shallow(clone_url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(dest)],
            check=True,
            capture_output=True,
            timeout=300,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"  CLONE FAILED: {e}")
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return False


def run_for_repo(repo: dict, out_root: Path) -> dict:
    slug = slugify(repo["full_name"])
    repo_dir = out_root / slug
    project_dir = repo_dir / "project"

    result = {"full_name": repo["full_name"], "slug": slug, "language": repo["language"]}

    if not clone_shallow(repo["clone_url"], project_dir):
        result["status"] = "clone_failed"
        return result

    try:
        components = discover_components(project_dir)
    except Exception as e:
        result["status"] = "discovery_failed"
        result["error"] = str(e)
        return result

    graph = KnowledgeGraphBuilder(components).build(source_repo=repo["full_name"])
    analysis_order = graph.get_depth_order()

    (repo_dir / "components.json").write_text(
        json.dumps([c.to_dict() for c in components], indent=2)
    )
    (repo_dir / "edges.json").write_text(
        json.dumps([e.to_dict() for e in graph.edges], indent=2)
    )
    (repo_dir / "analysis_order.json").write_text(json.dumps(analysis_order, indent=2))

    result["status"] = "ok"
    result["component_count"] = len(components)
    result["edge_count"] = len(graph.edges)
    result["depth_levels"] = len(analysis_order)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("scripts/graph_audit/corpus.json"))
    parser.add_argument("--out-root", type=Path, default=Path("audit_out"))
    parser.add_argument("--limit", type=int, help="Only process first N repos (for dry runs)")
    parser.add_argument(
        "--max-components",
        type=int,
        default=100,
        help="Skip repos with more than this many components (too expensive to audit)",
    )
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text())
    if args.limit:
        corpus = corpus[: args.limit]

    args.out_root.mkdir(parents=True, exist_ok=True)
    summary = []
    for repo in corpus:
        print(f"\n[{repo['full_name']}] ({repo['language']})")
        result = run_for_repo(repo, args.out_root)
        if result.get("component_count", 0) > args.max_components:
            result["status"] = "too_many_components"
        print(f"  -> {result.get('status')} (components={result.get('component_count')}, edges={result.get('edge_count')})")
        summary.append(result)

    (args.out_root / "discovery_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote summary to {args.out_root / 'discovery_summary.json'}")


if __name__ == "__main__":
    main()
