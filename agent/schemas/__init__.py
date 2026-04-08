"""Data schemas for code analysis agent."""

from .core import (
    Component,
    ComponentKind,
    LanguageType,
    KnowledgeBasis,
    Application,
    Library,
    ExternalDependency,
    CodeCitation,
    component_from_dict,
)
from .dependency_graph import DependencyGraph, ApplicationEdge
from .manifest import ArtifactManifest, ArtifactFile, MANIFEST_SCHEMA_VERSION

__all__ = [
    "Component",
    "ComponentKind",
    "LanguageType",
    "KnowledgeBasis",
    "Application",
    "Library",
    "ExternalDependency",
    "CodeCitation",
    "component_from_dict",
    "DependencyGraph",
    "ApplicationEdge",
    "ArtifactManifest",
    "ArtifactFile",
    "MANIFEST_SCHEMA_VERSION",
]
