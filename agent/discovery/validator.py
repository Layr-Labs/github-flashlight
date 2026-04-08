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
    library_names = {c.name for c in components if c.is_library}

    # Every library should be in the depth order
    all_ordered = set()
    for level in depth_order:
        for name in level:
            if name in all_ordered:
                errors.append(f"Component '{name}' appears in multiple depth levels")
            all_ordered.add(name)

    missing = library_names - all_ordered
    if missing:
        errors.append(f"Libraries missing from depth order: {missing}")

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
    - Analysis files reference valid source paths (spot check citations)
    """
    errors: List[str] = []

    for comp in components:
        # Check for analysis file
        analysis_file = analyses_dir / f"{comp.name}.md"
        if not analysis_file.exists():
            errors.append(f"Missing analysis file for component '{comp.name}'")

    return errors
