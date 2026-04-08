"""Artifact manifest schema for versioning and tracking generated analysis artifacts."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Bump this when the manifest schema itself changes
MANIFEST_SCHEMA_VERSION = "1.0.0"


@dataclass
class ArtifactFile:
    """Metadata for a single file in the artifact set."""

    path: str  # Relative path from service root (e.g., "service_analyses/core.md")
    size_bytes: int  # File size in bytes
    sha256: str  # SHA-256 hex digest of file contents
    category: str = ""  # File category: discovery, graph, analysis, architecture

    def to_dict(self) -> dict:
        d = {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }
        if self.category:
            d["category"] = self.category
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactFile":
        return cls(
            path=data["path"],
            size_bytes=data.get("size_bytes", 0),
            sha256=data.get("sha256", ""),
            category=data.get("category", ""),
        )

    @classmethod
    def from_path(cls, file_path: Path, root_dir: Path, category: str = "") -> "ArtifactFile":
        """Create an ArtifactFile by reading from disk.

        Args:
            file_path: Absolute path to the file.
            root_dir: The service root directory (for computing relative paths).
            category: File category label.
        """
        content = file_path.read_bytes()
        rel_path = str(file_path.relative_to(root_dir))
        return cls(
            path=rel_path,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            category=category,
        )


@dataclass
class ArtifactManifest:
    """Versioned manifest for a service's generated analysis artifacts.

    Written to `manifest.json` at the root of each service's artifact directory.
    Provides:
    - Monotonic artifact version number (incremented on each re-analysis)
    - Generation metadata (timestamp, model, prompt versions)
    - Complete file inventory with checksums for integrity verification
    - Schema version for forward compatibility
    """

    # Identity
    service_name: str  # Name of the analyzed service/repo
    artifact_version: int  # Monotonic version number (1, 2, 3, ...)

    # Generation metadata
    generated_at: str  # ISO 8601 timestamp of generation
    model: str = ""  # Model used for analysis (e.g., "claude-sonnet-4-20250514")
    generator: str = "github-flashlight"  # Tool that produced this artifact set
    schema_version: str = MANIFEST_SCHEMA_VERSION  # Manifest schema version

    # Source info
    source_repo: str = ""  # URL or path of the analyzed repository
    source_commit: str = ""  # Git commit hash of the analyzed source (if available)

    # Content summary
    libraries_count: int = 0  # Number of libraries analyzed
    applications_count: int = 0  # Number of applications analyzed
    total_files: int = 0  # Total artifact files in this version

    # File inventory
    files: List[ArtifactFile] = field(default_factory=list)

    # Extensible metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "service_name": self.service_name,
            "artifact_version": self.artifact_version,
            "generated_at": self.generated_at,
            "model": self.model,
            "generator": self.generator,
            "schema_version": self.schema_version,
            "source_repo": self.source_repo,
            "source_commit": self.source_commit,
            "libraries_count": self.libraries_count,
            "applications_count": self.applications_count,
            "total_files": self.total_files,
            "files": [f.to_dict() for f in self.files],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactManifest":
        return cls(
            service_name=data["service_name"],
            artifact_version=data["artifact_version"],
            generated_at=data.get("generated_at", ""),
            model=data.get("model", ""),
            generator=data.get("generator", "github-flashlight"),
            schema_version=data.get("schema_version", MANIFEST_SCHEMA_VERSION),
            source_repo=data.get("source_repo", ""),
            source_commit=data.get("source_commit", ""),
            libraries_count=data.get("libraries_count", 0),
            applications_count=data.get("applications_count", 0),
            total_files=data.get("total_files", 0),
            files=[ArtifactFile.from_dict(f) for f in data.get("files", [])],
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ArtifactManifest":
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def create_initial(
        cls,
        service_name: str,
        source_repo: str = "",
        source_commit: str = "",
        model: str = "",
    ) -> "ArtifactManifest":
        """Create a new v1 manifest for a fresh analysis run."""
        return cls(
            service_name=service_name,
            artifact_version=1,
            generated_at=datetime.now(timezone.utc).isoformat(),
            model=model,
            source_repo=source_repo,
            source_commit=source_commit,
        )

    @classmethod
    def create_next_version(
        cls,
        previous: "ArtifactManifest",
        source_commit: str = "",
        model: str = "",
    ) -> "ArtifactManifest":
        """Create a manifest for a re-analysis, incrementing the version."""
        return cls(
            service_name=previous.service_name,
            artifact_version=previous.artifact_version + 1,
            generated_at=datetime.now(timezone.utc).isoformat(),
            model=model or previous.model,
            source_repo=previous.source_repo,
            source_commit=source_commit or previous.source_commit,
        )

    def scan_directory(self, root_dir: Path) -> None:
        """Scan a service artifact directory and populate the file inventory.

        Args:
            root_dir: The service root directory to scan.
        """
        self.files = []

        # Category mapping by subdirectory
        category_map = {
            "service_discovery": "discovery",
            "dependency_graphs": "graph",
            "service_analyses": "analysis",
            "architecture_docs": "architecture",
        }

        for file_path in sorted(root_dir.rglob("*")):
            if not file_path.is_file():
                continue
            # Skip non-artifact files
            if file_path.name == "manifest.json":
                continue
            if file_path.suffix not in (".md", ".json"):
                continue

            # Determine category from parent directory
            rel = file_path.relative_to(root_dir)
            category = ""
            for dir_name, cat in category_map.items():
                if rel.parts and rel.parts[0] == dir_name:
                    category = cat
                    break

            self.files.append(
                ArtifactFile.from_path(file_path, root_dir, category=category)
            )

        self.total_files = len(self.files)
