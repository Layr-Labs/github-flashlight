"""Data structures for discovered applications and libraries."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path


@dataclass
class BaseComponent:
    """Base class for applications and libraries with common fields."""

    name: str  # e.g., "auth-service", "common-utils"
    type: str  # e.g., "rust-crate", "python-package", "typescript-module"
    root_path: Path  # Absolute path to component root
    manifest_path: Optional[Path]  # Path to Cargo.toml, package.json, etc.
    description: str  # Brief description from manifest or README
    external_dependencies: List[str] = field(default_factory=list)  # Third-party packages
    key_files: List[Path] = field(default_factory=list)  # Important files
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra info


@dataclass
class Application(BaseComponent):
    """Represents an executable application with an entrypoint and business purpose.

    Applications are deployable systems that use libraries and interact with other applications.
    Examples: web servers, CLI tools, background workers, APIs.
    """

    libraries_used: List[str] = field(default_factory=list)  # Internal libraries this application uses
    application_interactions: List[Dict[str, str]] = field(default_factory=list)  # How this app interacts with other apps
    # application_interactions format: [{"target": "api-service", "type": "http_api", "description": "Calls /users endpoint"}]
    third_party_applications: List[Dict[str, str]] = field(default_factory=list)  # External services/APIs this app integrates with
    # third_party_applications format: [{"name": "AWS S3", "type": "object_storage", "description": "Stores user uploads", "integration_method": "AWS SDK"}]

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "name": self.name,
            "type": self.type,
            "classification": "application",
            "root_path": str(self.root_path),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "description": self.description,
            "external_dependencies": self.external_dependencies,
            "libraries_used": self.libraries_used,
            "application_interactions": self.application_interactions,
            "third_party_applications": self.third_party_applications,
            "key_files": [str(f) for f in self.key_files],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Application":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            type=data["type"],
            root_path=Path(data["root_path"]),
            manifest_path=Path(data["manifest_path"]) if data.get("manifest_path") else None,
            description=data["description"],
            external_dependencies=data.get("external_dependencies", []),
            libraries_used=data.get("libraries_used", []),
            application_interactions=data.get("application_interactions", []),
            third_party_applications=data.get("third_party_applications", []),
            key_files=[Path(f) for f in data.get("key_files", [])],
            metadata=data.get("metadata", {}),
        )


@dataclass
class Library(BaseComponent):
    """Represents a reusable library/package without an entrypoint.

    Libraries provide shared code and utilities consumed by applications and other libraries.
    Examples: utility libraries, data models, shared business logic.
    """

    dependencies: List[str] = field(default_factory=list)  # Other internal libraries this depends on

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "name": self.name,
            "type": self.type,
            "classification": "library",
            "root_path": str(self.root_path),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "description": self.description,
            "external_dependencies": self.external_dependencies,
            "dependencies": self.dependencies,
            "key_files": [str(f) for f in self.key_files],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Library":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            type=data["type"],
            root_path=Path(data["root_path"]),
            manifest_path=Path(data["manifest_path"]) if data.get("manifest_path") else None,
            description=data["description"],
            external_dependencies=data.get("external_dependencies", []),
            dependencies=data.get("dependencies", []),
            key_files=[Path(f) for f in data.get("key_files", [])],
            metadata=data.get("metadata", {}),
        )


# Backward compatibility alias
Service = Application | Library


def component_from_dict(data: dict) -> Application | Library:
    """Factory function to deserialize into appropriate type based on classification."""
    classification = data.get("classification", "library")
    if classification == "application":
        return Application.from_dict(data)
    else:
        return Library.from_dict(data)
