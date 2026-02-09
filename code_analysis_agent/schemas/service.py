"""Service data structure for discovered services."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path


@dataclass
class Service:
    """Represents a discovered service in the codebase."""

    name: str  # e.g., "auth-service"
    type: str  # e.g., "rust-crate", "python-package", "typescript-module"
    root_path: Path  # Absolute path to service root
    manifest_path: Optional[Path]  # Path to Cargo.toml, package.json, etc.
    description: str  # Brief description from manifest or README
    dependencies: List[str] = field(default_factory=list)  # Internal service dependencies
    external_dependencies: List[str] = field(default_factory=list)  # External deps
    key_files: List[Path] = field(default_factory=list)  # Important files
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra info

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "name": self.name,
            "type": self.type,
            "root_path": str(self.root_path),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "description": self.description,
            "dependencies": self.dependencies,
            "external_dependencies": self.external_dependencies,
            "key_files": [str(f) for f in self.key_files],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Service":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            type=data["type"],
            root_path=Path(data["root_path"]),
            manifest_path=Path(data["manifest_path"]) if data.get("manifest_path") else None,
            description=data["description"],
            dependencies=data.get("dependencies", []),
            external_dependencies=data.get("external_dependencies", []),
            key_files=[Path(f) for f in data.get("key_files", [])],
            metadata=data.get("metadata", {}),
        )
