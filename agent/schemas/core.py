"""Data structures for discovered components.

Provides a unified Component type with a pluggable ComponentKind taxonomy,
replacing the previous binary Library/Application split. The old types are
preserved as backward-compatible aliases.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from pathlib import Path


# ---------------------------------------------------------------------------
# Component taxonomy
# ---------------------------------------------------------------------------


class ComponentKind(str, Enum):
    """Classification of a component's role in the codebase.

    Deterministic classification is handled by the discovery engine;
    UNKNOWN components are classified later by LLM analysis.
    """

    LIBRARY = "library"  # Reusable code, no entrypoint
    SERVICE = "service"  # Long-running process (HTTP, gRPC, daemon)
    CLI = "cli"  # Command-line tool
    CONTRACT = "contract"  # Smart contract, API definition, schema
    INFRA = "infra"  # IaC, deployment config (Terraform, Helm, K8s)
    PIPELINE = "pipeline"  # Data pipeline, workflow definition (Airflow, dbt)
    FRONTEND = "frontend"  # UI application (React, Vue, etc.)
    UNKNOWN = "unknown"  # Could not classify deterministically

    @classmethod
    def from_str(cls, value: str) -> "ComponentKind":
        """Parse from string, falling back to UNKNOWN."""
        try:
            return cls(value.lower())
        except ValueError:
            # Backward compat: map old "application" to SERVICE
            if value.lower() == "application":
                return cls.SERVICE
            return cls.UNKNOWN


class LanguageType(str, Enum):
    """Language ecosystem of a component."""

    GO = "go-module"
    RUST = "rust-crate"
    PYTHON = "python-package"
    TYPESCRIPT = "typescript-package"
    JAVASCRIPT = "javascript-package"
    JAVA = "java-package"
    KOTLIN = "kotlin-package"
    SOLIDITY = "solidity-contract"
    TERRAFORM = "terraform-module"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Supporting types (unchanged)
# ---------------------------------------------------------------------------


@dataclass
class CodeCitation:
    """Represents a traceable link from an analysis claim to a specific source code location.

    Code citations provide provenance for analysis findings, linking each claim
    or observation back to the exact file and line range where it was observed.
    This enables RAG systems to return verifiable, clickable references alongside
    analysis prose.
    """

    file_path: str  # Relative path from repo root (e.g., "src/auth/handler.rs")
    start_line: int  # Starting line number (1-indexed)
    end_line: int  # Ending line number (inclusive)
    claim: str  # The analysis finding this citation supports
    section: str = ""  # Which analysis section this belongs to
    snippet: str = ""  # Optional: the relevant code excerpt (kept short)

    def to_dict(self) -> dict:
        d = {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "claim": self.claim,
        }
        if self.section:
            d["section"] = self.section
        if self.snippet:
            d["snippet"] = self.snippet
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CodeCitation":
        return cls(
            file_path=data.get("file_path", ""),
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            claim=data.get("claim", ""),
            section=data.get("section", ""),
            snippet=data.get("snippet", ""),
        )

    def to_markdown(self) -> str:
        if self.start_line == self.end_line:
            return f"`{self.file_path}:{self.start_line}`"
        return f"`{self.file_path}:{self.start_line}-{self.end_line}`"

    def to_markdown_link(self, source_url: str = "", commit: str = "") -> str:
        """Render as a clickable markdown link if source_url is available.

        Args:
            source_url: Base URL of the repository (e.g., "https://github.com/org/repo").
            commit: Git commit hash for permalink stability.

        Returns:
            Markdown link like ``[`file.rs:10-20`](https://github.com/org/repo/blob/abc123/file.rs#L10-L20)``
            or plain ``file.rs:10-20`` if no source_url is provided.
        """
        label = self.to_markdown()
        url = self.source_url(source_url, commit)
        if url:
            return f"[{label}]({url})"
        return label

    def source_url(self, base_url: str = "", commit: str = "") -> str:
        """Compose a deep link to the exact source location on a git forge.

        Supports GitHub, GitLab, and Bitbucket URL conventions.

        Args:
            base_url: Repository URL (e.g., "https://github.com/org/repo").
                      Trailing slashes are stripped automatically.
            commit: Git commit SHA for permalinks. Falls back to "HEAD" if empty.

        Returns:
            Full URL with line anchors, or empty string if base_url is empty.
        """
        if not base_url:
            return ""

        base = base_url.rstrip("/")
        ref = commit or "HEAD"

        # Detect forge type from URL
        if "gitlab" in base.lower():
            # GitLab: /blob/{ref}/{path}#L{start}-{end}
            line_anchor = f"#L{self.start_line}-{self.end_line}"
        elif "bitbucket" in base.lower():
            # Bitbucket: /src/{ref}/{path}#lines-{start}:{end}
            return f"{base}/src/{ref}/{self.file_path}#lines-{self.start_line}:{self.end_line}"
        else:
            # GitHub (default): /blob/{ref}/{path}#L{start}-L{end}
            if self.start_line == self.end_line:
                line_anchor = f"#L{self.start_line}"
            else:
                line_anchor = f"#L{self.start_line}-L{self.end_line}"

        return f"{base}/blob/{ref}/{self.file_path}{line_anchor}"


@dataclass
class ExternalDependency:
    """Represents a third-party dependency with structured metadata."""

    name: str
    version: str = ""
    category: str = ""
    purpose: str = ""

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
        if isinstance(data, str):
            return cls(name=data)
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            category=data.get("category", ""),
            purpose=data.get("purpose", ""),
        )


# ---------------------------------------------------------------------------
# Unified Component
# ---------------------------------------------------------------------------


@dataclass
class Component:
    """A single component in a codebase.

    Replaces the old Library/Application split with a unified type and a
    ComponentKind enum for classification. All discovery, graph building,
    and analysis operate on Components.
    """

    name: str
    kind: ComponentKind
    type: str  # Language ecosystem (e.g., "go-module", "python-package")
    root_path: str  # Relative path from repo root
    manifest_path: str = ""  # Relative path to manifest file
    description: str = ""
    internal_dependencies: List[str] = field(default_factory=list)
    external_dependencies: List[ExternalDependency] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    citations: List[CodeCitation] = field(default_factory=list)

    # Backward-compat fields (populated from old Library/Application data)
    libraries_used: List[str] = field(default_factory=list)
    internal_applications: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary. Output is backward-compatible with old format."""
        d: dict = {
            "name": self.name,
            "kind": self.kind.value,
            "type": self.type,
            "classification": self._legacy_classification(),
            "root_path": self.root_path,
            "description": self.description,
            "internal_dependencies": self.internal_dependencies,
            "external_dependencies": [
                dep.to_dict() if isinstance(dep, ExternalDependency) else dep
                for dep in self.external_dependencies
            ],
            "key_files": self.key_files,
        }
        if self.manifest_path:
            d["manifest_path"] = self.manifest_path
        if self.metadata:
            d["metadata"] = self.metadata
        if self.citations:
            d["citations"] = [c.to_dict() for c in self.citations]
        # Legacy fields for backward compat
        if self.libraries_used:
            d["libraries_used"] = self.libraries_used
        if self.internal_applications:
            d["internal_applications"] = self.internal_applications
        return d

    def _legacy_classification(self) -> str:
        """Map ComponentKind to old 'library'/'application' for backward compat."""
        if self.kind == ComponentKind.LIBRARY:
            return "library"
        return "application"

    @classmethod
    def from_dict(cls, data: dict) -> "Component":
        """Deserialize from dictionary. Handles both new and old formats."""
        # Determine kind: prefer new 'kind' field, fall back to 'classification'
        if "kind" in data:
            kind = ComponentKind.from_str(data["kind"])
        elif "classification" in data:
            kind = ComponentKind.from_str(data["classification"])
        else:
            kind = ComponentKind.UNKNOWN

        return cls(
            name=data["name"],
            kind=kind,
            type=data.get("type", "unknown"),
            root_path=data.get("root_path", ""),
            manifest_path=data.get("manifest_path", ""),
            description=data.get("description", ""),
            internal_dependencies=data.get("internal_dependencies", []),
            external_dependencies=[
                ExternalDependency.from_dict(d)
                for d in data.get("external_dependencies", [])
            ],
            key_files=data.get("key_files", []),
            metadata=data.get("metadata", {}),
            citations=[CodeCitation.from_dict(c) for c in data.get("citations", [])],
            libraries_used=data.get("libraries_used", []),
            internal_applications=data.get("internal_applications", []),
        )

    @property
    def is_library(self) -> bool:
        return self.kind == ComponentKind.LIBRARY

    @property
    def is_executable(self) -> bool:
        return self.kind in (
            ComponentKind.SERVICE,
            ComponentKind.CLI,
            ComponentKind.FRONTEND,
            ComponentKind.PIPELINE,
        )


# ---------------------------------------------------------------------------
# Backward compatibility: Library and Application as thin wrappers
# ---------------------------------------------------------------------------


@dataclass
class BaseComponent:
    """Base class for legacy applications and libraries."""

    name: str
    type: str
    root_path: Path
    manifest_path: Optional[Path] = None
    description: str = ""
    key_files: List[Path] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Library(BaseComponent):
    """Legacy type. Use Component with kind=LIBRARY instead."""

    external_dependencies: List[ExternalDependency] = field(default_factory=list)
    internal_dependencies: List[str] = field(default_factory=list)
    citations: List[CodeCitation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "classification": "library",
            "kind": "library",
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
            "citations": [c.to_dict() for c in self.citations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Library":
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
            citations=[CodeCitation.from_dict(c) for c in data.get("citations", [])],
        )

    def to_component(self) -> Component:
        """Convert to unified Component."""
        return Component(
            name=self.name,
            kind=ComponentKind.LIBRARY,
            type=self.type,
            root_path=str(self.root_path),
            manifest_path=str(self.manifest_path) if self.manifest_path else "",
            description=self.description,
            internal_dependencies=self.internal_dependencies,
            external_dependencies=self.external_dependencies,
            key_files=[str(f) for f in self.key_files],
            metadata=self.metadata,
            citations=self.citations,
        )


@dataclass
class Application(BaseComponent):
    """Legacy type. Use Component with kind=SERVICE/CLI/FRONTEND instead."""

    external_dependencies: List[ExternalDependency] = field(default_factory=list)
    libraries_used: List[str] = field(default_factory=list)
    internal_applications: List[str] = field(default_factory=list)
    citations: List[CodeCitation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "classification": "application",
            "kind": "service",
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
            "citations": [c.to_dict() for c in self.citations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Application":
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
            citations=[CodeCitation.from_dict(c) for c in data.get("citations", [])],
        )

    def to_component(self) -> Component:
        """Convert to unified Component."""
        return Component(
            name=self.name,
            kind=ComponentKind.SERVICE,
            type=self.type,
            root_path=str(self.root_path),
            manifest_path=str(self.manifest_path) if self.manifest_path else "",
            description=self.description,
            internal_dependencies=[],
            external_dependencies=self.external_dependencies,
            key_files=[str(f) for f in self.key_files],
            metadata=self.metadata,
            citations=self.citations,
            libraries_used=self.libraries_used,
            internal_applications=self.internal_applications,
        )


# Backward compatibility alias
KnowledgeBasis = Application | Library


def component_from_dict(data: dict) -> Component:
    """Factory function to deserialize into a Component."""
    return Component.from_dict(data)
