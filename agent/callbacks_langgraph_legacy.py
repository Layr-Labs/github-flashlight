"""LangGraph callback handlers for agent lifecycle tracking.

Provides LangChain-compatible callback handlers that track:
- Tool calls (start, end, error)
- LLM/chat model invocations
- Subagent lifecycle (spawn, complete)
- Graph node transitions (for LangGraph visualization)
- Token usage metrics

These callbacks write structured JSONL logs for real-time visualization
in the session_profiler.html dashboard.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from agent.utils.transcript import TranscriptWriter

logger = logging.getLogger(__name__)


class FlashlightCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks tool usage, subagent lifecycle, and LLM calls.

    Provides comprehensive observability for LangGraph-based agent systems:
    - Tool call tracking with timing and context weight estimation
    - Subagent spawn/complete lifecycle events
    - LLM invocation tracking with token usage
    - Graph node transition events for visualization

    Writes structured JSONL logs compatible with the session_profiler.html dashboard.
    """

    def __init__(
        self,
        transcript_writer: Optional[TranscriptWriter] = None,
        session_dir: Optional[Path] = None,
        verbose: bool = False,
    ):
        self.transcript_writer = transcript_writer
        self.verbose = verbose

        # Active subagent context
        self._current_subagent_type: Optional[str] = None
        self._current_subagent_id: Optional[str] = None
        self._current_description: Optional[str] = None

        # Current graph node context
        self._current_graph_node: Optional[str] = None
        self._graph_run_id: Optional[str] = None

        # Counters
        self.subagent_counters: Dict[str, int] = {}
        self.active_code_analyzers: int = 0
        self.api_call_count: int = 0
        self.tool_call_count: int = 0

        # Token usage tracking
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cache_read_tokens: int = 0
        self.total_cache_creation_tokens: int = 0

        # Subagent tracking
        self._subagent_sessions: Dict[str, Dict[str, Any]] = {}

        # Active tool calls (for timing)
        self._active_tool_calls: Dict[str, datetime] = {}

        # Active LLM calls (for correlating start->complete with reasoning patterns)
        self._active_llm_calls: Dict[str, Dict[str, Any]] = {}

        # Tool call detail log (JSONL format)
        self.tool_log_file = None
        if session_dir:
            tool_log_path = session_dir / "tool_calls.jsonl"
            self.tool_log_file = open(tool_log_path, "w", encoding="utf-8")

    # ------------------------------------------------------------------
    # Subagent context management
    # ------------------------------------------------------------------

    def set_subagent_context(
        self,
        subagent_type: str,
        description: str,
    ) -> str:
        """Set the current subagent context and return a generated ID.

        Called by the graph when spawning a subagent node.

        Returns:
            Generated subagent ID (e.g., "CODE-LIBRARY-ANALYZER-3").
        """
        self.subagent_counters.setdefault(subagent_type, 0)
        self.subagent_counters[subagent_type] += 1
        subagent_id = f"{subagent_type.upper()}-{self.subagent_counters[subagent_type]}"

        self._current_subagent_type = subagent_type
        self._current_subagent_id = subagent_id
        self._current_description = description

        if subagent_type == "application-analyzer":
            self.active_code_analyzers += 1

        session = {
            "subagent_type": subagent_type,
            "subagent_id": subagent_id,
            "description": description,
            "spawned_at": datetime.now().isoformat(),
            "tool_calls": 0,
            "api_calls": 0,
        }
        self._subagent_sessions[subagent_id] = session

        print(f"{'=' * 60}")
        print(f"SUBAGENT SPAWNED: {subagent_id}")
        print(f"{'=' * 60}")
        print(f"Task: {description}")
        print(f"Type: {subagent_type}")
        print(f"{'=' * 60}")

        self._log_to_jsonl(
            {
                "event": "subagent_spawn",
                "timestamp": session["spawned_at"],
                "subagent_id": subagent_id,
                "subagent_type": subagent_type,
                "description": description,
            }
        )

        return subagent_id

    def clear_subagent_context(self) -> None:
        """Clear subagent context after subagent completes."""
        if self._current_subagent_id:
            session = self._subagent_sessions.get(self._current_subagent_id, {})
            completed_at = datetime.now().isoformat()
            session["completed_at"] = completed_at

            # Calculate duration
            spawned_at = session.get("spawned_at", "")
            if spawned_at:
                start = datetime.fromisoformat(spawned_at)
                end = datetime.fromisoformat(completed_at)
                secs = int((end - start).total_seconds())
                duration_str = f"{secs // 60:02d}:{secs % 60:02d}"
            else:
                duration_str = "??:??"

            print(f"{'=' * 60}")
            print(f"SUBAGENT COMPLETED: {self._current_subagent_id}")
            print(f"{'=' * 60}")
            print(f"Task: {self._current_description}")
            print(f"Duration: {duration_str}")
            print(f"Tool calls: {session.get('tool_calls', 0)}")
            print(f"{'=' * 60}")

            self._log_to_jsonl(
                {
                    "event": "subagent_complete",
                    "timestamp": completed_at,
                    "subagent_id": self._current_subagent_id,
                    "subagent_type": self._current_subagent_type,
                    "description": self._current_description,
                    "duration": duration_str,
                    "tool_calls": session.get("tool_calls", 0),
                }
            )

            # Handle application-analyzer completion signals
            if self._current_subagent_type == "application-analyzer":
                self.active_code_analyzers -= 1
                if self.transcript_writer:
                    self.transcript_writer.write_to_file(
                        f"[APPLICATION_ANALYSIS_COMPLETE] {self._current_description}\n"
                    )
                    if self.active_code_analyzers == 0:
                        self.transcript_writer.write_to_file(
                            "[ALL_APPLICATION_ANALYSIS_COMPLETE]\n"
                        )

        self._current_subagent_type = None
        self._current_subagent_id = None
        self._current_description = None

    # ------------------------------------------------------------------
    # LangChain callback methods
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: Optional[Dict[str, Any]],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts generating (non-chat/completion models)."""
        if serialized is None:
            serialized = {}

        self.api_call_count += 1
        agent_label = self._current_subagent_id or "LEAD AGENT"
        print(f"\n[LLM CALL #{self.api_call_count}] {agent_label}", flush=True)

        if self._current_subagent_id:
            session = self._subagent_sessions.get(self._current_subagent_id, {})
            session["api_calls"] = session.get("api_calls", 0) + 1

        # Analyze prompts for reasoning pattern (non-chat format)
        reasoning_pattern = self._analyze_prompt_reasoning_pattern(prompts, kwargs)

        # Store for correlation with llm_end
        self._active_llm_calls[str(run_id)] = {
            "reasoning_pattern": reasoning_pattern,
            "start_time": datetime.now(),
        }

        # Log LLM start event
        self._log_to_jsonl(
            {
                "event": "llm_start",
                "timestamp": datetime.now().isoformat(),
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "agent_type": self._current_subagent_type or "lead",
                "graph_node": self._current_graph_node,
                "reasoning_pattern": reasoning_pattern,
                "model": serialized.get("kwargs", {}).get("model_name", "unknown"),
                "llm_type": "completion",  # Non-chat model
            }
        )

    def on_chat_model_start(
        self,
        serialized: Optional[Dict[str, Any]],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chat model starts generating."""
        if serialized is None:
            serialized = {}

        self.api_call_count += 1
        agent_label = self._current_subagent_id or "LEAD AGENT"
        print(f"\n[LLM CALL #{self.api_call_count}] {agent_label}", flush=True)

        if self._current_subagent_id:
            session = self._subagent_sessions.get(self._current_subagent_id, {})
            session["api_calls"] = session.get("api_calls", 0) + 1

        # Analyze message structure for reasoning pattern detection
        reasoning_pattern = self._analyze_reasoning_pattern(messages, kwargs)

        # Store reasoning pattern for correlation with llm_complete
        self._active_llm_calls[str(run_id)] = {
            "reasoning_pattern": reasoning_pattern,
            "start_time": datetime.now(),
        }

        # Log LLM call start with reasoning context
        self._log_to_jsonl(
            {
                "event": "llm_start",
                "timestamp": datetime.now().isoformat(),
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "agent_type": self._current_subagent_type or "lead",
                "graph_node": self._current_graph_node,
                "reasoning_pattern": reasoning_pattern,
                "model": serialized.get("kwargs", {}).get("model_name", "unknown"),
            }
        )

    def _analyze_reasoning_pattern(
        self,
        messages: List[List[BaseMessage]],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze message structure to infer reasoning pattern.

        Patterns detected:
        - one_shot: Single user message, no prior context
        - multi_turn: Multiple back-and-forth exchanges
        - chain_of_thought: System prompt contains CoT instructions or prior reasoning
        - react: Tool use loop (agent -> tool -> agent pattern)
        - tree_of_thought: Multiple parallel branches or backtracking
        - self_reflection: Model critiquing/refining its own output
        """
        pattern = {
            "type": "one_shot",
            "turn_count": 0,
            "tool_results_in_context": 0,
            "has_system_prompt": False,
            "has_cot_instructions": False,
            "has_prior_assistant_messages": False,
            "context_window_estimate": 0,
        }

        if not messages or not messages[0]:
            return pattern

        msg_list = messages[0]  # First batch of messages
        pattern["turn_count"] = len(msg_list)

        # Count message types
        system_count = 0
        user_count = 0
        assistant_count = 0
        tool_count = 0

        total_content_length = 0
        cot_keywords = [
            "step by step",
            "think through",
            "reasoning",
            "let's think",
            "chain of thought",
            "analyze",
        ]

        for msg in msg_list:
            msg_type = type(msg).__name__
            content = ""

            if hasattr(msg, "content"):
                if isinstance(msg.content, str):
                    content = msg.content
                elif isinstance(msg.content, list):
                    content = " ".join(str(block) for block in msg.content)

            total_content_length += len(content)
            content_lower = content.lower()

            if msg_type == "SystemMessage":
                system_count += 1
                pattern["has_system_prompt"] = True
                # Check for CoT instructions in system prompt
                if any(kw in content_lower for kw in cot_keywords):
                    pattern["has_cot_instructions"] = True

            elif msg_type == "HumanMessage":
                user_count += 1

            elif msg_type == "AIMessage":
                assistant_count += 1
                pattern["has_prior_assistant_messages"] = True
                # Check for tool calls in assistant messages
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tool_count += len(msg.tool_calls)

            elif msg_type == "ToolMessage":
                tool_count += 1
                pattern["tool_results_in_context"] += 1

        # Estimate context window usage (rough: 1 token ≈ 4 chars)
        pattern["context_window_estimate"] = total_content_length // 4

        # Determine reasoning pattern type
        if tool_count > 0 and assistant_count > 0:
            # ReAct pattern: interleaved reasoning and tool use
            pattern["type"] = "react"
            if tool_count >= 3:
                pattern["type"] = "react_multi_step"
        elif assistant_count >= 2:
            # Multiple assistant messages could indicate self-reflection or tree-of-thought
            if pattern["has_cot_instructions"]:
                pattern["type"] = "chain_of_thought"
            else:
                pattern["type"] = "multi_turn"
        elif pattern["has_cot_instructions"]:
            pattern["type"] = "chain_of_thought"
        elif user_count > 1:
            pattern["type"] = "multi_turn"
        else:
            pattern["type"] = "one_shot"

        return pattern

    def _analyze_prompt_reasoning_pattern(
        self,
        prompts: List[str],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze raw prompt strings for reasoning pattern (non-chat LLM calls).

        This is used for completion-style models that receive prompts as strings
        rather than structured message lists.
        """
        pattern = {
            "type": "one_shot",
            "turn_count": len(prompts),
            "tool_results_in_context": 0,
            "has_system_prompt": False,
            "has_cot_instructions": False,
            "has_prior_assistant_messages": False,
            "context_window_estimate": 0,
            "llm_type": "completion",
        }

        if not prompts:
            return pattern

        total_content = " ".join(prompts)
        total_length = len(total_content)
        content_lower = total_content.lower()

        # Estimate context window
        pattern["context_window_estimate"] = total_length // 4

        # Check for CoT/reasoning indicators in the prompt
        cot_keywords = [
            "step by step",
            "think through",
            "reasoning",
            "let's think",
            "chain of thought",
            "analyze carefully",
            "break down",
        ]
        if any(kw in content_lower for kw in cot_keywords):
            pattern["has_cot_instructions"] = True
            pattern["type"] = "chain_of_thought"

        # Check for tool/function patterns (may appear in raw prompts)
        tool_indicators = [
            "tool_result",
            "function_call",
            "tool_call",
            "<tool>",
            "</tool>",
            "observation:",
            "action:",
        ]
        tool_matches = sum(1 for ind in tool_indicators if ind in content_lower)
        if tool_matches >= 2:
            pattern["tool_results_in_context"] = tool_matches
            pattern["type"] = "react"
            if tool_matches >= 4:
                pattern["type"] = "react_multi_step"

        # Check for multi-turn indicators
        turn_indicators = ["human:", "assistant:", "user:", "ai:"]
        turn_matches = sum(1 for ind in turn_indicators if ind in content_lower)
        if turn_matches >= 2 and pattern["type"] == "one_shot":
            pattern["type"] = "multi_turn"
            pattern["has_prior_assistant_messages"] = True

        return pattern

    def on_tool_start(
        self,
        serialized: Optional[Dict[str, Any]],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts executing."""
        if serialized is None:
            serialized = {}

        self.tool_call_count += 1
        tool_name = serialized.get("name", "unknown")
        agent_label = self._current_subagent_id or "LEAD AGENT"
        start_time = datetime.now()

        # Track start time for duration calculation
        self._active_tool_calls[str(run_id)] = start_time

        # Extract meaningful detail for console
        detail = self._get_tool_detail(tool_name, inputs)
        message = f"[{agent_label}] -> {tool_name}"
        if detail:
            message += f" {detail}"

        logger.info(message)
        if self.transcript_writer:
            self.transcript_writer.write(f"\n{message}")

        if self._current_subagent_id:
            session = self._subagent_sessions.get(self._current_subagent_id, {})
            session["tool_calls"] = session.get("tool_calls", 0) + 1

        # Parse tool input for structured logging
        tool_input = {}
        if inputs:
            tool_input = inputs
        elif input_str:
            try:
                import ast

                tool_input = (
                    ast.literal_eval(input_str)
                    if input_str.startswith("{")
                    else {"input": input_str}
                )
            except (ValueError, SyntaxError):
                tool_input = {"input": input_str[:200]}

        self._log_to_jsonl(
            {
                "event": "tool_call_start",
                "timestamp": start_time.isoformat(),
                "tool_use_id": str(run_id),
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "agent_type": self._current_subagent_type or "lead",
                "graph_node": self._current_graph_node,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "input_preview": str(input_str)[:200] if input_str else "",
            }
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes executing."""
        end_time = datetime.now()

        # Calculate duration
        start_time = self._active_tool_calls.pop(str(run_id), None)
        duration_ms = None
        if start_time:
            duration_ms = (end_time - start_time).total_seconds() * 1000

        # Handle different output types: str, ToolMessage, or other objects
        if output is None:
            output_size = 0
        elif isinstance(output, str):
            output_size = len(output)
        elif hasattr(output, "content"):
            # Handle ToolMessage and similar message objects
            output_size = len(output.content) if output.content else 0
        else:
            # Fallback: convert to string and measure
            output_size = len(str(output))

        self._log_to_jsonl(
            {
                "event": "tool_call_complete",
                "timestamp": end_time.isoformat(),
                "tool_use_id": str(run_id),
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "agent_type": self._current_subagent_type or "lead",
                "output_size": output_size,
                "duration_ms": duration_ms,
                "success": True,
            }
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool errors."""
        end_time = datetime.now()
        agent_label = self._current_subagent_id or "LEAD AGENT"
        logger.warning(f"[{agent_label}] Tool error: {error}")

        # Calculate duration
        start_time = self._active_tool_calls.pop(str(run_id), None)
        duration_ms = None
        if start_time:
            duration_ms = (end_time - start_time).total_seconds() * 1000

        self._log_to_jsonl(
            {
                "event": "tool_call_error",
                "timestamp": end_time.isoformat(),
                "tool_use_id": str(run_id),
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "agent_type": self._current_subagent_type or "lead",
                "duration_ms": duration_ms,
                "error": str(error),
            }
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM finishes generating."""
        end_time = datetime.now()

        # Retrieve reasoning pattern from correlated llm_start
        llm_call_data = self._active_llm_calls.pop(str(run_id), {})
        reasoning_pattern = llm_call_data.get("reasoning_pattern", {})
        start_time = llm_call_data.get("start_time")

        # Calculate LLM call duration
        duration_ms = None
        if start_time:
            duration_ms = (end_time - start_time).total_seconds() * 1000

        # Extract token usage from LLM response
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})

        # Handle different token usage formats (OpenAI, Anthropic via OpenRouter, etc.)
        input_tokens = token_usage.get("prompt_tokens", 0) or token_usage.get(
            "input_tokens", 0
        )
        output_tokens = token_usage.get("completion_tokens", 0) or token_usage.get(
            "output_tokens", 0
        )
        cache_read = token_usage.get("cache_read_input_tokens", 0)
        cache_creation = token_usage.get("cache_creation_input_tokens", 0)

        # Analyze response for reasoning indicators
        response_analysis = self._analyze_llm_response(response)

        # Update totals
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read
        self.total_cache_creation_tokens += cache_creation

        # Log token usage event with reasoning analysis AND pattern (no correlation needed in dashboard)
        self._log_to_jsonl(
            {
                "event": "llm_complete",
                "timestamp": end_time.isoformat(),
                "run_id": str(run_id),
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "agent_type": self._current_subagent_type or "lead",
                "graph_node": self._current_graph_node,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read,
                "cache_creation_tokens": cache_creation,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "model": llm_output.get("model_name", "unknown"),
                "response_analysis": response_analysis,
                "reasoning_pattern": reasoning_pattern,
                "duration_ms": duration_ms,
            }
        )

        # Extract text content for transcript
        if self.transcript_writer and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    text = gen.text
                    if text:
                        self.transcript_writer.write_to_file(text)

    def _analyze_llm_response(self, response: LLMResult) -> Dict[str, Any]:
        """Analyze LLM response for reasoning pattern indicators.

        Returns metrics about the response structure that help identify
        the reasoning pattern used.
        """
        analysis = {
            "has_tool_calls": False,
            "tool_call_count": 0,
            "has_thinking": False,
            "thinking_length": 0,
            "response_length": 0,
            "output_type": "text",
        }

        if not response.generations:
            return analysis

        for gen_list in response.generations:
            for gen in gen_list:
                # Check for tool calls
                if hasattr(gen, "message"):
                    msg = gen.message
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        analysis["has_tool_calls"] = True
                        analysis["tool_call_count"] = len(msg.tool_calls)
                        analysis["output_type"] = "tool_calls"

                    # Check for thinking/reasoning blocks (Claude extended thinking)
                    if hasattr(msg, "content") and isinstance(msg.content, list):
                        for block in msg.content:
                            if isinstance(block, dict):
                                if block.get("type") == "thinking":
                                    analysis["has_thinking"] = True
                                    analysis["thinking_length"] = len(
                                        block.get("thinking", "")
                                    )
                                elif block.get("type") == "text":
                                    analysis["response_length"] += len(
                                        block.get("text", "")
                                    )
                    elif hasattr(msg, "content") and isinstance(msg.content, str):
                        analysis["response_length"] = len(msg.content)

                # Fallback to gen.text
                if gen.text:
                    if analysis["response_length"] == 0:
                        analysis["response_length"] = len(gen.text)

        return analysis

    # ------------------------------------------------------------------
    # Graph node tracking (LangGraph integration)
    # ------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain/graph node starts execution."""
        # Handle None serialized (can happen with some LangChain components)
        if serialized is None:
            serialized = {}

        node_name = serialized.get("name", "unknown")
        graph_id = serialized.get("graph", {}).get("id", str(run_id)[:8])

        # Track graph run
        if not self._graph_run_id:
            self._graph_run_id = graph_id

        self._current_graph_node = node_name

        self._log_to_jsonl(
            {
                "event": "graph_node_start",
                "timestamp": datetime.now().isoformat(),
                "node_name": node_name,
                "graph_id": graph_id,
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
            }
        )

        if self.verbose:
            logger.info(f"[GRAPH] Node started: {node_name}")

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain/graph node completes execution."""
        node_name = self._current_graph_node or "unknown"

        self._log_to_jsonl(
            {
                "event": "graph_node_end",
                "timestamp": datetime.now().isoformat(),
                "node_name": node_name,
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "run_id": str(run_id),
            }
        )

        if self.verbose:
            logger.info(f"[GRAPH] Node completed: {node_name}")

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain/graph node errors."""
        node_name = self._current_graph_node or "unknown"

        self._log_to_jsonl(
            {
                "event": "graph_node_error",
                "timestamp": datetime.now().isoformat(),
                "node_name": node_name,
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "run_id": str(run_id),
                "error": str(error),
            }
        )

        logger.error(f"[GRAPH] Node error in {node_name}: {error}")

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _get_tool_detail(
        self, tool_name: str, tool_input: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Extract human-readable detail for specific tools."""
        if not tool_input:
            return None

        if tool_name == "grep_files":
            pattern = tool_input.get("pattern", "")
            path = tool_input.get("path")
            if path:
                return f"`{pattern}` in {path}"
            return f"`{pattern}`"

        if tool_name in ("read_file", "write_file"):
            fp = tool_input.get("file_path", "")
            return fp

        if tool_name == "glob_files":
            return f"`{tool_input.get('pattern', '')}`"

        if tool_name == "bash":
            command = tool_input.get("command", "")
            if len(command) > 80:
                return f"`{command[:80]}...`"
            return f"`{command}`"

        return None

    def _log_to_jsonl(self, log_entry: Dict[str, Any]) -> None:
        """Write structured log entry to JSONL file."""
        if self.tool_log_file:
            self.tool_log_file.write(json.dumps(log_entry) + "\n")
            self.tool_log_file.flush()

    def close(self) -> None:
        """Close the tool log file."""
        if self.tool_log_file:
            self.tool_log_file.close()
            self.tool_log_file = None
