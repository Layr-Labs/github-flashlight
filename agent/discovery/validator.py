"""Validation gates between pipeline stages.

Each validator returns a list of error strings. Empty list = valid.
"""

import logging
from pathlib import Path
from typing import List

from agent.schemas.core import Component

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when validation fails with fatal errors."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s): {errors[0]}")


def validate_discovery(
    components: List[Component],
    repo_root: Path,
) -> List[str]:
    """Validate discovery output before graph building.

    Checks:
    - No duplicate component names
    - All root_paths exist in the repo
    - All internal dependency references resolve to known components
    - No self-dependencies
    """
    errors: List[str] = []
    names: dict[str, int] = {}

    for comp in components:
        # Duplicate names
        if comp.name in names:
            errors.append(
                f"Duplicate component name '{comp.name}' "
                f"(roots: {components[names[comp.name]].root_path}, {comp.root_path})"
            )
        names[comp.name] = len(names)

        # Root path exists
        root = repo_root / comp.root_path if comp.root_path else repo_root
        if not root.exists():
            errors.append(
                f"Component '{comp.name}' root_path does not exist: {comp.root_path}"
            )

        # Self-dependency
        if comp.name in comp.internal_dependencies:
            errors.append(f"Component '{comp.name}' depends on itself")

    # Internal deps resolve
    name_set = {c.name for c in components}
    for comp in components:
        for dep in comp.internal_dependencies:
            if dep not in name_set:
                errors.append(
                    f"Component '{comp.name}' has unresolved internal dependency: '{dep}'"
                )

    return errors


def validate_graph(
    components: List[Component],
    depth_order: List[List[str]],
) -> List[str]:
    """Validate dependency graph after building.

    Checks:
    - Every component appears in exactly one depth level
    - Topological ordering is valid (no dep on a later depth)
    - No cycles detected (would have failed topological sort)
    """
    errors: List[str] = []
    name_set = {c.name for c in components}

    # Every component should appear in exactly one depth level
    all_ordered = set()
    for level in depth_order:
        for name in level:
            if name in all_ordered:
                errors.append(f"Component '{name}' appears in multiple depth levels")
            all_ordered.add(name)

    missing = name_set - all_ordered
    if missing:
        errors.append(f"Components missing from depth order: {missing}")

    # Validate topological property: for each component at depth N,
    # all its dependencies should be at depth < N
    depth_map: dict[str, int] = {}
    for depth, level in enumerate(depth_order):
        for name in level:
            depth_map[name] = depth

    dep_map = {c.name: c.internal_dependencies for c in components}
    for name, depth in depth_map.items():
        for dep in dep_map.get(name, []):
            if dep in depth_map and depth_map[dep] >= depth:
                errors.append(
                    f"Topological violation: '{name}' (depth {depth}) "
                    f"depends on '{dep}' (depth {depth_map[dep]})"
                )

    return errors


def validate_analysis(
    components: List[Component],
    analyses_dir: Path,
    repo_root: Path,
) -> List[str]:
    """Validate post-analysis output.

    Checks:
    - Every component has a corresponding analysis .md file
    - Analysis files contain a ## Citations section with valid JSON
    - Cited files exist in the repository (spot check)
    - Cited line ranges are plausible (start <= end, within file length)
    """
    errors: List[str] = []

    for comp in components:
        # Check for analysis file
        analysis_file = analyses_dir / f"{comp.name}.md"
        if not analysis_file.exists():
            errors.append(f"Missing analysis file for component '{comp.name}'")
            continue

        # Spot-check citations
        citation_errors = _validate_citations_in_file(
            analysis_file, comp.name, repo_root
        )
        errors.extend(citation_errors)

    return errors


def _validate_citations_in_file(
    md_path: Path,
    component_name: str,
    repo_root: Path,
    max_spot_checks: int = 5,
) -> List[str]:
    """Validate citations embedded in a Markdown analysis file.

    Performs lightweight checks:
    - ## Citations section exists
    - JSON is parseable
    - Spot-checks up to max_spot_checks citations for file existence and line plausibility.
    """
    import json
    import re

    errors: List[str] = []
    text = md_path.read_text(encoding="utf-8")

    # Look for ## Citations + ```json block
    pattern = re.compile(
        r"^## Citations\b.*?```json\s*\n(.*?)\n\s*```",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        errors.append(
            f"[{component_name}] Missing ## Citations section with JSON block"
        )
        return errors

    json_text = match.group(1).strip()
    if not json_text:
        errors.append(f"[{component_name}] ## Citations JSON block is empty")
        return errors

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        errors.append(f"[{component_name}] Invalid JSON in ## Citations: {exc}")
        return errors

    if not isinstance(data, list):
        errors.append(
            f"[{component_name}] ## Citations must be a JSON array, got {type(data).__name__}"
        )
        return errors

    if len(data) == 0:
        errors.append(f"[{component_name}] ## Citations array is empty (expected 10+)")
        return errors

    # Spot-check a sample of citations
    import random

    sample = (
        data[:max_spot_checks]
        if len(data) <= max_spot_checks
        else random.sample(data, max_spot_checks)
    )

    for i, cite in enumerate(sample):
        file_path = cite.get("file_path", "")
        start_line = cite.get("start_line", 0)
        end_line = cite.get("end_line", 0)

        if not file_path:
            errors.append(f"[{component_name}] Citation [{i}] missing file_path")
            continue

        # Strip /tmp/*/project/ prefix if present
        cleaned = re.sub(r"^/tmp/[^/]+/project/", "", file_path)

        full_path = repo_root / cleaned
        if not full_path.exists():
            errors.append(f"[{component_name}] Citation file not found: {cleaned}")
            continue

        # Check line plausibility
        if isinstance(start_line, int) and isinstance(end_line, int):
            if start_line < 1 or end_line < start_line:
                errors.append(
                    f"[{component_name}] Invalid line range {start_line}-{end_line} "
                    f"in {cleaned}"
                )
            else:
                # Check against actual file length
                try:
                    line_count = sum(
                        1 for _ in open(full_path, encoding="utf-8", errors="replace")
                    )
                    if start_line > line_count:
                        errors.append(
                            f"[{component_name}] Citation start_line {start_line} > "
                            f"file length {line_count} in {cleaned}"
                        )
                except OSError:
                    pass  # Skip if we can't read the file

    return errors
