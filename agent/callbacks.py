"""LangGraph callback handlers for agent lifecycle tracking.

Replaces the claude-agent-sdk hook system (PreToolUse, PostToolUse,
SubagentStop) with LangChain-compatible callback handlers that integrate
with the existing SubagentTracker and TranscriptWriter infrastructure.
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

    Replaces the claude-agent-sdk hook system with LangChain callbacks.
    Writes structured logs to transcript and JSONL files.
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

        # Counters
        self.subagent_counters: Dict[str, int] = {}
        self.active_code_analyzers: int = 0
        self.api_call_count: int = 0
        self.tool_call_count: int = 0

        # Subagent tracking
        self._subagent_sessions: Dict[str, Dict[str, Any]] = {}

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
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts generating."""
        self.api_call_count += 1
        agent_label = self._current_subagent_id or "LEAD AGENT"
        print(f"\n[CLAUDE CALL #{self.api_call_count}] {agent_label}", flush=True)

        if self._current_subagent_id:
            session = self._subagent_sessions.get(self._current_subagent_id, {})
            session["api_calls"] = session.get("api_calls", 0) + 1

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when chat model starts generating."""
        self.api_call_count += 1
        agent_label = self._current_subagent_id or "LEAD AGENT"
        print(f"\n[CLAUDE CALL #{self.api_call_count}] {agent_label}", flush=True)

        if self._current_subagent_id:
            session = self._subagent_sessions.get(self._current_subagent_id, {})
            session["api_calls"] = session.get("api_calls", 0) + 1

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
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
        self.tool_call_count += 1
        tool_name = serialized.get("name", "unknown")
        agent_label = self._current_subagent_id or "LEAD AGENT"

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

        self._log_to_jsonl(
            {
                "event": "tool_call_start",
                "timestamp": datetime.now().isoformat(),
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "tool_name": tool_name,
                "input_preview": str(input_str)[:200] if input_str else "",
            }
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes executing."""
        output_size = len(output) if output else 0

        self._log_to_jsonl(
            {
                "event": "tool_call_complete",
                "timestamp": datetime.now().isoformat(),
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
                "output_size": output_size,
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
        agent_label = self._current_subagent_id or "LEAD AGENT"
        logger.warning(f"[{agent_label}] Tool error: {error}")

        self._log_to_jsonl(
            {
                "event": "tool_call_error",
                "timestamp": datetime.now().isoformat(),
                "agent_id": self._current_subagent_id or "MAIN_AGENT",
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
        # Extract text content for transcript
        if self.transcript_writer and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    text = gen.text
                    if text:
                        self.transcript_writer.write_to_file(text)

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
