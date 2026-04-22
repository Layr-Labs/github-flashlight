"""Post-analysis citation extractor.

Reads Markdown analysis files produced by code analyzer subagents,
extracts the structured ``## Citations`` JSON blocks, validates them,
and produces:

1. Per-component ``{component_name}.citations.json`` files in service_analyses/
2. An aggregated ``all_citations.json`` in service_analyses/ for RAG indexing

The extractor also enriches citations with deep links to the git forge
when ``source_repo`` and ``source_commit`` are available from the manifest.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.schemas.core import CodeCitation

logger = logging.getLogger(__name__)

# Pattern to match the ## Citations section and its fenced JSON block.
# We look for ``## Citations`` followed (possibly with intervening HTML comments
# or blank lines) by a ```json ... ``` fenced code block.
_CITATIONS_SECTION_RE = re.compile(
    r"^## Citations\b.*?"  # section heading
    r"```json\s*\n"  # opening fence
    r"(.*?)"  # captured JSON content (non-greedy)
    r"\n\s*```",  # closing fence
    re.MULTILINE | re.DOTALL,
)

# Patterns for stripping extracted JSON sections out of the Markdown once
# they've been lifted into sidecar files. Each pattern matches the full
# section (heading + fenced JSON block) so it can be removed wholesale.
# Anchored with ``\b`` on the heading keyword so ``## Analysis Summary`` is
# not caught by the ``## Analysis Data`` pattern.
_STRIP_CITATIONS_RE = re.compile(
    r"^## Citations\b[^\n]*\n.*?```json\s*\n.*?\n\s*```\s*\n?",
    re.MULTILINE | re.DOTALL,
)
_STRIP_ANALYSIS_DATA_RE = re.compile(
    r"^## Analysis Data\b[^\n]*\n.*?```json\s*\n.*?\n\s*```\s*\n?",
    re.MULTILINE | re.DOTALL,
)
# Collapse three-or-more consecutive blank lines left behind by the strips.
_COLLAPSE_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_extracted_sections(markdown_text: str) -> str:
    """Remove ``## Citations`` and ``## Analysis Data`` JSON blocks from Markdown.

    These sections are emitted by the component-analyzer for machine
    consumption, but the citations are lifted into a sidecar ``.citations.json``
    and ``## Analysis Data`` is never consumed downstream. Leaving them in the
    human-facing Markdown is just duplicated noise.

    This function is idempotent: running it twice on the same text produces
    the same result as running it once, so re-invoking the pipeline on an
    already-cleaned analysis file is a no-op.

    Args:
        markdown_text: Raw Markdown from a component analysis file.

    Returns:
        Markdown with the two JSON sections removed and trailing blank-line
        runs collapsed. Ends with a single trailing newline.
    """
    cleaned = _STRIP_CITATIONS_RE.sub("", markdown_text)
    cleaned = _STRIP_ANALYSIS_DATA_RE.sub("", cleaned)
    cleaned = _COLLAPSE_BLANK_LINES_RE.sub("\n\n", cleaned)
    # Normalise trailing whitespace to exactly one newline.
    return cleaned.rstrip() + "\n"


@dataclass
class ExtractionResult:
    """Result of extracting citations from a single Markdown file."""

    component_name: str
    source_file: str  # Path to the .md file
    citations: List[CodeCitation] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    raw_count: int = 0  # Citations found before validation

    @property
    def valid_count(self) -> int:
        return len(self.citations)


def extract_citations_from_markdown(
    markdown_text: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Extract raw citation dicts from a Markdown analysis file.

    Args:
        markdown_text: Full contents of a component analysis .md file.

    Returns:
        (raw_citation_dicts, errors) — the parsed JSON array and any errors encountered.
    """
    errors: List[str] = []

    match = _CITATIONS_SECTION_RE.search(markdown_text)
    if not match:
        errors.append("No ## Citations section with a ```json code block found")
        return [], errors

    json_text = match.group(1).strip()
    if not json_text:
        errors.append("## Citations JSON block is empty")
        return [], errors

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in ## Citations block: {exc}")
        return [], errors

    if not isinstance(data, list):
        errors.append(f"## Citations JSON must be an array, got {type(data).__name__}")
        return [], errors

    return data, errors


def validate_citation_dict(
    raw: Dict[str, Any],
    repo_root: Optional[Path] = None,
    component_root: Optional[str] = None,
) -> Tuple[Optional[CodeCitation], List[str]]:
    """Validate a single raw citation dict and convert to CodeCitation.

    Args:
        raw: A dict from the parsed JSON array.
        repo_root: Optional path to the source repository for file existence checks.
        component_root: Optional repo-root-relative path of the component whose
            analysis produced this citation (e.g. ``"omlx/models"``). Used as a
            fallback prefix when the LLM emits component-relative paths like
            ``"models/base_model.py"`` instead of repo-root-relative
            ``"omlx/models/base_model.py"``.

    Returns:
        (CodeCitation or None, list of error strings).
    """
    errors: List[str] = []

    file_path = raw.get("file_path", "")
    if not file_path:
        errors.append("Missing required field 'file_path'")

    start_line = raw.get("start_line", 0)
    end_line = raw.get("end_line", 0)

    if not isinstance(start_line, int) or start_line < 1:
        errors.append(f"Invalid start_line: {start_line} (must be positive integer)")
    if not isinstance(end_line, int) or end_line < 1:
        errors.append(f"Invalid end_line: {end_line} (must be positive integer)")
    if (
        isinstance(start_line, int)
        and isinstance(end_line, int)
        and end_line < start_line
    ):
        errors.append(f"end_line ({end_line}) < start_line ({start_line})")

    claim = raw.get("claim", "")
    if not claim:
        errors.append("Missing required field 'claim'")

    # Strip any /tmp/*/project/ prefix that agents sometimes include
    if file_path:
        # Match patterns like /tmp/my-service/project/src/... and strip prefix
        cleaned = re.sub(r"^/tmp/[^/]+/project/", "", file_path)
        if cleaned != file_path:
            logger.debug(
                "Stripped absolute prefix from citation path: %s -> %s",
                file_path,
                cleaned,
            )
            file_path = cleaned

    # Existence check with path-shape fallbacks. LLMs emit citation paths
    # in several shapes; we try the canonical one first, then fall back.
    if repo_root and file_path:
        normalised = file_path.lstrip("./").lstrip("/")

        candidate_paths: List[str] = [normalised]
        if component_root:
            root_parts = [
                p for p in component_root.strip("./").rstrip("/").split("/") if p
            ]
            file_parts = [p for p in normalised.split("/") if p]

            # Strategy A: dedupe trailing segments of component_root that
            # overlap with leading segments of file_path, then join. Handles
            # the common case where the LLM repeats the component's own
            # directory name:
            #   component_root = "omlx/models"
            #   file_path      = "models/base_model.py"
            #   -> merge to "omlx/models/base_model.py"
            for overlap in range(
                min(len(file_parts), len(root_parts)), 0, -1
            ):
                if root_parts[-overlap:] == file_parts[:overlap]:
                    merged = "/".join(root_parts + file_parts[overlap:])
                    if merged not in candidate_paths:
                        candidate_paths.append(merged)
                    break

            # Strategy B: straight prefix (no overlap). Handles the case
            # where the LLM wrote a bare filename:
            #   component_root = "omlx/models"
            #   file_path      = "base_model.py"
            #   -> "omlx/models/base_model.py"
            joined = "/".join(root_parts + file_parts) if root_parts else normalised
            if joined not in candidate_paths:
                candidate_paths.append(joined)

        resolved: Optional[str] = None
        for candidate in candidate_paths:
            if (repo_root / candidate).exists():
                resolved = candidate
                break

        if resolved is None:
            errors.append(f"Cited file does not exist: {file_path}")
        elif resolved != file_path:
            logger.debug(
                "Resolved citation path via fallback: %s -> %s",
                file_path,
                resolved,
            )
            file_path = resolved

    if errors:
        return None, errors

    return CodeCitation(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        claim=claim,
        section=raw.get("section", ""),
        snippet=raw.get("snippet", ""),
    ), []


def extract_component_citations(
    md_path: Path,
    component_name: str,
    repo_root: Optional[Path] = None,
    component_root: Optional[str] = None,
) -> ExtractionResult:
    """Extract and validate citations from a single component analysis Markdown file.

    Args:
        md_path: Path to the component's .md analysis file.
        component_name: Name of the component (for labeling).
        repo_root: Optional source repo path for file existence validation.
        component_root: Optional repo-root-relative path of this component
            (e.g. ``"omlx/models"``), used as a fallback path prefix when
            the LLM emits component-relative citation paths.

    Returns:
        ExtractionResult with validated citations and any errors.
    """
    result = ExtractionResult(
        component_name=component_name,
        source_file=str(md_path),
    )

    if not md_path.exists():
        result.errors.append(f"Analysis file not found: {md_path}")
        return result

    markdown_text = md_path.read_text(encoding="utf-8")
    raw_dicts, extract_errors = extract_citations_from_markdown(markdown_text)
    result.errors.extend(extract_errors)
    result.raw_count = len(raw_dicts)

    for i, raw in enumerate(raw_dicts):
        citation, val_errors = validate_citation_dict(
            raw, repo_root, component_root
        )
        if val_errors:
            for err in val_errors:
                result.errors.append(f"Citation [{i}]: {err}")
        if citation:
            result.citations.append(citation)

    return result


def build_citations_index(
    analyses_dir: Path,
    repo_root: Optional[Path] = None,
    source_repo: str = "",
    source_commit: str = "",
    component_roots: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Extract citations from all analysis Markdown files and produce an index.

    This is the main entry point for the citation extraction pipeline.

    Args:
        analyses_dir: Path to the service_analyses/ directory containing .md files.
        repo_root: Optional source repo path for file existence validation.
        source_repo: Repository URL for generating deep links.
        source_commit: Git commit hash for permalink stability.
        component_roots: Optional ``{component_name: root_path}`` map. When
            provided, a citation path that isn't valid at the repo root will
            be retried with the component's root_path as prefix. This
            recovers citations where the LLM wrote paths relative to the
            component directory (e.g. ``"base_model.py"`` for the ``models``
            component at ``omlx/models``).

    Returns:
        Dict suitable for writing as all_citations.json, containing:
        - metadata (source_repo, source_commit, timestamp, counts)
        - per-component citation arrays
        - aggregated flat list for RAG
    """
    from datetime import datetime, timezone

    results: List[ExtractionResult] = []
    component_roots = component_roots or {}

    # Find all .md analysis files (skip any .citations.json files)
    md_files = sorted(analyses_dir.glob("*.md"))

    for md_path in md_files:
        component_name = md_path.stem
        result = extract_component_citations(
            md_path,
            component_name,
            repo_root,
            component_root=component_roots.get(component_name),
        )
        results.append(result)

        # Write per-component citations file
        if result.citations:
            component_citations = {
                "component": component_name,
                "source_file": result.source_file,
                "source_repo": source_repo,
                "source_commit": source_commit,
                "citation_count": result.valid_count,
                "citations": [],
            }
            for c in result.citations:
                entry = c.to_dict()
                url = c.source_url(source_repo, source_commit)
                if url:
                    entry["source_url"] = url
                component_citations["citations"].append(entry)

            out_path = analyses_dir / f"{component_name}.citations.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(component_citations, f, indent=2)

            logger.info(
                "Extracted %d citations for %s (from %d raw)",
                result.valid_count,
                component_name,
                result.raw_count,
            )

            # Citations + analysis-data JSON blocks are now in the sidecar;
            # strip them from the Markdown so the human-facing analysis isn't
            # duplicating machine-readable artefacts. Guarded by the
            # successful-write branch so that files with malformed citation
            # blocks are left untouched for debugging.
            try:
                original = md_path.read_text(encoding="utf-8")
                stripped = strip_extracted_sections(original)
                if stripped != original:
                    md_path.write_text(stripped, encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "Could not strip extracted sections from %s: %s",
                    md_path,
                    exc,
                )

    # Build aggregated index
    total_valid = sum(r.valid_count for r in results)
    total_raw = sum(r.raw_count for r in results)
    total_errors = sum(len(r.errors) for r in results)
    components_with_citations = sum(1 for r in results if r.citations)
    components_without = sum(1 for r in results if not r.citations and r.raw_count == 0)

    # Flat list of all citations with component context (for RAG embedding)
    all_citations_flat: List[Dict[str, Any]] = []
    per_component: Dict[str, List[Dict[str, Any]]] = {}

    for result in results:
        component_entries = []
        for c in result.citations:
            entry = c.to_dict()
            entry["component"] = result.component_name
            url = c.source_url(source_repo, source_commit)
            if url:
                entry["source_url"] = url
            all_citations_flat.append(entry)
            component_entries.append(entry)
        if component_entries:
            per_component[result.component_name] = component_entries

    index = {
        "metadata": {
            "source_repo": source_repo,
            "source_commit": source_commit,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_citations": total_valid,
            "total_raw_parsed": total_raw,
            "total_validation_errors": total_errors,
            "components_with_citations": components_with_citations,
            "components_without_citations": components_without,
            "components_analyzed": len(results),
        },
        "by_component": per_component,
        "all_citations": all_citations_flat,
    }

    # Write aggregated index
    index_path = analyses_dir / "all_citations.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    # Log summary
    logger.info(
        "Citation extraction complete: %d valid citations across %d components "
        "(%d validation errors, %d components without citations)",
        total_valid,
        components_with_citations,
        total_errors,
        components_without,
    )

    # Log any errors for debugging
    for result in results:
        if result.errors:
            for err in result.errors:
                logger.warning("[%s] %s", result.component_name, err)

    return index
