"""LangGraph graph definitions for the flashlight multi-agent system.

Replaces the claude-agent-sdk's ClaudeSDKClient with explicit LangGraph
StateGraphs for the lead orchestrator and specialized subagents.

Architecture:
    - build_subagent_graph(): Creates a reusable tool-calling agent graph
      for code analysis, architecture documentation, and external service analysis.
    - build_lead_graph(): Creates the top-level orchestrator graph that
      delegates to subagents via the Task tool pattern.

The lead agent uses a custom "spawn_subagent" tool that, when called,
is intercepted by the graph to run a subagent subgraph.

LLM calls are routed through OpenRouter (https://openrouter.ai/api/v1)
using the OpenAI-compatible ChatOpenAI client. Set OPENROUTER_API_KEY
in your environment.
"""

import logging
import os
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from agent.callbacks import FlashlightCallbackHandler
from agent.state import LeadAgentState, SubagentState
from agent.tools import (
    ANALYSIS_TOOLS,
    DOCUMENTER_TOOLS,
    LEAD_AGENT_TOOLS,
)

logger = logging.getLogger(__name__)

# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _make_llm(
    model_name: str = "anthropic/claude-sonnet-4-20250514",
    max_tokens: int = 16384,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance configured for OpenRouter.

    Args:
        model_name: Model identifier on OpenRouter (e.g., "anthropic/claude-sonnet-4-20250514").
        max_tokens: Maximum tokens for completion.

    Returns:
        Configured ChatOpenAI instance.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Get one at https://openrouter.ai/keys"
        )

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=OPENROUTER_BASE_URL,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "https://github.com/Layr-Labs/github-flashlight",
            "X-Title": "github-flashlight",
        },
    )


# ---------------------------------------------------------------------------
# Agent configurations (prompt + model + tools per agent type)
# ---------------------------------------------------------------------------


# Maps agent type names to tool sets
AGENT_TOOL_MAP = {
    "code-library-analyzer": ANALYSIS_TOOLS,
    "application-analyzer": ANALYSIS_TOOLS,
    "architecture-documenter": DOCUMENTER_TOOLS,
    "external-service-analyzer": ANALYSIS_TOOLS,
}


# ---------------------------------------------------------------------------
# Subagent graph
# ---------------------------------------------------------------------------


def build_subagent_graph(
    system_prompt: str,
    tools: list,
    model_name: str = "anthropic/claude-sonnet-4-20250514",
) -> StateGraph:
    """Build a tool-calling agent subgraph for a specialized subagent.

    This creates a simple ReAct-style loop:
        agent_node -> should_continue -> tool_node -> agent_node -> ...

    Args:
        system_prompt: System prompt for this subagent.
        tools: List of LangChain tool objects available to this agent.
        model_name: OpenRouter model identifier.

    Returns:
        Compiled LangGraph StateGraph.
    """
    llm = _make_llm(model_name=model_name).bind_tools(tools)
    tool_node = ToolNode(tools)

    def agent_node(state: SubagentState) -> dict:
        """Invoke the LLM with the current message history."""
        messages = state["messages"]
        # Prepend system prompt if not already present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + list(messages)

        response = llm.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: SubagentState) -> Literal["tools", "__end__"]:
        """Route based on whether the last message has tool calls."""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        return "__end__"

    graph = StateGraph(SubagentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")

    return graph.compile()


# ---------------------------------------------------------------------------
# Lead agent graph
# ---------------------------------------------------------------------------


def _make_spawn_subagent_tool():
    """Create the spawn_subagent tool definition.

    This tool is called by the lead agent LLM when it wants to delegate
    work to a subagent. The actual subagent execution is handled by the
    graph's routing logic, not by this tool function -- this function
    just returns a marker that the graph intercepts.
    """

    @tool
    def spawn_subagent(
        subagent_type: str,
        description: str,
        prompt: str,
    ) -> str:
        """Spawn a specialized subagent to perform analysis.

        Use this tool to delegate work to a specialized agent. Available types:
        - code-library-analyzer: Analyze a library/package component
        - application-analyzer: Analyze an application/service component
        - architecture-documenter: Synthesize architecture documentation from completed analyses
        - external-service-analyzer: Analyze integration with an external service

        Args:
            subagent_type: The type of subagent to spawn.
            description: Brief description of the task (e.g., "Analyze the crypto library").
            prompt: The full prompt/instructions for the subagent.
        """
        # This is a placeholder -- the actual execution is handled by the
        # lead graph's routing logic, which intercepts spawn_subagent tool
        # calls and runs the appropriate subagent subgraph.
        return f"Subagent '{subagent_type}' task '{description}' has been queued."

    return spawn_subagent


def build_lead_graph(
    system_prompt: str,
    agent_prompts: Dict[str, str],
    model_name: str = "anthropic/claude-sonnet-4-20250514",
    callback_handler: Optional[FlashlightCallbackHandler] = None,
) -> StateGraph:
    """Build the lead orchestrator graph.

    The lead agent has access to file tools AND a special spawn_subagent tool.
    When it calls spawn_subagent, the graph intercepts the call, runs the
    subagent as an inline subgraph, and returns the result.

    Args:
        system_prompt: System prompt for the lead orchestrator.
        agent_prompts: Map of subagent type -> system prompt.
        model_name: OpenRouter model identifier.
        callback_handler: Optional callback handler for lifecycle tracking.

    Returns:
        Compiled LangGraph StateGraph.
    """
    spawn_subagent = _make_spawn_subagent_tool()

    # Lead agent has file tools + the spawn_subagent tool
    lead_tools = LEAD_AGENT_TOOLS + [spawn_subagent]

    llm = _make_llm(model_name=model_name).bind_tools(lead_tools)

    # Tool node for non-subagent tools only (file operations, bash)
    file_tool_node = ToolNode(LEAD_AGENT_TOOLS)

    def agent_node(state: LeadAgentState) -> dict:
        """Invoke the lead agent LLM."""
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + list(messages)

        response = llm.invoke(messages)
        return {"messages": [response]}

    def route_tools(
        state: LeadAgentState,
    ) -> Literal["file_tools", "run_subagent", "__end__"]:
        """Route based on the type of tool call in the last message.

        - spawn_subagent calls -> run_subagent node
        - file/bash tool calls -> file_tools node
        - no tool calls -> end
        """
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return "__end__"

        # Check if any tool call is a spawn_subagent call
        for tc in last_message.tool_calls:
            if tc["name"] == "spawn_subagent":
                return "run_subagent"

        return "file_tools"

    def run_subagent(state: LeadAgentState) -> dict:
        """Execute subagent(s) requested by the lead agent.

        Finds all spawn_subagent tool calls in the last message,
        runs each subagent as an inline subgraph, and returns
        ToolMessage results.
        """
        last_message = state["messages"][-1]
        service_name = state.get("service_name", "unknown")
        repo_path = state.get("repo_path", "")
        results: List[ToolMessage] = []

        for tc in last_message.tool_calls:
            if tc["name"] != "spawn_subagent":
                # Handle non-subagent tool calls that got mixed in
                results.append(
                    ToolMessage(
                        content="Error: non-subagent tool call routed to subagent handler",
                        tool_call_id=tc["id"],
                    )
                )
                continue

            subagent_type = tc["args"]["subagent_type"]
            description = tc["args"]["description"]
            prompt = tc["args"]["prompt"]

            # Get the subagent's system prompt
            subagent_system_prompt = agent_prompts.get(subagent_type, "")
            if not subagent_system_prompt:
                results.append(
                    ToolMessage(
                        content=f"Error: unknown subagent type '{subagent_type}'",
                        tool_call_id=tc["id"],
                    )
                )
                continue

            # Get tools for this subagent type
            subagent_tools = AGENT_TOOL_MAP.get(subagent_type, ANALYSIS_TOOLS)

            # Notify callback handler
            subagent_id = None
            if callback_handler:
                subagent_id = callback_handler.set_subagent_context(
                    subagent_type, description
                )

            try:
                # Build and run the subagent graph
                subagent_graph = build_subagent_graph(
                    system_prompt=subagent_system_prompt,
                    tools=subagent_tools,
                    model_name=model_name,
                )

                # Run the subagent with a human message containing the task prompt
                subagent_result = subagent_graph.invoke(
                    {
                        "messages": [HumanMessage(content=prompt)],
                        "subagent_type": subagent_type,
                        "description": description,
                        "service_name": service_name,
                        "repo_path": repo_path,
                    },
                    config={"callbacks": [callback_handler]}
                    if callback_handler
                    else {},
                )

                # Extract the final text response from the subagent
                final_messages = subagent_result.get("messages", [])
                final_text = ""
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        if isinstance(msg.content, str):
                            final_text = msg.content
                        elif isinstance(msg.content, list):
                            # Handle content blocks
                            text_parts = [
                                block["text"]
                                for block in msg.content
                                if isinstance(block, dict)
                                and block.get("type") == "text"
                            ]
                            final_text = "\n".join(text_parts)
                        break

                if not final_text:
                    final_text = f"Subagent {subagent_type} completed (no text output)."

                results.append(
                    ToolMessage(
                        content=final_text,
                        tool_call_id=tc["id"],
                    )
                )

            except Exception as exc:
                logger.error(
                    "Subagent %s failed: %s", subagent_type, exc, exc_info=True
                )
                results.append(
                    ToolMessage(
                        content=f"Error: subagent {subagent_type} failed: {exc}",
                        tool_call_id=tc["id"],
                    )
                )
            finally:
                if callback_handler:
                    callback_handler.clear_subagent_context()

        return {"messages": results}

    # Build the graph
    graph = StateGraph(LeadAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("file_tools", file_tool_node)
    graph.add_node("run_subagent", run_subagent)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_tools)
    graph.add_edge("file_tools", "agent")
    graph.add_edge("run_subagent", "agent")

    return graph.compile()
