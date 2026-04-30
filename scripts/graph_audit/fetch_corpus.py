"""Fetch a stratified corpus of GitHub repos for graph auditing.

Uses GitHub's search API (requires `gh` CLI authenticated) to pull
popular + recently active repos per language. Writes corpus.json with
clone URLs; actual cloning happens in run_discovery.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


LANGUAGES = {
    "rust": "Rust",
    "go": "Go",
    "typescript": "TypeScript",
    "python": "Python",
    "solidity": "Solidity",
}


def fetch_top_repos(language: str, per_lang: int) -> list[dict]:
    """Popular + recently active repos for one language via `gh api`."""
    query = f"language:{language} stars:>500 pushed:>2026-01-01"
    cmd = [
        "gh",
        "api",
        "-X",
        "GET",
        "search/repositories",
        "-f",
        f"q={query}",
        "-f",
        "sort=stars",
        "-f",
        "order=desc",
        "-f",
        f"per_page={per_lang}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return [
        {
            "language": language,
            "full_name": item["full_name"],
            "clone_url": item["clone_url"],
            "stars": item["stargazers_count"],
            "size_kb": item["size"],
        }
        for item in data["items"]
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--per-lang",
        type=int,
        default=4,
        help="Repos to fetch per language (default 4, yielding 20 total across 5 langs)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scripts/graph_audit/corpus.json"),
    )
    parser.add_argument(
        "--max-size-kb",
        type=int,
        default=200_000,
        help="Skip repos larger than this (avoid multi-GB monorepos)",
    )
    args = parser.parse_args()

    corpus: list[dict] = []
    for lang_key, lang_name in LANGUAGES.items():
        print(f"Fetching {args.per_lang} repos for {lang_name}...")
        try:
            repos = fetch_top_repos(lang_name, args.per_lang * 2)
        except subprocess.CalledProcessError as e:
            print(f"  FAILED for {lang_name}: {e.stderr}")
            continue

        kept = 0
        for repo in repos:
            if repo["size_kb"] > args.max_size_kb:
                print(f"  SKIP (too large): {repo['full_name']} ({repo['size_kb']} KB)")
                continue
            corpus.append(repo)
            kept += 1
            if kept >= args.per_lang:
                break

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(corpus, indent=2))
    print(f"\nWrote {len(corpus)} repos to {args.output}")


if __name__ == "__main__":
    main()
