"""LangGraph state definitions for the flashlight multi-agent system.

Defines the shared state schemas used by the lead agent graph and
subagent subgraphs. Uses TypedDict with LangGraph's Annotated reducers
for message accumulation.
"""

import os
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Optional, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# Default model from environment variable
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")


# ---------------------------------------------------------------------------
# Lead agent state
# ---------------------------------------------------------------------------


class AgentState(dict):
    """State for the lead orchestrator agent.

    Attributes:
        messages: Accumulated conversation messages (LLM + tool results).
        subagent_results: Map of subagent task descriptions to their outputs.
        pending_subagents: List of subagent tasks queued for execution.
        completed_subagents: Count of completed subagent tasks.
        service_name: Name of the service being analyzed.
        repo_path: Path to the cloned repository.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    subagent_results: Dict[str, str]
    pending_subagents: List[Dict[str, Any]]
    completed_subagents: int
    service_name: str
    repo_path: str


# Using TypedDict for LangGraph compatibility
from typing import TypedDict


class LeadAgentState(TypedDict):
    """State schema for the lead orchestrator graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    subagent_results: dict[str, str]
    service_name: str
    repo_path: str


class SubagentState(TypedDict):
    """State schema for individual subagent (code analyzer, etc.) graphs."""

    messages: Annotated[list[BaseMessage], add_messages]
    subagent_type: str
    description: str
    service_name: str
    repo_path: str


# ---------------------------------------------------------------------------
# Subagent task descriptor
# ---------------------------------------------------------------------------


@dataclass
class SubagentTask:
    """Describes a subagent to be spawned by the lead agent.

    Created when the lead agent decides to delegate analysis of a component
    to a specialized subagent.
    """

    subagent_type: str  # e.g., "code-library-analyzer", "application-analyzer"
    description: str  # e.g., "Analyze the crypto library"
    prompt: str  # Full prompt to send to the subagent
    tools: List[str] = field(default_factory=list)  # Tool names this agent needs
    model: str = field(default_factory=lambda: DEFAULT_MODEL)

    def to_dict(self) -> dict:
        return {
            "subagent_type": self.subagent_type,
            "description": self.description,
            "prompt": self.prompt,
            "tools": self.tools,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubagentTask":
        return cls(
            subagent_type=data["subagent_type"],
            description=data["description"],
            prompt=data["prompt"],
            tools=data.get("tools", []),
            model=data.get("model", DEFAULT_MODEL),
        )
