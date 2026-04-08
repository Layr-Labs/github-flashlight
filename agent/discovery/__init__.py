"""Deterministic component discovery engine.

Replaces LLM-driven discovery with fast, reliable manifest parsing.
Scans a repository, finds components via language-specific plugins,
classifies them, extracts dependencies, and validates the results.
"""

from .engine import discover_components
from .validator import validate_discovery, validate_graph, ValidationError

__all__ = [
    "discover_components",
    "validate_discovery",
    "validate_graph",
    "ValidationError",
]
