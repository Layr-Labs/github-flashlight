"""Comprehensive tracking system for subagent tool calls using hooks and message stream."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Record of a single tool call."""
    timestamp: str
    tool_name: str
    tool_input: Dict[str, Any]
    tool_use_id: str
    subagent_type: str
    parent_tool_use_id: Optional[str] = None
    tool_output: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class SubagentSession:
    """Information about a subagent execution session."""
    subagent_type: str
    parent_tool_use_id: str
    spawned_at: str
    description: str
    prompt_preview: str
    subagent_id: str  # Unique identifier like "RESEARCHER-1"
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    completed_at: Optional[str] = None
    is_complete: bool = False
    api_call_count: int = 0  # Track API round-trips for this subagent
    last_api_call_time: Optional[str] = None


class SubagentTracker:
    """
    Tracks all tool calls made by subagents using both hooks and message stream parsing.

    This tracker:
    1. Monitors the message stream to detect subagent spawns via Task tool
    2. Uses hooks (PreToolUse/PostToolUse) to capture all tool invocations
    3. Associates tool calls with their originating subagent
    4. Logs tool usage to console and transcript files
    """

    def __init__(
        self,
        transcript_writer=None,
        session_dir: Optional[Path] = None,
        verbose: bool = False
    ):
        # Map: parent_tool_use_id -> SubagentSession
        self.sessions: Dict[str, SubagentSession] = {}

        # Map: tool_use_id -> ToolCallRecord (for efficient lookup in post hook)
        self.tool_call_records: Dict[str, ToolCallRecord] = {}

        # Counter for active code-analyzer subagents (for orchestration)
        self.active_code_analyzers = 0

        # Current execution context (from message stream)
        self._current_parent_id: Optional[str] = None

        # Counter for each subagent type to create unique IDs
        self.subagent_counters: Dict[str, int] = defaultdict(int)

        # Transcript writer for logging clean output
        self.transcript_writer = transcript_writer

        # Verbose mode for detailed API logging
        self.verbose = verbose

        # Tool call detail log (JSONL format)
        self.tool_log_file = None
        if session_dir:
            tool_log_path = session_dir / "tool_calls.jsonl"
            self.tool_log_file = open(tool_log_path, "w", encoding="utf-8")

        logger.debug("SubagentTracker initialized (verbose=%s)", verbose)

    def register_subagent_spawn(
        self,
        tool_use_id: str,
        subagent_type: str,
        description: str,
        prompt: str
    ) -> str:
        """
        Register a new subagent spawn detected from the message stream.

        Args:
            tool_use_id: The ID of the Task tool use block
            subagent_type: Type of subagent (e.g., 'researcher', 'report-writer')
            description: Brief description of the task
            prompt: The full prompt given to the subagent

        Returns:
            The generated subagent_id (e.g., 'RESEARCHER-1')
        """
        # Increment counter for this subagent type and create unique ID
        self.subagent_counters[subagent_type] += 1
        subagent_id = f"{subagent_type.upper()}-{self.subagent_counters[subagent_type]}"

        session = SubagentSession(
            subagent_type=subagent_type,
            parent_tool_use_id=tool_use_id,
            spawned_at=datetime.now().isoformat(),
            description=description,
            prompt_preview=prompt[:1000] + "..." if len(prompt) > 1000 else prompt,
            subagent_id=subagent_id
        )

        self.sessions[tool_use_id] = session

        # Increment counter for application-analyzer subagents
        if subagent_type == "application-analyzer":
            self.active_code_analyzers += 1
            print(f"📊 Active code-analyzers: {self.active_code_analyzers}")

        print(f"{'='*60}")
        print(f"🚀 SUBAGENT SPAWNED: {subagent_id}")
        print(f"{'='*60}")
        print(f"Task: {description}")
        print(f"Type: {subagent_type}")
        print(f"Tool Use ID: {tool_use_id}")
        print(f"{'='*60}")

        # Verbose spawn logging
        if self.verbose:
            logger.info(f"📝 AGENT DETAILS:")
            logger.info(f"   Spawn Time: {session.spawned_at}")
            logger.debug(f"   Prompt Preview: {session.prompt_preview}")

        return subagent_id

    def mark_subagent_complete(self, tool_use_id: str):
        """
        Mark a subagent session as complete.

        Args:
            tool_use_id: The ID of the Task tool use block
        """
        session = self.sessions.get(tool_use_id)
        if not session:
            logger.warning(f"Attempted to mark unknown subagent as complete: {tool_use_id}")
            return

        session.completed_at = datetime.now().isoformat()
        session.is_complete = True

        print(f"{'='*60}")
        print(f"✅ SUBAGENT COMPLETED: {session.subagent_id}")
        print(f"{'='*60}")
        print(f"Task: {session.description}")
        print(f"Duration: {session.spawned_at} → {session.completed_at}")
        print(f"API calls: {session.api_call_count}")
        print(f"Tool calls: {len(session.tool_calls)}")
        print(f"{'='*60}")

        # Verbose completion logging
        if self.verbose:
            print(f"📊 COMPLETION DETAILS:")
            print(f"   Type: {session.subagent_type}")
            print(f"   Tool Use ID: {tool_use_id}")
            print(f"   Started: {session.spawned_at}")
            print(f"   Completed: {session.completed_at}")
            print(f"   API Calls: {session.api_call_count}")
            print(f"   Tool Calls: {len(session.tool_calls)}")

        # Log completion to JSONL
        self._log_to_jsonl({
            "event": "subagent_complete",
            "timestamp": session.completed_at,
            "subagent_id": session.subagent_id,
            "subagent_type": session.subagent_type,
            "tool_use_id": tool_use_id,
            "description": session.description,
            "spawned_at": session.spawned_at,
            "completed_at": session.completed_at,
            "api_call_count": session.api_call_count,
            "tool_call_count": len(session.tool_calls)
        })

        # Handle application-analyzer completions
        if session.subagent_type == "application-analyzer":
            self.active_code_analyzers -= 1
            logger.info(f"📊 Active code-analyzers: {self.active_code_analyzers}")

            # Write simple completion marker (architecture documenter polls filesystem)
            if self.transcript_writer:
                self.transcript_writer.write_to_file(f"[APPLICATION_ANALYSIS_COMPLETE] {session.description}\n")

            # If all code-analyzers are done, signal completion
            if self.active_code_analyzers == 0:
                logger.info(f"✅ ALL CODE ANALYZERS COMPLETE")
                if self.transcript_writer:
                    self.transcript_writer.write_to_file("[ALL_APPLICATION_ANALYSIS_COMPLETE]\n")

    def set_current_context(self, parent_tool_use_id: Optional[str]):
        """
        Update the current execution context from message stream.

        Args:
            parent_tool_use_id: The parent tool use ID from the current message
        """
        self._current_parent_id = parent_tool_use_id

    def _log_tool_use(self, agent_label: str, tool_name: str, tool_input: Dict[str, Any] = None):
        """
        Helper method to log tool use to console, transcript, and detailed log.

        Args:
            agent_label: Label for the agent (e.g., "RESEARCHER-1", "MAIN AGENT")
            tool_name: Name of the tool being used
            tool_input: Optional tool input parameters for detailed logging
        """
        # Build base message
        message = f"\n[{agent_label}] → {tool_name}"

        # Add tool-specific details for console output
        detail = self._get_tool_detail(tool_name, tool_input)
        console_message = message + (f" {detail}" if detail else "")

        # Log to console
        logger.info(console_message.strip())
        if self.transcript_writer:
            self.transcript_writer.write(console_message)
        else:
            print(console_message, flush=True)

        # Transcript file only: add full input details
        if self.transcript_writer and tool_input:
            full_detail = self._format_tool_input(tool_input)
            if full_detail:
                self.transcript_writer.write_to_file(f"    Input: {full_detail}\n")

    def _get_tool_detail(self, tool_name: str, tool_input: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract human-readable detail for specific tools to show in console."""
        if not tool_input:
            return None

        # Grep - show pattern and optional path
        if tool_name == "Grep":
            pattern = tool_input.get('pattern', '')
            path = tool_input.get('path')
            if path:
                return f"`{pattern}` in {self._format_path(path)}"
            return f"`{pattern}`"

        # File operations - show relative path
        if tool_name in ("Read", "Write") and 'file_path' in tool_input:
            return self._format_path(tool_input['file_path'])

        # Glob - show pattern
        if tool_name == "Glob" and 'pattern' in tool_input:
            return f"`{tool_input['pattern']}`"

        # Bash commands - show truncated command
        if tool_name == "Bash" and 'command' in tool_input:
            command = tool_input['command']
            max_length = 80
            if len(command) > max_length:
                return f"`{command[:max_length]}...`"
            return f"`{command}`"

        return None

    def _format_path(self, file_path: str) -> str:
        """Format a file path as relative if possible, otherwise absolute."""
        try:
            return str(Path(file_path).relative_to(Path.cwd()))
        except ValueError:
            return file_path

    def _format_tool_input(self, tool_input: Dict[str, Any], max_length: int = 100) -> str:
        """Format tool input for human-readable logging."""
        if not tool_input:
            return ""

        # WebSearch: show query
        if 'query' in tool_input:
            query = str(tool_input['query'])
            return f"query='{query if len(query) <= max_length else query[:max_length] + '...'}'"

        # Write: show file path and content size
        if 'file_path' in tool_input and 'content' in tool_input:
            filename = Path(tool_input['file_path']).name
            return f"file='{filename}' ({len(tool_input['content'])} chars)"

        # Read/Glob: show path or pattern
        if 'file_path' in tool_input:
            return f"path='{tool_input['file_path']}'"
        if 'pattern' in tool_input:
            return f"pattern='{tool_input['pattern']}'"

        # Task: show subagent spawn
        if 'subagent_type' in tool_input:
            return f"spawn={tool_input.get('subagent_type', '')} ({tool_input.get('description', '')})"

        # Fallback: generic (truncated)
        return str(tool_input)[:max_length]

    def _log_to_jsonl(self, log_entry: Dict[str, Any]):
        """Write structured log entry to JSONL file."""
        if self.tool_log_file:
            self.tool_log_file.write(json.dumps(log_entry) + "\n")
            self.tool_log_file.flush()

    def _write_analysis_event(self, session: SubagentSession):
        """Write analysis completion event marker to transcript for architecture documenter to poll.

        Args:
            session: The completed code-analyzer subagent session
        """
        if not self.transcript_writer:
            return

        # Extract component name from description (e.g., "Analyze common-utils" -> "common-utils")
        component_name = session.description
        if component_name.startswith("Analyze "):
            component_name = component_name[len("Analyze "):].strip()

        # Determine component type from description or prompt
        # Typical descriptions: "Analyze {component_name}" where prompt contains classification info
        component_type = "unknown"
        prompt_lower = session.prompt_preview.lower()
        desc_lower = session.description.lower()

        if "classification=library" in prompt_lower or "library" in desc_lower:
            component_type = "library"
        elif "classification=application" in prompt_lower or "application" in desc_lower or "-service" in desc_lower:
            component_type = "application"

        # If still unknown, assume it's an application (safer default for incremental processing)
        if component_type == "unknown":
            component_type = "application"

        # Determine phase for libraries (extract from prompt if available)
        phase = None
        if component_type == "library":
            if "phase 1" in session.prompt_preview.lower() or "no dependencies" in session.prompt_preview.lower():
                phase = 1
            elif "phase 2" in session.prompt_preview.lower() or "with dependencies" in session.prompt_preview.lower():
                phase = 2

        # Build event JSON
        event_data = {
            "event": "library_ready" if component_type == "library" else "application_ready",
            "name": component_name,
            "timestamp": session.completed_at
        }
        if phase is not None:
            event_data["phase"] = phase

        # Write event marker to transcript
        event_line = f"[ANALYSIS_EVENT] {json.dumps(event_data)}\n"
        self.transcript_writer.write_to_file(event_line)

    async def pre_tool_use_hook(self, hook_input, tool_use_id, context):
        """Hook callback for PreToolUse events - captures tool calls."""
        tool_name = hook_input['tool_name']
        tool_input = hook_input['tool_input']
        timestamp = datetime.now().isoformat()

        # DEBUG: Log what we're receiving
        if self.verbose or True:  # Always log for now to debug
            logger.info(f"PreToolUse hook fired:")
            logger.info(f"  tool_name: {tool_name}")
            logger.info(f"  tool_use_id: {tool_use_id}")
            logger.info(f"  hook_input keys: {list(hook_input.keys())}")
            logger.info(f"  hook_input full: {hook_input}")
            logger.info(f"  context type: {type(context)}")
            logger.info(f"  context content: {context}")
            logger.info(f"  _current_parent_id: {self._current_parent_id}")

        # Determine agent context
        is_subagent = self._current_parent_id and self._current_parent_id in self.sessions

        if is_subagent:
            session = self.sessions[self._current_parent_id]
            agent_id = session.subagent_id
            agent_type = session.subagent_type
            # Create and store record for subagent
            record = ToolCallRecord(
                timestamp=timestamp,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
                subagent_type=agent_type,
                parent_tool_use_id=self._current_parent_id
            )
            session.tool_calls.append(record)
            self.tool_call_records[tool_use_id] = record

            # Log
            self._log_tool_use(agent_id, tool_name, tool_input)
            self._log_to_jsonl({
                "event": "tool_call_start",
                "timestamp": timestamp,
                "tool_use_id": tool_use_id,
                "agent_id": agent_id,
                "agent_type": agent_type,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "parent_tool_use_id": self._current_parent_id
            })
        elif tool_name != 'Task':  # Skip Task calls for main agent (handled by spawn message)
            # Main agent tool call
            if self.verbose:
                logger.info(f"   Agent: [MAIN AGENT] (lead)")

            self._log_tool_use("MAIN AGENT", tool_name, tool_input)
            self._log_to_jsonl({
                "event": "tool_call_start",
                "timestamp": timestamp,
                "tool_use_id": tool_use_id,
                "agent_id": "MAIN_AGENT",
                "agent_type": "lead",
                "tool_name": tool_name,
                "tool_input": tool_input
            })

        return {'continue_': True}

    async def post_tool_use_hook(self, hook_input, tool_use_id, context):
        """Hook callback for PostToolUse events - captures tool results."""
        tool_response = hook_input.get('tool_response')
        record = self.tool_call_records.get(tool_use_id)

        if not record:
            return {'continue_': True}

        # Update record with output
        record.tool_output = tool_response

        # Check for errors
        error = tool_response.get('error') if isinstance(tool_response, dict) else None
        output_size = len(str(tool_response)) if tool_response else 0

        if error:
            record.error = error
            session = self.sessions.get(record.parent_tool_use_id)
            if session:
                logger.warning(f"[{session.subagent_id}] Tool {record.tool_name} error: {error}")

            # Verbose error logging
            if self.verbose:
                logger.error(f"❌ TOOL ERROR: ID={tool_use_id[:8]}... Error={error}")

        # Get agent info for logging
        session = self.sessions.get(record.parent_tool_use_id)
        agent_id = session.subagent_id if session else "MAIN_AGENT"
        agent_type = session.subagent_type if session else "lead"

        # Verbose completion logging
        if self.verbose:
            status = "✅ SUCCESS" if error is None else "❌ FAILED"
            logger.info(f"{status}: Tool={record.tool_name} ID={tool_use_id[:8]}... Size={output_size} bytes")
            if error is None:
                logger.debug(f"   Output preview: {str(tool_response)[:200]}...")

        # Log completion to JSONL
        self._log_to_jsonl({
            "event": "tool_call_complete",
            "timestamp": datetime.now().isoformat(),
            "tool_use_id": tool_use_id,
            "agent_id": agent_id,
            "agent_type": agent_type,
            "tool_name": record.tool_name,
            "success": error is None,
            "error": error,
            "output_size": output_size
        })

        return {'continue_': True}

    async def post_tool_result_hook(self, hook_input, sdk_agent_id, _context):
        """Hook callback for SubagentStop events - detects subagent completion.

        The SDK provides agent_id (not tool_use_id), so we need to find the matching session.
        We use agent_type from hook_input and find the first incomplete session of that type.
        """
        agent_type = hook_input.get('agent_type', 'unknown')

        # Find the first incomplete session of this type
        # (Sessions complete in order, so first incomplete is the one that just finished)
        matching_tool_use_id = None
        for tool_use_id, session in self.sessions.items():
            if session.subagent_type == agent_type and not session.is_complete:
                matching_tool_use_id = tool_use_id
                break

        if matching_tool_use_id:
            session = self.sessions[matching_tool_use_id]
            print(f"🎯 SubagentStop: {session.subagent_id} (type={agent_type})")

            # Mark complete (this decrements counters and writes events)
            self.mark_subagent_complete(matching_tool_use_id)
        else:
            if self.verbose:
                logger.warning(f"⚠️  SubagentStop for {agent_type} but no incomplete session found")
                logger.warning(f"   SDK agent_id: {sdk_agent_id}")

        return {'continue_': True}

    def close(self):
        """Close the tool log file."""
        if self.tool_log_file:
            self.tool_log_file.close()
