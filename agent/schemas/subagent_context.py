"""Analysis context for subagent prompts."""

from dataclasses import dataclass
from typing import Optional

@dataclass
class AnalysisContext:
    """Context information passed to code analyzer subagents."""
    
    component_name: str
    component_type: str
    classification: str
    root_path: str
    description: str
    upstream_context: Optional[str] = None
    library_context: Optional[str] = None
