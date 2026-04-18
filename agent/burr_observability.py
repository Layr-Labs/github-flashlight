"""Enhanced observability for Burr-based agent workflows.

Provides:
1. Lifecycle hooks for pre/post action logging with source info
2. Custom tracing for LLM calls with token counts
3. OpenTelemetry integration for external LLM instrumentation

Usage:
    from agent.burr_observability import FlashlightTracker, create_instrumented_app

    app = create_instrumented_app(
        system_prompt="...",
        enable_otel=True,  # Auto-instrument OpenAI/Anthropic calls
    )
"""

import inspect
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from burr.core import State
from burr.core.action import Action
from burr.lifecycle import (
    PostRunStepHook,
    PreRunStepHook,
    PostRunStepHookAsync,
    PreRunStepHookAsync,
)


@dataclass
class ActionTrace:
    """Trace data for a single action execution."""

    action_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None

    # Source identification
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    tags: List[str] = field(default_factory=list)

    # State info
    state_before: Dict[str, Any] = field(default_factory=dict)
    state_after: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None

    # LLM-specific
    token_usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None

    # Error tracking
    error: Optional[str] = None
    sequence_id: Optional[int] = None


class FlashlightTracker(PreRunStepHook, PostRunStepHook):
    """Custom lifecycle hook for enhanced observability.

    Captures:
    - Action source file/line information
    - Tags from action definitions
    - Token usage from LLM actions
    - Timing information
    - State diffs

    Logs to JSONL for our custom dashboard or any external tool.
    """

    def __init__(
        self,
        log_file: Optional[Path] = None,
        verbose: bool = False,
        include_state: bool = True,
        include_source: bool = True,
    ):
        self.log_file = log_file
        self.verbose = verbose
        self.include_state = include_state
        self.include_source = include_source

        self._active_traces: Dict[str, ActionTrace] = {}
        self._all_traces: List[ActionTrace] = []

        # Ensure log file directory exists
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_source_info(self, action: Action) -> tuple[Optional[str], Optional[int]]:
        """Extract source file and line from an action."""
        if not self.include_source:
            return None, None

        try:
            # Try to get the actual function/method
            if hasattr(action, "_fn"):
                fn = action._fn
            elif hasattr(action, "run"):
                fn = action.run
            else:
                return None, None

            source_file = inspect.getfile(fn)
            source_lines, start_line = inspect.getsourcelines(fn)
            return source_file, start_line
        except (TypeError, OSError):
            return None, None

    def _get_tags(self, action: Action) -> List[str]:
        """Extract tags from an action."""
        try:
            return list(action.tags) if action.tags else []
        except Exception:
            return []

    def _sanitize_state(self, state: State) -> Dict[str, Any]:
        """Convert state to a serializable dict, truncating large values."""
        if not self.include_state:
            return {}

        result = {}
        for key in state.keys():
            value = state.get(key)
            # Truncate large strings/lists
            if isinstance(value, str) and len(value) > 500:
                result[key] = value[:500] + "...(truncated)"
            elif isinstance(value, list) and len(value) > 10:
                result[key] = f"[{len(value)} items]"
            elif isinstance(value, dict) and len(str(value)) > 500:
                result[key] = f"{{...{len(value)} keys}}"
            else:
                try:
                    json.dumps(value)  # Check if serializable
                    result[key] = value
                except (TypeError, ValueError):
                    result[key] = str(type(value))
        return result

    def pre_run_step(
        self,
        *,
        state: State,
        action: Action,
        inputs: Dict[str, Any],
        sequence_id: int,
        **future_kwargs: Any,
    ):
        """Called before each action runs."""
        source_file, source_line = self._get_source_info(action)
        tags = self._get_tags(action)

        trace = ActionTrace(
            action_name=action.name,
            start_time=datetime.now(),
            source_file=source_file,
            source_line=source_line,
            tags=tags,
            state_before=self._sanitize_state(state),
            inputs={k: v for k, v in inputs.items() if not k.startswith("_")},
            sequence_id=sequence_id,
        )

        self._active_traces[action.name] = trace

        if self.verbose:
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            source_str = f" @ {source_file}:{source_line}" if source_file else ""
            print(f"[START] {action.name}{tag_str}{source_str}")

    def post_run_step(
        self,
        *,
        state: State,
        action: Action,
        result: Optional[dict],
        sequence_id: int,
        exception: Optional[Exception],
        **future_kwargs: Any,
    ):
        """Called after each action completes."""
        trace = self._active_traces.pop(action.name, None)
        if not trace:
            return

        trace.end_time = datetime.now()
        trace.duration_ms = (trace.end_time - trace.start_time).total_seconds() * 1000
        trace.state_after = self._sanitize_state(state)
        trace.result = result

        if exception:
            trace.error = str(exception)

        # Extract LLM-specific info from state
        token_usage = state.get("token_usage")
        if token_usage:
            trace.token_usage = token_usage

        self._all_traces.append(trace)

        # Log to file
        if self.log_file:
            self._write_trace(trace)

        if self.verbose:
            duration_str = f" ({trace.duration_ms:.1f}ms)" if trace.duration_ms else ""
            error_str = f" ERROR: {trace.error}" if trace.error else ""
            token_str = ""
            if trace.token_usage:
                token_str = f" [tokens: {trace.token_usage.get('input', 0)}in/{trace.token_usage.get('output', 0)}out]"
            print(f"[END] {action.name}{duration_str}{token_str}{error_str}")

    def _write_trace(self, trace: ActionTrace):
        """Write a trace to the JSONL log file."""
        entry = {
            "event": "action_complete",
            "timestamp": trace.end_time.isoformat()
            if trace.end_time
            else trace.start_time.isoformat(),
            "action": trace.action_name,
            "sequence_id": trace.sequence_id,
            "duration_ms": trace.duration_ms,
            "source_file": trace.source_file,
            "source_line": trace.source_line,
            "tags": trace.tags,
            "inputs": trace.inputs,
            "token_usage": trace.token_usage,
            "error": trace.error,
        }

        if self.include_state:
            entry["state_keys_before"] = list(trace.state_before.keys())
            entry["state_keys_after"] = list(trace.state_after.keys())

        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all traced actions."""
        if not self._all_traces:
            return {"total_actions": 0}

        total_duration = sum(t.duration_ms or 0 for t in self._all_traces)
        total_input_tokens = sum(
            (t.token_usage or {}).get("input", 0) for t in self._all_traces
        )
        total_output_tokens = sum(
            (t.token_usage or {}).get("output", 0) for t in self._all_traces
        )

        actions_by_name = {}
        for trace in self._all_traces:
            if trace.action_name not in actions_by_name:
                actions_by_name[trace.action_name] = {
                    "count": 0,
                    "total_duration_ms": 0,
                    "tags": trace.tags,
                    "source": f"{trace.source_file}:{trace.source_line}"
                    if trace.source_file
                    else None,
                }
            actions_by_name[trace.action_name]["count"] += 1
            actions_by_name[trace.action_name]["total_duration_ms"] += (
                trace.duration_ms or 0
            )

        return {
            "total_actions": len(self._all_traces),
            "total_duration_ms": total_duration,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "actions": actions_by_name,
            "errors": [t.error for t in self._all_traces if t.error],
        }


def create_instrumented_app(
    system_prompt: str,
    project_name: str = "flashlight",
    log_dir: Optional[Path] = None,
    enable_otel: bool = False,
    verbose: bool = False,
):
    """Create a Burr application with full observability instrumentation.

    Args:
        system_prompt: System prompt for the agent
        project_name: Project name for Burr tracking
        log_dir: Directory for custom JSONL logs
        enable_otel: Enable OpenTelemetry instrumentation for LLM calls
        verbose: Print trace info to console

    Returns:
        Tuple of (app, tracker) where tracker has get_summary() method
    """
    from agent.burr_app import build_interactive_agent
    from burr.core import ApplicationBuilder

    # Setup custom tracker
    log_file = None
    if log_dir:
        log_file = log_dir / "traces.jsonl"

    tracker = FlashlightTracker(
        log_file=log_file,
        verbose=verbose,
        include_state=True,
        include_source=True,
    )

    # Enable OpenTelemetry if requested
    if enable_otel:
        try:
            from burr.integrations.opentelemetry import init_instruments

            init_instruments("openai", "anthropic", "httpx")
            print("[OTel] Instrumented: openai, anthropic, httpx")
        except ImportError:
            print("[OTel] Warning: opentelemetry packages not installed")

    # Build app with hooks
    # Note: We need to rebuild the app to add hooks
    from agent.burr_app import (
        receive_input,
        call_llm,
        execute_tools,
        respond,
        HAS_TOOLS,
        NO_TOOLS,
    )

    app = (
        ApplicationBuilder()
        .with_actions(
            receive_input=receive_input,
            call_llm=call_llm,
            execute_tools=execute_tools,
            respond=respond,
        )
        .with_transitions(
            ("receive_input", "call_llm"),
            ("call_llm", "execute_tools", HAS_TOOLS),
            ("call_llm", "respond", NO_TOOLS),
            ("execute_tools", "call_llm"),
            ("respond", "receive_input"),
        )
        .with_entrypoint("receive_input")
        .with_state(
            messages=[],
            system_prompt=system_prompt,
            token_usage={"input": 0, "output": 0},
            pending_tool_calls=[],
            has_pending_tools=False,
        )
        .with_tracker(project=project_name, use_otel_tracing=enable_otel)
        .with_hooks(tracker)
        .build()
    )

    return app, tracker


# Example usage showing the @trace decorator for internal function instrumentation
if __name__ == "__main__":
    from burr.visibility import trace

    @trace()
    def example_llm_call(prompt: str) -> str:
        """This function will have its inputs/outputs automatically logged."""
        # Simulated LLM call
        return f"Response to: {prompt}"

    # Demo the tracker
    tracker = FlashlightTracker(verbose=True)
    print("FlashlightTracker initialized")
    print("\nTo use with full OpenTelemetry instrumentation:")
    print("  app, tracker = create_instrumented_app(")
    print("      system_prompt='...',")
    print("      enable_otel=True,")
    print("      verbose=True,")
    print("  )")
