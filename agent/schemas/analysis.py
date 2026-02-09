"""Service analysis output schema."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class ServiceAnalysis:
    """Results of analyzing a single service."""

    service_name: str
    analyzer_id: str  # e.g., "CODE-ANALYZER-3"
    timestamp: str

    # Analysis sections
    architecture: str  # High-level architecture description
    key_components: List[str]  # Major components/modules
    data_flows: List[str]  # Important data/control flows
    external_dependencies: List[str]  # External libraries/services used
    internal_dependencies: List[str]  # Internal services depended upon
    api_surface: str  # Public API/interfaces exposed

    # Context from upstream
    upstream_context: Dict[str, str] = field(default_factory=dict)  # dep_name -> summary

    # Metadata
    files_analyzed: List[Path] = field(default_factory=list)
    analysis_depth: str = "deep"  # "light", "medium", "deep"

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON/markdown output."""
        return {
            "service_name": self.service_name,
            "analyzer_id": self.analyzer_id,
            "timestamp": self.timestamp,
            "architecture": self.architecture,
            "key_components": self.key_components,
            "data_flows": self.data_flows,
            "external_dependencies": self.external_dependencies,
            "internal_dependencies": self.internal_dependencies,
            "api_surface": self.api_surface,
            "upstream_context": self.upstream_context,
            "files_analyzed": [str(f) for f in self.files_analyzed],
            "analysis_depth": self.analysis_depth,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServiceAnalysis":
        """Deserialize from dictionary."""
        return cls(
            service_name=data["service_name"],
            analyzer_id=data["analyzer_id"],
            timestamp=data["timestamp"],
            architecture=data["architecture"],
            key_components=data["key_components"],
            data_flows=data["data_flows"],
            external_dependencies=data["external_dependencies"],
            internal_dependencies=data["internal_dependencies"],
            api_surface=data["api_surface"],
            upstream_context=data.get("upstream_context", {}),
            files_analyzed=[Path(f) for f in data.get("files_analyzed", [])],
            analysis_depth=data.get("analysis_depth", "deep"),
        )
