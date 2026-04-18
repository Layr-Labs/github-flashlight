"""LangGraph graph definitions for the flashlight multi-agent system.

Architecture:
    - Interactive Lead Agent via `build_lead_graph()` for CLI interaction
    - Parallel Layer-Based Orchestration via `run_parallel_analysis()`
    - Deterministic dispatch based on dependency graph topological layers
    - All subagents within a layer execute in parallel
    - Context accumulates between layers for dependency-aware analysis

LLM calls are routed through OpenRouter (https://openrouter.ai/api/v1)
using the OpenAI-compatible ChatOpenAI client. Set OPENROUTER_API_KEY
in your environment.
"""

import logging
import os
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from agent.callbacks import FlashlightCallbackHandler
from agent.state import LeadAgentState, SubagentState
from agent.tools import ANALYSIS_TOOLS, DOCUMENTER_TOOLS, LEAD_AGENT_TOOLS

logger = logging.getLogger(__name__)

# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _make_llm(
    model_name: str | None = None,
    max_tokens: int = 16384,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance configured for OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Get one at https://openrouter.ai/keys"
        )

    model = model_name or DEFAULT_MODEL
    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=OPENROUTER_BASE_URL,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "https://github.com/anthropics/flashlight",
            "X-Title": "flashlight",
        },
    )


# ---------------------------------------------------------------------------
# Agent tool configurations
# ---------------------------------------------------------------------------

AGENT_TOOL_MAP = {
    "code-library-analyzer": ANALYSIS_TOOLS,
    "application-analyzer": ANALYSIS_TOOLS,
    "architecture-documenter": DOCUMENTER_TOOLS,
    "external-service-analyzer": ANALYSIS_TOOLS,
}


# ---------------------------------------------------------------------------
# Subagent graph (ReAct loop for individual component analysis)
# ---------------------------------------------------------------------------


def build_subagent_graph(
    system_prompt: str,
    tools: list,
    model_name: str | None = None,
) -> StateGraph:
    """Build a tool-calling agent graph for a specialized subagent.

    Creates a ReAct-style loop:
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
# Parallel layer-based orchestration (primary entry point)
# ---------------------------------------------------------------------------


def run_parallel_analysis(
    components: List[Any],
    agent_prompts: Dict[str, str],
    model_name: str | None = None,
    callback_handler: Optional[FlashlightCallbackHandler] = None,
    max_workers: int = 10,
) -> Dict[str, Any]:
    """Run parallel layer-based analysis of all components.

    This is the primary entry point for analyzing a codebase:

    1. Builds a dependency graph from component.internal_dependencies
    2. Computes topological layers (leaves first)
    3. Dispatches all subagents in a layer in parallel
    4. Waits for layer completion before proceeding
    5. Passes accumulated analysis context to subsequent layers

    Args:
        components: List of discovered Component objects.
        agent_prompts: Map of subagent type -> system prompt.
        model_name: OpenRouter model identifier.
        callback_handler: Optional callback handler for observability.
        max_workers: Maximum parallel subagents per layer.

    Returns:
        Dict mapping component name to SubagentResult with analysis output.

    Example:
        from agent.discovery.engine import discover_components
        from agent.graph import run_parallel_analysis

        components = discover_components(repo_path)
        results = run_parallel_analysis(
            components=components,
            agent_prompts=AGENT_PROMPTS,
            callback_handler=my_callback,
        )

        for name, result in results.items():
            if result.success:
                print(f"{name}: {result.output[:200]}...")
    """
    from agent.orchestrator import ParallelOrchestrator, make_subagent_runner

    runner = make_subagent_runner(
        build_graph_fn=build_subagent_graph,
        agent_prompts=agent_prompts,
        model_name=model_name,
        callback_handler=callback_handler,
    )

    orchestrator = ParallelOrchestrator(
        components=components,
        subagent_runner=runner,
        callback_handler=callback_handler,
        max_workers=max_workers,
        agent_prompts=agent_prompts,
    )

    return orchestrator.run()


def build_analysis_pipeline(
    components: List[Any],
    agent_prompts: Dict[str, str],
    synthesis_prompt: str,
    model_name: str | None = None,
    callback_handler: Optional[FlashlightCallbackHandler] = None,
    max_workers: int = 10,
) -> StateGraph:
    """Build a complete analysis pipeline with parallel dispatch + synthesis.

    Creates a LangGraph that:
    1. Runs parallel layer-based analysis of all components
    2. Synthesizes results into final documentation

    Args:
        components: List of discovered Component objects.
        agent_prompts: Map of subagent type -> system prompt.
        synthesis_prompt: System prompt for the synthesis phase.
        model_name: OpenRouter model identifier.
        callback_handler: Optional callback handler.
        max_workers: Maximum parallel subagents per layer.

    Returns:
        Compiled LangGraph StateGraph.
    """
    from typing import TypedDict

    from agent.orchestrator import (
        ParallelOrchestrator,
        build_dependency_layers,
        make_subagent_runner,
    )

    layers, _ = build_dependency_layers(components)
    llm = _make_llm(model_name=model_name)

    runner = make_subagent_runner(
        build_graph_fn=build_subagent_graph,
        agent_prompts=agent_prompts,
        model_name=model_name,
        callback_handler=callback_handler,
    )

    class PipelineState(TypedDict):
        """State for the analysis pipeline."""

        messages: List[Any]
        analysis_results: dict
        layers_completed: int
        synthesis_complete: bool

    def parallel_analysis_node(state: PipelineState) -> dict:
        """Execute parallel layer-based analysis."""
        orchestrator = ParallelOrchestrator(
            components=components,
            subagent_runner=runner,
            callback_handler=callback_handler,
            max_workers=max_workers,
            agent_prompts=agent_prompts,
        )

        results = orchestrator.run()

        analysis_results = {
            name: {
                "success": r.success,
                "output": r.output,
                "error": r.error,
                "duration": r.duration_seconds,
            }
            for name, r in results.items()
        }

        return {
            "analysis_results": analysis_results,
            "layers_completed": len(layers),
        }

    def synthesis_node(state: PipelineState) -> dict:
        """Synthesize all analysis results into final documentation."""
        results = state.get("analysis_results", {})

        results_text = "\n\n".join(
            f"## {name}\n{data.get('output', 'No output')}"
            for name, data in results.items()
            if data.get("success", False)
        )

        synthesis_message = HumanMessage(
            content=f"""Based on the following component analyses, synthesize a comprehensive 
architecture document for the codebase.

{results_text}

Please create:
1. Executive Summary
2. System Architecture Overview  
3. Component Relationships
4. Key Design Patterns
5. External Dependencies Analysis
6. Recommendations
"""
        )

        messages = [
            SystemMessage(content=synthesis_prompt),
            synthesis_message,
        ]

        response = llm.invoke(messages)

        return {
            "messages": [synthesis_message, response],
            "synthesis_complete": True,
        }

    def should_synthesize(state: PipelineState) -> Literal["synthesis", "__end__"]:
        """Route to synthesis if analysis is complete."""
        if state.get("synthesis_complete"):
            return "__end__"
        if state.get("analysis_results"):
            return "synthesis"
        return "__end__"

    graph = StateGraph(PipelineState)
    graph.add_node("parallel_analysis", parallel_analysis_node)
    graph.add_node("synthesis", synthesis_node)

    graph.set_entry_point("parallel_analysis")
    graph.add_conditional_edges("parallel_analysis", should_synthesize)
    graph.add_edge("synthesis", "__end__")

    return graph.compile()


# ---------------------------------------------------------------------------
# Lead agent graph (interactive CLI)
# ---------------------------------------------------------------------------


def build_lead_graph(
    system_prompt: str,
    agent_prompts: Dict[str, str],
    model_name: str | None = None,
    callback_handler: Optional[FlashlightCallbackHandler] = None,
) -> StateGraph:
    """Build the interactive lead agent graph for CLI usage.

    Creates a ReAct-style agent loop that:
        1. Receives user input
        2. Invokes the LLM with tools
        3. Executes tool calls
        4. Continues until LLM produces a final response

    The lead agent can use file exploration tools to understand the codebase
    and coordinate analysis work.

    Args:
        system_prompt: System prompt for the lead agent.
        agent_prompts: Map of subagent type -> system prompt (for future use).
        model_name: OpenRouter model identifier.
        callback_handler: Optional callback handler for observability.

    Returns:
        Compiled LangGraph StateGraph.

    Example:
        graph = build_lead_graph(
            system_prompt=load_prompt("lead_agent.txt"),
            agent_prompts={"code-library-analyzer": "..."},
        )

        state = {"messages": [], "subagent_results": {}, ...}
        result = graph.invoke(state, config={"callbacks": [handler]})
    """
    llm = _make_llm(model_name=model_name).bind_tools(LEAD_AGENT_TOOLS)
    tool_node = ToolNode(LEAD_AGENT_TOOLS)

    def agent_node(state: LeadAgentState) -> dict:
        """Invoke the lead agent LLM with conversation history."""
        messages = list(state.get("messages", []))

        # Ensure system prompt is first
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages

        response = llm.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: LeadAgentState) -> Literal["tools", "__end__"]:
        """Route based on whether the last message has tool calls."""
        messages = state.get("messages", [])
        if not messages:
            return "__end__"

        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        return "__end__"

    graph = StateGraph(LeadAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")

    return graph.compile()
