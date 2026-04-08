"""Abstract base class for language discovery plugins."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from agent.schemas.core import Component


class LanguagePlugin(ABC):
    """Interface for language-specific component discovery.

    Each plugin knows:
    - What manifest files to look for (e.g., go.mod, Cargo.toml)
    - How to parse them to extract name, dependencies, classification
    - How to distinguish libraries from executables in its ecosystem
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name (e.g., 'Go', 'Python')."""
        ...

    @property
    @abstractmethod
    def manifest_patterns(self) -> List[str]:
        """Glob patterns for manifest files (e.g., ['**/go.mod'])."""
        ...

    @property
    @abstractmethod
    def exclude_patterns(self) -> List[str]:
        """Glob patterns to exclude (e.g., ['**/vendor/**', '**/node_modules/**'])."""
        ...

    @abstractmethod
    def parse_manifest(self, manifest_path: Path, repo_root: Path) -> List[Component]:
        """Parse a manifest file and return discovered components.

        A single manifest may yield multiple components (e.g., a Cargo
        workspace with multiple crates).

        Args:
            manifest_path: Absolute path to the manifest file.
            repo_root: Absolute path to the repository root.

        Returns:
            List of Component objects discovered from this manifest.
        """
        ...

    def should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded from discovery."""
        path_str = str(path)
        for pattern in self.exclude_patterns:
            # Simple substring check for common exclusions
            exclude_dir = pattern.replace("**/", "").replace("/**", "")
            if exclude_dir in path_str:
                return True
        return False
