"""Discovery engine: scans a repository and produces a component inventory.

This replaces the LLM-driven discovery in the lead agent prompt.
Runs in seconds with zero LLM calls.
"""

import json
import logging
from pathlib import Path
from typing import List

from agent.schemas.core import Component, ComponentKind
from .languages import ALL_PLUGINS
from .validator import validate_discovery

logger = logging.getLogger(__name__)


def discover_components(
    repo_root: Path,
    output_dir: Path | None = None,
) -> List[Component]:
    """Scan a repository and discover all components.

    Args:
        repo_root: Absolute path to the repository root.
        output_dir: If provided, write components.json to this directory.

    Returns:
        List of discovered Component objects.
    """
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError(f"Repository root not found: {repo_root}")

    all_components: List[Component] = []
    seen_roots: set[str] = set()

    for plugin in ALL_PLUGINS:
        for pattern in plugin.manifest_patterns:
            for manifest_path in sorted(repo_root.glob(pattern)):
                # Skip excluded paths
                if plugin.should_exclude(manifest_path):
                    continue

                try:
                    components = plugin.parse_manifest(manifest_path, repo_root)
                except Exception as e:
                    logger.warning(
                        "Failed to parse %s with %s plugin: %s",
                        manifest_path, plugin.name, e,
                    )
                    continue

                for comp in components:
                    # Deduplicate by root_path
                    if comp.root_path in seen_roots:
                        continue
                    seen_roots.add(comp.root_path)
                    all_components.append(comp)

        logger.info(
            "%s plugin: found %d manifests",
            plugin.name,
            sum(1 for c in all_components if plugin.name.lower() in c.type),
        )

    # Resolve cross-references: internal dependencies should reference
    # component names, not paths
    _resolve_internal_deps(all_components)

    # Detect repo shape
    shape = _detect_repo_shape(all_components)
    logger.info("Repo shape: %s (%d components)", shape, len(all_components))

    # Validate
    errors = validate_discovery(all_components, repo_root)
    for err in errors:
        logger.warning("Discovery validation: %s", err)

    # Write output
    if output_dir:
        _write_output(all_components, output_dir)

    return all_components


def _resolve_internal_deps(components: List[Component]) -> None:
    """Ensure internal_dependencies reference component names, not paths."""
    name_set = {c.name for c in components}
    root_to_name = {c.root_path: c.name for c in components}

    for comp in components:
        resolved = []
        for dep in comp.internal_dependencies:
            if dep in name_set:
                resolved.append(dep)
            elif dep in root_to_name:
                resolved.append(root_to_name[dep])
            else:
                # Try partial match (e.g., "common" might match "my-common")
                matches = [n for n in name_set if dep in n or n in dep]
                if len(matches) == 1:
                    resolved.append(matches[0])
                else:
                    logger.debug(
                        "Could not resolve internal dep '%s' for %s",
                        dep, comp.name,
                    )
        comp.internal_dependencies = resolved


def _detect_repo_shape(components: List[Component]) -> str:
    """Classify the repository shape."""
    if len(components) == 0:
        return "empty"
    if len(components) == 1:
        return "single-package"

    languages = {c.type for c in components}
    if len(languages) > 1:
        return "polyglot-monorepo"

    return "monorepo"


def _write_output(components: List[Component], output_dir: Path) -> None:
    """Write components.json in the standard format."""
    output_dir.mkdir(parents=True, exist_ok=True)

    libraries = [c for c in components if c.kind == ComponentKind.LIBRARY]
    executables = [c for c in components if c.kind != ComponentKind.LIBRARY]

    output = {
        "libraries": [c.to_dict() for c in libraries],
        "applications": [c.to_dict() for c in executables],
        "metadata": {
            "total_components": len(components),
            "by_kind": {
                kind.value: sum(1 for c in components if c.kind == kind)
                for kind in ComponentKind
                if any(c.kind == kind for c in components)
            },
            "by_language": {
                lang: sum(1 for c in components if c.type == lang)
                for lang in sorted({c.type for c in components})
            },
        },
    }

    # Write combined components.json
    with open(output_dir / "components.json", "w") as f:
        json.dump(output, f, indent=2)

    # Also write separate files for backward compat
    with open(output_dir / "libraries.json", "w") as f:
        json.dump({"libraries": [c.to_dict() for c in libraries]}, f, indent=2)

    with open(output_dir / "applications.json", "w") as f:
        json.dump({"applications": [c.to_dict() for c in executables]}, f, indent=2)

    logger.info(
        "Wrote %d components to %s (%d libraries, %d executables)",
        len(components), output_dir, len(libraries), len(executables),
    )
