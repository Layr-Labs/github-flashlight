"""Data schemas for code analysis agent."""

from .core import (
    Component,
    ComponentKind,
    LanguageType,
    ExternalDependency,
    CodeCitation,
    component_from_dict,
)
from .dependency_graph import DependencyGraph, ComponentEdge
from .manifest import ArtifactManifest, ArtifactFile, MANIFEST_SCHEMA_VERSION

__all__ = [
    "Component",
    "ComponentKind",
    "LanguageType",
    "ExternalDependency",
    "CodeCitation",
    "component_from_dict",
    "DependencyGraph",
    "ComponentEdge",
    "ArtifactManifest",
    "ArtifactFile",
    "MANIFEST_SCHEMA_VERSION",
]
