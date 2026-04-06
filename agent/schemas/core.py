"""Data structures for discovered applications and libraries."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path


@dataclass
class ExternalDependency:
    """Represents a third-party dependency with structured metadata."""

    name: str  # Package name (e.g., "tokio", "express", "serde")
    version: str = ""  # Version constraint (e.g., "1.35", "^4.18.0")
    category: str = (
        ""  # Category: web-framework, database, serialization, async-runtime, etc.
    )
    purpose: str = ""  # Brief description of why this dependency is used

    def to_dict(self) -> dict:
        d = {"name": self.name}
        if self.version:
            d["version"] = self.version
        if self.category:
            d["category"] = self.category
        if self.purpose:
            d["purpose"] = self.purpose
        return d

    @classmethod
    def from_dict(cls, data) -> "ExternalDependency":
        """Deserialize from dict or string (backward compat)."""
        if isinstance(data, str):
            return cls(name=data)
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            category=data.get("category", ""),
            purpose=data.get("purpose", ""),
        )


@dataclass
class BaseComponent:
    """Base class for applications and libraries with common fields."""

    name: str  # e.g., "auth-service", "common-utils"
    type: str  # e.g., "rust-crate", "python-package", "typescript-module"
    root_path: Path  # Absolute path to component root
    manifest_path: Optional[Path] = None  # Path to Cargo.toml, package.json, etc.
    description: str = ""  # Brief description from manifest or README
    key_files: List[Path] = field(default_factory=list)  # Important files
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra info


@dataclass
class Library(BaseComponent):
    """Represents a reusable library/package without an entrypoint.

    Libraries provide shared code and utilities consumed by applications and other libraries.
    Examples: utility libraries, data models, shared business logic.
    """

    external_dependencies: List[ExternalDependency] = field(
        default_factory=list
    )  # Third-party packages
    internal_dependencies: List[str] = field(
        default_factory=list
    )  # Other internal libraries this depends on

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "name": self.name,
            "type": self.type,
            "classification": "library",
            "root_path": str(self.root_path),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "description": self.description,
            "external_dependencies": [
                d.to_dict() if isinstance(d, ExternalDependency) else d
                for d in self.external_dependencies
            ],
            "internal_dependencies": self.internal_dependencies,
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
            manifest_path=Path(data["manifest_path"])
            if data.get("manifest_path")
            else None,
            description=data.get("description", ""),
            external_dependencies=[
                ExternalDependency.from_dict(d)
                for d in data.get("external_dependencies", [])
            ],
            internal_dependencies=data.get("internal_dependencies", []),
            key_files=[Path(f) for f in data.get("key_files", [])],
            metadata=data.get("metadata", {}),
        )


@dataclass
class Application(BaseComponent):
    """Represents an executable application with an entrypoint and business purpose.

    Applications are deployable systems that use libraries and interact with other applications.
    Examples: web servers, CLI tools, background workers, APIs.
    """

    external_dependencies: List[ExternalDependency] = field(
        default_factory=list
    )  # Third-party packages
    libraries_used: List[str] = field(
        default_factory=list
    )  # Internal libraries this application uses
    internal_applications: List[str] = field(
        default_factory=list
    )  # Other internal apps this one interacts with

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        return {
            "name": self.name,
            "type": self.type,
            "classification": "application",
            "root_path": str(self.root_path),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "description": self.description,
            "external_dependencies": [
                d.to_dict() if isinstance(d, ExternalDependency) else d
                for d in self.external_dependencies
            ],
            "libraries_used": self.libraries_used,
            "internal_applications": self.internal_applications,
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
            manifest_path=Path(data["manifest_path"])
            if data.get("manifest_path")
            else None,
            description=data.get("description", ""),
            external_dependencies=[
                ExternalDependency.from_dict(d)
                for d in data.get("external_dependencies", [])
            ],
            libraries_used=data.get("libraries_used", []),
            internal_applications=data.get("internal_applications", []),
            key_files=[Path(f) for f in data.get("key_files", [])],
            metadata=data.get("metadata", {}),
        )


# Backward compatibility alias
KnowledgeBasis = Application | Library


def component_from_dict(data: dict) -> Application | Library:
    """Factory function to deserialize into appropriate type based on classification."""
    classification = data.get("classification", "library")
    if classification == "application":
        return Application.from_dict(data)
    else:
        return Library.from_dict(data)
