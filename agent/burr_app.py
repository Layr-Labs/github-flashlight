"""Burr-based agent implementation for Flashlight.

Replaces LangGraph with Burr's explicit state machine paradigm.
Key benefits:
- Explicit state/transitions (no inference needed for observability)
- Built-in tracking UI
- State persistence/checkpointing

Architecture:
    INTERACTIVE MODE (CLI chat):
        receive_input -> call_llm -> [execute_tools -> call_llm]* -> respond

    ANALYSIS MODE (headless codebase analysis):
        receive_input -> read_discovery -> analyze_depth_N -> ... -> synthesize -> respond

        Each analyze_depth_N action:
        - Runs component analyzers in parallel for all components at that depth
        - Each component analyzer is a ReAct loop (call_llm <-> execute_tools)
        - Waits for all to complete before transitioning to next depth

Multi-agent visibility:
    The Burr UI shows:
    - receive_input: Initial task
    - read_discovery: Load components.json and analysis_order.json
    - analyze_depth_0: Parallel analysis of depth-0 components
    - analyze_depth_1: Parallel analysis of depth-1 components (with upstream context)
    - ... (more depth levels as needed)
    - synthesize: Architecture documentation synthesis
    - respond: Final output
"""

import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx
from burr.core import Application, ApplicationBuilder, State, action, expr

if TYPE_CHECKING:
    from burr.visibility import TracerFactory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")


def get_api_key() -> str:
    """Get OpenRouter API key from environment."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Get one at https://openrouter.ai/keys"
        )
    return key


# ---------------------------------------------------------------------------
# Tool implementations (framework-agnostic)
# ---------------------------------------------------------------------------


def tool_read_file(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read a file from the local filesystem."""
    from pathlib import Path

    p = Path(file_path)
    if not p.exists():
        return f"Error: path does not exist: {file_path}"

    if p.is_dir():
        entries = sorted(p.iterdir())
        lines = [entry.name + ("/" if entry.is_dir() else "") for entry in entries]
        return "\n".join(lines) if lines else "(empty directory)"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading {file_path}: {exc}"

    all_lines = text.splitlines(keepends=True)
    total = len(all_lines)
    start = max(0, offset - 1)
    end = start + limit
    selected = all_lines[start:end]

    result_lines = []
    for i, line in enumerate(selected, start=start + 1):
        content = line.rstrip("\n\r")
        if len(content) > 2000:
            content = content[:2000] + "... (truncated)"
        result_lines.append(f"{i}: {content}")

    result = "\n".join(result_lines)
    if end < total:
        result += f"\n\n(Showing lines {offset}-{end} of {total} total lines)"
    return result


def tool_write_file(file_path: str, content: str) -> str:
    """Write content to a file."""
    from pathlib import Path

    p = Path(file_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {file_path}"
    except Exception as exc:
        return f"Error writing {file_path}: {exc}"


def tool_glob_files(pattern: str, path: Optional[str] = None) -> str:
    """Find files matching a glob pattern."""
    from pathlib import Path

    base = Path(path) if path else Path.cwd()
    if not base.exists():
        return f"Error: directory does not exist: {base}"

    try:
        matches = sorted(base.glob(pattern))
        files = [str(m) for m in matches if m.is_file()]
        if not files:
            return f"No files found matching pattern '{pattern}' in {base}"
        if len(files) > 500:
            result = "\n".join(files[:500])
            result += f"\n\n... and {len(files) - 500} more files (truncated)"
            return result
        return "\n".join(files)
    except Exception as exc:
        return f"Error searching for pattern '{pattern}': {exc}"


def tool_grep_files(
    pattern: str, path: Optional[str] = None, include: Optional[str] = None
) -> str:
    """Search file contents using a regular expression."""
    import subprocess
    from pathlib import Path

    base = Path(path) if path else Path.cwd()
    if not base.exists():
        return f"Error: directory does not exist: {base}"

    cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
    if include:
        cmd.extend(["--glob", include])
    cmd.append(pattern)
    cmd.append(str(base))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if not output:
            return f"No matches found for pattern '{pattern}' in {base}"
        lines = output.split("\n")
        if len(lines) > 500:
            output = "\n".join(lines[:500])
            output += f"\n\n... and {len(lines) - 500} more matches (truncated)"
        return output
    except FileNotFoundError:
        return f"Error: ripgrep (rg) not found. Install it for fast search."
    except subprocess.TimeoutExpired:
        return "Error: search timed out after 30 seconds"
    except Exception as exc:
        return f"Error searching: {exc}"


def tool_bash(command: str, workdir: Optional[str] = None, timeout: int = 120) -> str:
    """Execute a bash command and return its output."""
    import subprocess

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += f"STDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n(exit code: {result.returncode})"

        if len(output) > 100_000:
            output = output[:100_000] + "\n... (output truncated at 100KB)"
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout} seconds"
    except Exception as exc:
        return f"Error executing command: {exc}"


# Tool registry for the LLM
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the local filesystem. Returns contents with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start from (1-indexed)",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max lines to return",
                        "default": 2000,
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating parent directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file",
                    },
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "Find files matching a glob pattern like '**/*.py'",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match",
                    },
                    "path": {"type": "string", "description": "Directory to search in"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "Search file contents using a regular expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {"type": "string", "description": "Directory to search in"},
                    "include": {
                        "type": "string",
                        "description": "File pattern filter (e.g., '*.py')",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a bash command and return its output",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                    "workdir": {"type": "string", "description": "Working directory"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 120,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_subagent",
            "description": "Spawn a subagent to analyze a component. The subagent runs its own ReAct loop and returns when complete. Multiple spawn_subagent calls in the same response will run in PARALLEL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_type": {
                        "type": "string",
                        "enum": [
                            "component-analyzer",
                            "architecture-documenter",
                            "external-service-analyzer",
                        ],
                        "description": "Type of subagent to spawn",
                    },
                    "component_name": {
                        "type": "string",
                        "description": "Name of the component to analyze",
                    },
                    "component_kind": {
                        "type": "string",
                        "enum": [
                            "library",
                            "service",
                            "cli",
                            "contract",
                            "infra",
                            "pipeline",
                            "frontend",
                            "unknown",
                        ],
                        "description": "Kind of component (from ComponentKind)",
                    },
                    "component_type": {
                        "type": "string",
                        "description": "Language type (e.g., go-module, rust-crate, python-package)",
                    },
                    "component_path": {
                        "type": "string",
                        "description": "Relative path to the component root",
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service being analyzed (for /tmp/{service_name}/)",
                    },
                    "component_description": {
                        "type": "string",
                        "description": "Optional description of the component",
                    },
                    "dependency_list": {
                        "type": "string",
                        "description": "Comma-separated list of direct internal dependencies (for components at depth > 0)",
                    },
                    "upstream_context": {
                        "type": "string",
                        "description": "Summaries of dependency analyses to provide context (for depth > 0)",
                    },
                },
                "required": [
                    "subagent_type",
                    "component_name",
                    "component_kind",
                    "component_type",
                    "component_path",
                    "service_name",
                ],
            },
        },
    },
]


def tool_spawn_subagent(
    subagent_type: str,
    component_name: str,
    component_kind: str,
    component_type: str,
    component_path: str,
    service_name: str,
    component_description: str = "",
    dependency_list: str = "",
    upstream_context: str = "",
) -> str:
    """Spawn a subagent to analyze a component.

    This runs a complete ReAct loop for the subagent with its own system prompt.
    The subagent has access to the same tools (read, write, glob, grep, bash)
    but NOT spawn_subagent (no recursive spawning).

    Args:
        subagent_type: One of "component-analyzer", "architecture-documenter", "external-service-analyzer"
        component_name: Name of the component being analyzed
        component_kind: ComponentKind value (library, service, cli, etc.)
        component_type: Language type (go-module, rust-crate, etc.)
        component_path: Relative path to component root
        service_name: Name of the service being analyzed (for /tmp/{service_name}/)
        component_description: Optional description of the component
        dependency_list: Comma-separated list of direct dependencies (for depth > 0)
        upstream_context: Summaries of dependency analyses (for depth > 0)

    Returns:
        The final response from the subagent, or error message.
    """
    from pathlib import Path

    # Load the appropriate prompt template
    prompts_dir = Path(__file__).parent / "prompts" / "subagents"

    # Select prompt based on subagent type and whether it has dependencies
    if subagent_type == "component-analyzer":
        if dependency_list:
            prompt_file = prompts_dir / "component_analyzer.txt"
        else:
            prompt_file = prompts_dir / "component_analyzer_depth0.txt"
    elif subagent_type == "architecture-documenter":
        prompt_file = prompts_dir / "architecture_documenter.txt"
    elif subagent_type == "external-service-analyzer":
        prompt_file = prompts_dir / "external_service_analyzer.txt"
    else:
        return f"Error: Unknown subagent type '{subagent_type}'"

    if not prompt_file.exists():
        return f"Error: Prompt file not found: {prompt_file}"

    try:
        prompt_template = prompt_file.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading prompt file: {e}"

    # Substitute placeholders using string replacement
    # (can't use .format() because templates have JSON examples with curly braces)
    prompt = prompt_template
    prompt = prompt.replace("{component_name}", component_name)
    prompt = prompt.replace("{component_kind}", component_kind)
    prompt = prompt.replace("{component_type}", component_type)
    prompt = prompt.replace("{component_path}", component_path)
    prompt = prompt.replace(
        "{component_description}", component_description or "(no description)"
    )
    prompt = prompt.replace("{dependency_list}", dependency_list or "(none)")
    prompt = prompt.replace(
        "{upstream_context}", upstream_context or "(no upstream context)"
    )
    prompt = prompt.replace("{SERVICE_NAME}", service_name)

    # Run the subagent as a proper Burr Application
    # This creates visibility in the Burr UI with parent/child relationship
    result = _run_subagent_as_app(
        system_prompt=f"You are a {subagent_type} for the {service_name} codebase.",
        user_prompt=prompt,
        subagent_type=subagent_type,
        component_name=component_name,
        # TODO: Pass parent_app_id and parent_sequence_id from execution context
        # For now, subagents appear as top-level apps in the UI
    )

    return result


def _build_subagent_app(
    system_prompt: str,
    subagent_type: str,
    component_name: str,
    parent_app_id: str = "",
    parent_sequence_id: int = 0,
) -> Application:
    """Build a Burr Application for a subagent.

    This creates a proper tracked Burr app that shows up in the UI
    with a parent/child relationship to the lead agent.
    """
    # Subagent tools - no spawn_subagent (prevent recursion)
    subagent_tools = [
        t for t in AVAILABLE_TOOLS if t["function"]["name"] != "spawn_subagent"
    ]

    # Create subagent-specific versions of call_llm and execute_tools
    # that use the filtered tool list
    @action(
        reads=["messages", "system_prompt"],
        writes=["messages", "llm_response", "pending_tool_calls", "has_pending_tools"],
        tags=[f"subagent:{subagent_type}", f"component:{component_name}"],
    )
    def subagent_call_llm(state: State) -> State:
        messages = state.get("messages", [])
        sys_prompt = state.get("system_prompt", "")

        api_messages = [{"role": "system", "content": sys_prompt}] + messages

        response = call_openrouter(
            messages=api_messages,
            tools=subagent_tools,
        )

        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])

        assistant_msg = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        return state.update(
            messages=messages + [assistant_msg],
            llm_response=content,
            pending_tool_calls=tool_calls,
            has_pending_tools=len(tool_calls) > 0,
        )

    @action(
        reads=["pending_tool_calls", "messages"],
        writes=["messages", "pending_tool_calls", "has_pending_tools"],
        tags=[f"subagent:{subagent_type}", f"component:{component_name}"],
    )
    def subagent_execute_tools(state: State) -> State:
        tool_calls = state.get("pending_tool_calls", [])
        messages = list(state.get("messages", []))

        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_id = tool_call["id"]

            try:
                tool_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": f"Error parsing arguments: {e}",
                    }
                )
                continue

            if tool_name in SUBAGENT_TOOL_FUNCTIONS:
                try:
                    result = SUBAGENT_TOOL_FUNCTIONS[tool_name](**tool_args)
                except Exception as e:
                    result = f"Error: {e}"
            else:
                result = f"Unknown tool: {tool_name}"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result,
                }
            )

        return state.update(
            messages=messages,
            pending_tool_calls=[],
            has_pending_tools=False,
        )

    @action(reads=[], writes=["messages"], tags=[f"subagent:{subagent_type}"])
    def subagent_receive_input(state: State, user_input: str) -> State:
        return state.update(messages=[{"role": "user", "content": user_input}])

    @action(
        reads=["llm_response"],
        writes=["final_response"],
        tags=[f"subagent:{subagent_type}"],
    )
    def subagent_respond(state: State) -> State:
        return state.update(final_response=state.get("llm_response", ""))

    # Build the application
    builder = (
        ApplicationBuilder()
        .with_actions(
            receive_input=subagent_receive_input,
            call_llm=subagent_call_llm,
            execute_tools=subagent_execute_tools,
            respond=subagent_respond,
        )
        .with_transitions(
            ("receive_input", "call_llm"),
            ("call_llm", "execute_tools", HAS_TOOLS),
            ("call_llm", "respond", NO_TOOLS),
            ("execute_tools", "call_llm"),
        )
        .with_entrypoint("receive_input")
        .with_state(
            messages=[],
            system_prompt=system_prompt,
            pending_tool_calls=[],
            has_pending_tools=False,
        )
        .with_tracker(project="flashlight")
        .with_identifiers(app_id=f"subagent-{subagent_type}-{component_name}")
    )

    # Add parent relationship if provided
    if parent_app_id:
        builder = builder.with_spawning_parent(
            app_id=parent_app_id,
            sequence_id=parent_sequence_id,
        )

    return builder.build()


def _run_subagent_as_app(
    system_prompt: str,
    user_prompt: str,
    subagent_type: str,
    component_name: str,
    parent_app_id: str = "",
    parent_sequence_id: int = 0,
) -> str:
    """Run a subagent as a proper Burr Application.

    This creates visibility in the Burr UI with parent/child relationship.
    """
    app = _build_subagent_app(
        system_prompt=system_prompt,
        subagent_type=subagent_type,
        component_name=component_name,
        parent_app_id=parent_app_id,
        parent_sequence_id=parent_sequence_id,
    )

    try:
        action, result, state = app.run(
            halt_after=["respond"],
            inputs={"user_input": user_prompt},
        )
        return state.get("final_response", "(no response)")
    except Exception as e:
        logger.error(f"Subagent {subagent_type}:{component_name} failed: {e}")
        return f"Error: {e}"


def _run_subagent_loop(
    system_prompt: str,
    user_prompt: str,
    subagent_type: str,
    component_name: str,
    max_iterations: int = 50,
) -> str:
    """Run a ReAct loop for a subagent.

    DEPRECATED: Use _run_subagent_as_app for proper Burr UI visibility.
    This is kept as a lightweight fallback.

    Args:
        system_prompt: System prompt for the subagent
        user_prompt: The analysis task prompt
        subagent_type: Type of subagent (for logging)
        component_name: Name of component being analyzed (for logging)
        max_iterations: Maximum tool call iterations

    Returns:
        The final text response from the subagent
    """
    # Subagent tools - same as main agent but NO spawn_subagent
    subagent_tools = [
        t for t in AVAILABLE_TOOLS if t["function"]["name"] != "spawn_subagent"
    ]

    messages = [
        {"role": "user", "content": user_prompt},
    ]

    api_messages = [{"role": "system", "content": system_prompt}] + messages

    for iteration in range(max_iterations):
        logger.info(
            f"[{subagent_type}:{component_name}] Iteration {iteration + 1}/{max_iterations}"
        )

        try:
            response = call_openrouter(
                messages=api_messages,
                tools=subagent_tools,
            )
        except Exception as e:
            logger.error(f"[{subagent_type}:{component_name}] LLM call failed: {e}")
            return f"Error: LLM call failed after {iteration + 1} iterations: {e}"

        content = response["content"]
        tool_calls = response["tool_calls"]

        # Add assistant message
        assistant_msg = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        api_messages.append(assistant_msg)

        # If no tool calls, we're done
        if not tool_calls:
            logger.info(
                f"[{subagent_type}:{component_name}] Completed after {iteration + 1} iterations"
            )
            return content or "(no response)"

        # Execute tool calls
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_id = tool_call["id"]

            try:
                tool_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                tool_result = f"Error parsing tool arguments: {e}"
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": tool_result,
                    }
                )
                continue

            # Execute the tool (but not spawn_subagent)
            if tool_name in SUBAGENT_TOOL_FUNCTIONS:
                try:
                    tool_result = SUBAGENT_TOOL_FUNCTIONS[tool_name](**tool_args)
                except Exception as e:
                    tool_result = f"Error executing {tool_name}: {e}"
            else:
                tool_result = f"Unknown tool: {tool_name}"

            api_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result,
                }
            )

    logger.warning(
        f"[{subagent_type}:{component_name}] Hit max iterations ({max_iterations})"
    )
    return f"Error: Subagent hit maximum iterations ({max_iterations})"


# Tool functions available to subagents (no spawn_subagent)
SUBAGENT_TOOL_FUNCTIONS = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "glob_files": tool_glob_files,
    "grep_files": tool_grep_files,
    "bash": tool_bash,
}

# Tool functions for the lead agent (includes spawn_subagent)
TOOL_FUNCTIONS = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "glob_files": tool_glob_files,
    "grep_files": tool_grep_files,
    "bash": tool_bash,
    "spawn_subagent": tool_spawn_subagent,
}


# ---------------------------------------------------------------------------
# OpenRouter LLM client
# ---------------------------------------------------------------------------


def call_openrouter(
    messages: List[Dict[str, Any]],
    model: str = DEFAULT_MODEL,
    tools: Optional[List[Dict]] = None,
    max_tokens: int = 16384,
    timeout: float = 600.0,
    max_retries: int = 3,
    initial_retry_delay: float = 2.0,
) -> Dict[str, Any]:
    """Call OpenRouter API and return the response with retry logic.

    Implements exponential backoff for transient failures:
    - Timeouts (httpx.TimeoutException)
    - Rate limits (429)
    - Server errors (5xx)

    Args:
        messages: Conversation messages
        model: Model identifier
        tools: Optional tool definitions
        max_tokens: Maximum tokens in response
        timeout: Request timeout in seconds (default 600s for large contexts)
        max_retries: Maximum retry attempts (default 3)
        initial_retry_delay: Initial delay between retries in seconds

    Returns dict with:
        - content: str (text response)
        - tool_calls: list (if any)
        - usage: dict (token counts)
        - model: str
        - finish_reason: str

    Raises:
        httpx.HTTPStatusError: On non-retryable HTTP errors (4xx except 429)
        RuntimeError: On exhausted retries
    """
    api_key = get_api_key()

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/anthropics/flashlight",
        "X-Title": "flashlight",
    }

    last_exception: Optional[Exception] = None
    retry_delay = initial_retry_delay

    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )

                # Check for retryable HTTP errors
                if response.status_code == 429:
                    # Rate limited - check for Retry-After header
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            retry_delay = float(retry_after)
                        except ValueError:
                            pass  # Use exponential backoff delay
                    raise httpx.HTTPStatusError(
                        f"Rate limited (429)",
                        request=response.request,
                        response=response,
                    )

                if response.status_code >= 500:
                    # Server error - retryable
                    raise httpx.HTTPStatusError(
                        f"Server error ({response.status_code})",
                        request=response.request,
                        response=response,
                    )

                # Non-retryable errors (4xx except 429)
                response.raise_for_status()
                data = response.json()

            choice = data["choices"][0]
            message = choice["message"]

            return {
                "content": message.get("content", ""),
                "tool_calls": message.get("tool_calls", []),
                "usage": data.get("usage", {}),
                "model": data.get("model", model),
                "finish_reason": choice.get("finish_reason", ""),
            }

        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_exception = e
            is_timeout = isinstance(e, httpx.TimeoutException)
            is_retryable_http = isinstance(e, httpx.HTTPStatusError) and (
                e.response.status_code == 429 or e.response.status_code >= 500
            )

            if attempt < max_retries and (is_timeout or is_retryable_http):
                error_type = (
                    "timeout" if is_timeout else f"HTTP {e.response.status_code}"
                )
                logger.warning(
                    f"OpenRouter request failed ({error_type}), "
                    f"retrying in {retry_delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                )
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                raise

        except httpx.RequestError as e:
            # Network errors (connection refused, DNS failure, etc.)
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f"OpenRouter request failed (network error: {e}), "
                    f"retrying in {retry_delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                )
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                raise

    # Should not reach here, but just in case
    raise RuntimeError(
        f"OpenRouter request failed after {max_retries + 1} attempts: {last_exception}"
    )


# ---------------------------------------------------------------------------
# Burr Actions - Interactive Mode (ReAct loop)
# ---------------------------------------------------------------------------


@action(
    reads=["messages", "system_prompt"],
    writes=[
        "messages",
        "llm_response",
        "pending_tool_calls",
        "has_pending_tools",
        "token_usage",
    ],
    tags=["pattern:react", "component:llm", "source:agent/burr_app.py:call_llm"],
)
def call_llm(state: State, __tracer: "TracerFactory") -> State:
    """Call the LLM with the current conversation history.

    This is the core LLM action - it sends messages to OpenRouter and
    processes the response, extracting any tool calls.

    Sets has_pending_tools boolean for transition conditions.
    Source: agent/burr_app.py
    Pattern: ReAct (Reasoning + Acting)

    Uses __tracer for nested span visibility into:
    - Message preparation
    - OpenRouter API call (with token/model details)
    - Response processing
    """
    messages = state.get("messages", [])
    system_prompt = state.get("system_prompt", "You are a helpful assistant.")

    # Span: Build messages array
    with __tracer("prepare_messages") as t:
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages)
        t.log_attributes(
            message_count=len(api_messages),
            system_prompt_length=len(system_prompt),
            has_tools=True,
        )

    # Span: Call the LLM via OpenRouter
    with __tracer("openrouter_api_call", span_dependencies=["prepare_messages"]) as t:
        model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        t.log_attributes(model=model, tool_count=len(AVAILABLE_TOOLS))

        response = call_openrouter(
            messages=api_messages,
            tools=AVAILABLE_TOOLS,
        )

        # Log response details
        usage = response["usage"]
        t.log_attributes(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=response.get("finish_reason", "unknown"),
            has_tool_calls=len(response["tool_calls"]) > 0,
            response_model=response.get("model", model),
        )

    # Span: Process response
    with __tracer("process_response", span_dependencies=["openrouter_api_call"]) as t:
        content = response["content"]
        tool_calls = response["tool_calls"]

        # Track token usage
        current_usage = state.get("token_usage", {"input": 0, "output": 0})
        new_usage = {
            "input": current_usage["input"] + usage.get("prompt_tokens", 0),
            "output": current_usage["output"] + usage.get("completion_tokens", 0),
        }

        # Build assistant message
        assistant_message = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls

        new_messages = messages + [assistant_message]
        has_pending = len(tool_calls) > 0

        t.log_attributes(
            response_length=len(content) if content else 0,
            tool_call_count=len(tool_calls),
            has_pending_tools=has_pending,
            cumulative_input_tokens=new_usage["input"],
            cumulative_output_tokens=new_usage["output"],
        )

    return state.update(
        messages=new_messages,
        llm_response=content,
        pending_tool_calls=tool_calls,
        has_pending_tools=has_pending,
        token_usage=new_usage,
    )


@action(
    reads=["pending_tool_calls", "messages"],
    writes=["messages", "pending_tool_calls", "has_pending_tools", "tool_results"],
    tags=[
        "pattern:react",
        "component:tool_executor",
        "source:agent/burr_app.py:execute_tools",
    ],
)
def execute_tools(state: State, __tracer: "TracerFactory") -> State:
    """Execute pending tool calls and add results to conversation.

    This action handles the "Act" part of ReAct - executing each tool
    and formatting the results for the LLM.

    Source: agent/burr_app.py
    Pattern: ReAct - Tool Execution

    Uses __tracer to create a span for each individual tool execution.
    """
    tool_calls = state.get("pending_tool_calls", [])
    messages = state.get("messages", [])

    tool_results = []
    new_messages = list(messages)

    # Log overview
    __tracer.log_attributes(
        total_tool_calls=len(tool_calls),
        tool_names=[tc["function"]["name"] for tc in tool_calls],
    )

    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call["function"]["name"]
        tool_args = json.loads(tool_call["function"]["arguments"])
        tool_id = tool_call["id"]

        # Create a span for each tool execution
        with __tracer(f"tool:{tool_name}") as t:
            t.log_attributes(
                tool_index=i,
                tool_id=tool_id,
                tool_args=tool_args,
            )

            # Execute the tool
            if tool_name in TOOL_FUNCTIONS:
                try:
                    result = TOOL_FUNCTIONS[tool_name](**tool_args)
                    t.log_attributes(
                        success=True,
                        result_length=len(result) if isinstance(result, str) else None,
                    )
                except Exception as e:
                    result = f"Error executing {tool_name}: {e}"
                    t.log_attributes(success=False, error=str(e))
            else:
                result = f"Unknown tool: {tool_name}"
                t.log_attributes(success=False, error="unknown_tool")

        tool_results.append(
            {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": result,
            }
        )

        # Add tool result message
        new_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result,
            }
        )

    return state.update(
        messages=new_messages,
        pending_tool_calls=[],  # Clear pending
        has_pending_tools=False,  # Clear the boolean flag
        tool_results=tool_results,
    )


@action(
    reads=["messages"],
    writes=["messages"],
    tags=["component:input", "source:agent/burr_app.py:receive_input"],
)
def receive_input(state: State, user_input: str) -> State:
    """Add user input to the conversation.

    user_input is passed as a runtime input (not from state).

    Source: agent/burr_app.py
    """
    messages = state.get("messages", [])

    new_messages = messages + [{"role": "user", "content": user_input}]

    return state.update(messages=new_messages)


@action(
    reads=["llm_response"],
    writes=["final_response"],
    tags=["component:output", "source:agent/burr_app.py:respond"],
)
def respond(state: State) -> State:
    """Extract final response for the user.

    Source: agent/burr_app.py
    """
    return state.update(final_response=state.get("llm_response", ""))


# ---------------------------------------------------------------------------
# Transition conditions (using Burr's expr() syntax)
# ---------------------------------------------------------------------------

# We store 'has_pending_tools' boolean in state for cleaner condition expressions
HAS_TOOLS = expr("has_pending_tools == True")
NO_TOOLS = expr("has_pending_tools == False")

# Analysis mode conditions
HAS_MORE_DEPTHS = expr("current_depth < total_depths")
NO_MORE_DEPTHS = expr("current_depth >= total_depths")


# ---------------------------------------------------------------------------
# Burr Actions - Analysis Mode (structured multi-agent workflow)
# ---------------------------------------------------------------------------


@action(
    reads=["service_name"],
    writes=[
        "components",
        "depth_order",
        "current_depth",
        "total_depths",
        "component_analyses",
    ],
    tags=[
        "phase:discovery",
        "component:orchestrator",
        "source:agent/burr_app.py:read_discovery",
    ],
)
def read_discovery(state: State, __tracer: "TracerFactory") -> State:
    """Load pre-built discovery results.

    Reads:
    - /tmp/{service_name}/service_discovery/components.json
    - /tmp/{service_name}/dependency_graphs/analysis_order.json

    Populates state with components and depth ordering for analysis.
    """
    from pathlib import Path

    service_name = state.get("service_name", "unknown")
    work_dir = Path(f"/tmp/{service_name}")
    components_file = work_dir / "service_discovery" / "components.json"
    analysis_order_file = work_dir / "dependency_graphs" / "analysis_order.json"

    with __tracer("load_components") as t:
        if not components_file.exists():
            raise FileNotFoundError(f"Components file not found: {components_file}")

        with open(components_file) as f:
            components_data = json.load(f)

        # Handle both list and dict formats
        if isinstance(components_data, dict):
            components = components_data.get("components", [])
        else:
            components = components_data

        t.log_attributes(component_count=len(components))

    with __tracer("load_analysis_order") as t:
        if not analysis_order_file.exists():
            raise FileNotFoundError(
                f"Analysis order file not found: {analysis_order_file}"
            )

        with open(analysis_order_file) as f:
            analysis_order = json.load(f)

        depth_order = analysis_order.get("depth_levels", [])
        t.log_attributes(
            depth_count=len(depth_order),
            total_components=sum(len(level) for level in depth_order),
        )

    # Build component lookup by name
    component_map = {c["name"]: c for c in components}

    return state.update(
        components=component_map,
        depth_order=depth_order,
        current_depth=0,
        total_depths=len(depth_order),
        component_analyses={},  # Will be populated as we analyze
    )


@action(
    reads=[
        "components",
        "depth_order",
        "current_depth",
        "component_analyses",
        "service_name",
    ],
    writes=["component_analyses", "current_depth"],
    tags=[
        "phase:analysis",
        "component:orchestrator",
        "source:agent/burr_app.py:analyze_current_depth",
    ],
)
def analyze_current_depth(state: State, __tracer: "TracerFactory") -> State:
    """Analyze all components at the current depth level.

    For each component at this depth:
    1. Build upstream context from already-analyzed dependencies
    2. Run a component analyzer ReAct loop
    3. Store the analysis result

    Components at the same depth are analyzed sequentially in this implementation.
    (Future: could use threading for true parallelism)
    """
    from pathlib import Path

    components = state.get("components", {})
    depth_order = state.get("depth_order", [])
    current_depth = state.get("current_depth", 0)
    analyses = dict(state.get("component_analyses", {}))
    service_name = state.get("service_name", "unknown")

    if current_depth >= len(depth_order):
        # No more depths to analyze
        return state.update(current_depth=current_depth)

    component_names = depth_order[current_depth]

    __tracer.log_attributes(
        depth=current_depth,
        component_count=len(component_names),
        component_names=component_names,
    )

    for comp_name in component_names:
        comp = components.get(comp_name)
        if not comp:
            logger.warning(f"Component not found in inventory: {comp_name}")
            continue

        with __tracer(f"analyze:{comp_name}") as t:
            # Build upstream context from dependencies
            upstream_context = ""
            deps = comp.get("internal_dependencies", [])
            if deps:
                context_parts = []
                for dep_name in deps:
                    if dep_name in analyses:
                        # Extract summary from the analysis
                        analysis = analyses[dep_name]
                        summary = _extract_summary(analysis)
                        context_parts.append(f"### {dep_name}\n{summary}")
                upstream_context = "\n\n".join(context_parts)

            t.log_attributes(
                component_kind=comp.get("kind", "unknown"),
                component_type=comp.get("type", "unknown"),
                dependency_count=len(deps),
                has_upstream_context=bool(upstream_context),
            )

            # Run the component analyzer
            analysis_result = _run_component_analyzer(
                component=comp,
                service_name=service_name,
                upstream_context=upstream_context,
                tracer=t,
            )

            analyses[comp_name] = analysis_result

            t.log_attributes(
                analysis_length=len(analysis_result) if analysis_result else 0,
                success=bool(
                    analysis_result and not analysis_result.startswith("Error")
                ),
            )

    return state.update(
        component_analyses=analyses,
        current_depth=current_depth + 1,
    )


def _extract_summary(analysis: str) -> str:
    """Extract a brief summary from a component analysis."""
    # Look for a summary section or take first few paragraphs
    lines = analysis.split("\n")
    summary_lines = []
    in_summary = False

    for line in lines:
        if "## Summary" in line or "## Overview" in line:
            in_summary = True
            continue
        if in_summary:
            if line.startswith("## "):
                break
            if line.strip():
                summary_lines.append(line)
            if len(summary_lines) >= 5:
                break

    if summary_lines:
        return "\n".join(summary_lines)

    # Fallback: first non-empty paragraph
    for line in lines:
        if line.strip() and not line.startswith("#"):
            return line[:500]

    return "(no summary available)"


def _run_component_analyzer(
    component: Dict[str, Any],
    service_name: str,
    upstream_context: str,
    tracer: Any,
    parent_app_id: str = "",
    parent_sequence_id: int = 0,
) -> str:
    """Run a component analyzer as a proper Burr Application.

    This creates visibility in the Burr UI for each component being analyzed.
    """
    from pathlib import Path

    comp_name = component.get("name", "unknown")
    comp_kind = component.get("kind", "unknown")
    comp_type = component.get("type", "unknown")
    comp_path = component.get("root_path", "")
    comp_desc = component.get("description", "")
    deps = component.get("internal_dependencies", [])

    # Load prompt template
    prompts_dir = Path(__file__).parent / "prompts" / "subagents"
    if deps or upstream_context:
        prompt_file = prompts_dir / "component_analyzer.txt"
    else:
        prompt_file = prompts_dir / "component_analyzer_depth0.txt"

    if not prompt_file.exists():
        return f"Error: Prompt file not found: {prompt_file}"

    try:
        prompt_template = prompt_file.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading prompt file: {e}"

    # Substitute placeholders using simple string replacement
    prompt = prompt_template
    prompt = prompt.replace("{component_name}", comp_name)
    prompt = prompt.replace("{component_kind}", comp_kind)
    prompt = prompt.replace("{component_type}", comp_type)
    prompt = prompt.replace("{component_path}", comp_path)
    prompt = prompt.replace("{component_description}", comp_desc or "(no description)")
    prompt = prompt.replace("{dependency_list}", ", ".join(deps) if deps else "(none)")
    prompt = prompt.replace(
        "{upstream_context}", upstream_context or "(no upstream context)"
    )
    prompt = prompt.replace("{SERVICE_NAME}", service_name)

    system_prompt = f"You are a component-analyzer for the {service_name} codebase."

    # Run as a proper Burr application for UI visibility
    return _run_subagent_as_app(
        system_prompt=system_prompt,
        user_prompt=prompt,
        subagent_type="component-analyzer",
        component_name=comp_name,
        parent_app_id=parent_app_id,
        parent_sequence_id=parent_sequence_id,
    )


@action(
    reads=["component_analyses", "service_name"],
    writes=["synthesis_result"],
    tags=[
        "phase:synthesis",
        "component:orchestrator",
        "source:agent/burr_app.py:synthesize",
    ],
)
def synthesize(state: State, __tracer: "TracerFactory") -> State:
    """Synthesize all component analyses into architecture documentation.

    Runs the architecture-documenter subagent to create:
    - architecture.md
    - quick_reference.md
    """
    from pathlib import Path

    analyses = state.get("component_analyses", {})
    service_name = state.get("service_name", "unknown")

    __tracer.log_attributes(
        component_count=len(analyses),
        service_name=service_name,
    )

    # Load architecture documenter prompt
    prompts_dir = Path(__file__).parent / "prompts" / "subagents"
    prompt_file = prompts_dir / "architecture_documenter.txt"

    if not prompt_file.exists():
        return state.update(synthesis_result=f"Error: Prompt not found: {prompt_file}")

    try:
        prompt_template = prompt_file.read_text(encoding="utf-8")
    except Exception as e:
        return state.update(synthesis_result=f"Error reading prompt: {e}")

    # Build analysis summary for the prompt
    analysis_summaries = []
    for name, analysis in analyses.items():
        summary = _extract_summary(analysis)
        analysis_summaries.append(f"### {name}\n{summary}")

    # Substitute placeholders using string replacement
    prompt = prompt_template
    prompt = prompt.replace("{SERVICE_NAME}", service_name)
    prompt = prompt.replace("{component_summaries}", "\n\n".join(analysis_summaries))

    system_prompt = (
        f"You are an architecture-documenter for the {service_name} codebase."
    )

    # Run the synthesizer (simpler - usually doesn't need many tool calls)
    subagent_tools = [
        t for t in AVAILABLE_TOOLS if t["function"]["name"] != "spawn_subagent"
    ]

    messages = [{"role": "user", "content": prompt}]
    api_messages = [{"role": "system", "content": system_prompt}] + messages

    max_iterations = 20
    for iteration in range(max_iterations):
        with __tracer(f"synth_iteration_{iteration}") as iter_t:
            try:
                response = call_openrouter(
                    messages=api_messages,
                    tools=subagent_tools,
                )
            except Exception as e:
                iter_t.log_attributes(error=str(e))
                return state.update(synthesis_result=f"Error: LLM call failed: {e}")

            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            iter_t.log_attributes(
                has_content=bool(content),
                tool_call_count=len(tool_calls),
            )

            assistant_msg = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            api_messages.append(assistant_msg)

            if not tool_calls:
                return state.update(synthesis_result=content or "(no response)")

            # Execute tool calls
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_id = tool_call["id"]

                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                except json.JSONDecodeError as e:
                    api_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": f"Error parsing arguments: {e}",
                        }
                    )
                    continue

                if tool_name in SUBAGENT_TOOL_FUNCTIONS:
                    try:
                        tool_result = SUBAGENT_TOOL_FUNCTIONS[tool_name](**tool_args)
                    except Exception as e:
                        tool_result = f"Error: {e}"
                else:
                    tool_result = f"Unknown tool: {tool_name}"

                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": tool_result,
                    }
                )

    return state.update(synthesis_result=f"Error: Synthesizer hit max iterations")


@action(
    reads=["synthesis_result", "component_analyses", "service_name"],
    writes=["final_response"],
    tags=[
        "phase:output",
        "component:orchestrator",
        "source:agent/burr_app.py:analysis_respond",
    ],
)
def analysis_respond(state: State) -> State:
    """Format final analysis response."""
    service_name = state.get("service_name", "unknown")
    analyses = state.get("component_analyses", {})
    synthesis = state.get("synthesis_result", "")

    response = f"""Analysis complete for {service_name}.

Analyzed {len(analyses)} components:
{chr(10).join(f"  - {name}" for name in sorted(analyses.keys()))}

Documentation: /tmp/{service_name}/architecture_docs/architecture.md
"""

    return state.update(final_response=response)


# ---------------------------------------------------------------------------
# Application builders
# ---------------------------------------------------------------------------


def build_analysis_pipeline(
    service_name: str,
    project_name: str = "flashlight-analysis",
) -> Application:
    """Build the analysis pipeline for headless codebase analysis.

    Creates a structured state machine:

        receive_input -> read_discovery -> analyze_current_depth -+-> synthesize -> analysis_respond
                                               ^                  |
                                               |  (more depths)   |
                                               +------------------+

    The analyze_current_depth action loops until all depth levels are processed.

    Args:
        service_name: Name of the service being analyzed (for /tmp/{service_name}/)
        project_name: Project name for Burr tracking UI

    Returns:
        Compiled Burr Application
    """

    # Simple input action for analysis mode
    @action(reads=[], writes=["task"], tags=["phase:input"])
    def receive_analysis_input(state: State, task: str) -> State:
        return state.update(task=task)

    app = (
        ApplicationBuilder()
        .with_actions(
            receive_input=receive_analysis_input,
            read_discovery=read_discovery,
            analyze_current_depth=analyze_current_depth,
            synthesize=synthesize,
            respond=analysis_respond,
        )
        .with_transitions(
            ("receive_input", "read_discovery"),
            ("read_discovery", "analyze_current_depth"),
            ("analyze_current_depth", "analyze_current_depth", HAS_MORE_DEPTHS),
            ("analyze_current_depth", "synthesize", NO_MORE_DEPTHS),
            ("synthesize", "respond"),
        )
        .with_entrypoint("receive_input")
        .with_state(
            task="",
            components={},
            depth_order=[],
            current_depth=0,
            total_depths=0,
            component_analyses={},
            service_name=service_name,
            synthesis_result="",
            final_response="",
        )
        .with_tracker(project=project_name)
        .build()
    )

    return app


def build_interactive_agent(
    system_prompt: str,
    project_name: str = "flashlight",
    app_id: Optional[str] = None,
) -> Application:
    """Build an interactive agent for CLI usage.

    Creates a ReAct-style agent with the following state machine:

        receive_input -> call_llm -> [execute_tools -> call_llm]* -> respond -> receive_input

    The inner loop (call_llm <-> execute_tools) continues until the LLM
    responds without tool calls. Then we loop back to receive_input for
    the next conversation turn.

    Args:
        system_prompt: System prompt for the agent
        project_name: Project name for Burr tracking UI
        app_id: Optional application ID for resuming sessions

    Returns:
        Compiled Burr Application
    """
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
            ("respond", "receive_input"),  # Loop back for next turn
        )
        .with_entrypoint("receive_input")
        .with_state(
            messages=[],
            system_prompt=system_prompt,
            token_usage={"input": 0, "output": 0},
            pending_tool_calls=[],
            has_pending_tools=False,
        )
        .with_tracker(project=project_name)  # Built-in Burr UI tracking!
        .build()
    )

    return app


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run_interactive(system_prompt: str, project_name: str = "flashlight"):
    """Run an interactive chat session.

    This is the main entry point for CLI usage.
    """
    app = build_interactive_agent(system_prompt, project_name)

    print("\n" + "=" * 50)
    print("  Flashlight - Code Analysis Agent (Burr)")
    print("=" * 50)
    print("\nAnalyze codebases with an AI assistant.")
    print("Type 'exit' to quit.\n")
    print("Burr UI available at: http://localhost:7241")
    print("=" * 50 + "\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ["exit", "quit", "q"]:
            break

        # Run the agent through one conversation turn
        # receive_input -> call_llm -> [execute_tools -> call_llm]* -> respond
        app = app.update(state={**app.state, "user_input": user_input})

        action, result, state = app.run(
            halt_after=["respond"],
            inputs={"user_input": user_input},
        )

        response = state.get("final_response", "")
        print(f"\nAssistant: {response}\n")

        # Show token usage
        usage = state.get("token_usage", {})
        print(f"[Tokens: {usage.get('input', 0)} in / {usage.get('output', 0)} out]\n")

    print("\nGoodbye!")


if __name__ == "__main__":
    # Simple test
    run_interactive(
        system_prompt="You are a helpful code analysis assistant. Help the user explore and understand codebases."
    )
