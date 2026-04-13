"""LangGraph-compatible tool implementations.

Replaces the built-in tools previously provided by claude-agent-sdk
(Glob, Grep, Read, Bash, Write) with explicit Python implementations
decorated as LangChain tools.
"""

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@tool
def read_file(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read a file from the local filesystem.

    Returns the file contents with each line prefixed by its line number.
    Use offset and limit to read specific sections of large files.

    Args:
        file_path: Absolute path to the file to read.
        offset: Line number to start reading from (1-indexed, default 1).
        limit: Maximum number of lines to return (default 2000).
    """
    p = Path(file_path)
    if not p.exists():
        return f"Error: path does not exist: {file_path}"

    if p.is_dir():
        entries = sorted(p.iterdir())
        lines = []
        for entry in entries:
            name = entry.name + ("/" if entry.is_dir() else "")
            lines.append(name)
        return "\n".join(lines) if lines else "(empty directory)"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading {file_path}: {exc}"

    all_lines = text.splitlines(keepends=True)
    total = len(all_lines)

    # Apply offset (1-indexed) and limit
    start = max(0, offset - 1)
    end = start + limit
    selected = all_lines[start:end]

    result_lines = []
    for i, line in enumerate(selected, start=start + 1):
        # Truncate very long lines
        content = line.rstrip("\n\r")
        if len(content) > 2000:
            content = content[:2000] + "... (truncated)"
        result_lines.append(f"{i}: {content}")

    result = "\n".join(result_lines)
    if end < total:
        result += f"\n\n(Showing lines {offset}-{end} of {total} total lines)"
    return result


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed.

    This will overwrite the file if it already exists.

    Args:
        file_path: Absolute path to the file to write.
        content: The content to write to the file.
    """
    p = Path(file_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {file_path}"
    except Exception as exc:
        return f"Error writing {file_path}: {exc}"


# ---------------------------------------------------------------------------
# Glob
# ---------------------------------------------------------------------------


@tool
def glob_files(pattern: str, path: Optional[str] = None) -> str:
    """Find files matching a glob pattern.

    Supports patterns like '**/*.py', 'src/**/*.ts', etc.

    Args:
        pattern: The glob pattern to match files against.
        path: The directory to search in. Defaults to current working directory.
    """
    base = Path(path) if path else Path.cwd()
    if not base.exists():
        return f"Error: directory does not exist: {base}"

    try:
        matches = sorted(base.glob(pattern))
        # Filter out directories, only return files
        files = [str(m) for m in matches if m.is_file()]
        if not files:
            return f"No files found matching pattern '{pattern}' in {base}"
        # Cap output to avoid massive returns
        if len(files) > 500:
            result = "\n".join(files[:500])
            result += f"\n\n... and {len(files) - 500} more files (truncated)"
            return result
        return "\n".join(files)
    except Exception as exc:
        return f"Error searching for pattern '{pattern}': {exc}"


# ---------------------------------------------------------------------------
# Grep
# ---------------------------------------------------------------------------


@tool
def grep_files(
    pattern: str,
    path: Optional[str] = None,
    include: Optional[str] = None,
) -> str:
    """Search file contents using a regular expression.

    Returns matching file paths and line numbers.

    Args:
        pattern: The regex pattern to search for in file contents.
        path: The directory to search in. Defaults to current working directory.
        include: Optional file pattern to filter by (e.g., '*.py', '*.{ts,tsx}').
    """
    base = Path(path) if path else Path.cwd()
    if not base.exists():
        return f"Error: directory does not exist: {base}"

    # Build ripgrep command for efficiency; fall back to Python if rg not available
    cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
    if include:
        cmd.extend(["--glob", include])
    cmd.append(pattern)
    cmd.append(str(base))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        if not output:
            return f"No matches found for pattern '{pattern}' in {base}"
        # Truncate if very large
        lines = output.split("\n")
        if len(lines) > 500:
            output = "\n".join(lines[:500])
            output += f"\n\n... and {len(lines) - 500} more matches (truncated)"
        return output
    except FileNotFoundError:
        # ripgrep not available, fall back to Python regex search
        return _grep_python_fallback(pattern, base, include)
    except subprocess.TimeoutExpired:
        return f"Error: search timed out after 30 seconds"
    except Exception as exc:
        return f"Error searching: {exc}"


def _grep_python_fallback(pattern: str, base: Path, include: Optional[str]) -> str:
    """Pure-Python fallback for grep when ripgrep is not available."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"Invalid regex pattern '{pattern}': {exc}"

    matches = []
    for root, _dirs, files in os.walk(base):
        for fname in files:
            if include:
                # Simple glob match on filename
                if not fnmatch.fnmatch(fname, include):
                    continue
            fpath = Path(root) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        matches.append(f"{fpath}:{i}:{line}")
                        if len(matches) >= 500:
                            matches.append("\n... (truncated at 500 matches)")
                            return "\n".join(matches)
            except (OSError, UnicodeDecodeError):
                continue

    if not matches:
        return f"No matches found for pattern '{pattern}' in {base}"
    return "\n".join(matches)


# ---------------------------------------------------------------------------
# Bash
# ---------------------------------------------------------------------------


@tool
def bash(command: str, workdir: Optional[str] = None, timeout: int = 120) -> str:
    """Execute a bash command and return its output.

    Args:
        command: The command to execute.
        workdir: Optional working directory. Defaults to current directory.
        timeout: Timeout in seconds (default 120).
    """
    cwd = workdir if workdir else None
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
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

        # Truncate very large outputs
        if len(output) > 100_000:
            output = output[:100_000] + "\n... (output truncated at 100KB)"
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout} seconds"
    except Exception as exc:
        return f"Error executing command: {exc}"


# ---------------------------------------------------------------------------
# Tool collections
# ---------------------------------------------------------------------------

# All tools available for code analysis subagents
ANALYSIS_TOOLS = [read_file, write_file, glob_files, grep_files, bash]

# Restricted set for architecture documenter (no bash/grep needed)
DOCUMENTER_TOOLS = [read_file, write_file, glob_files]

# Full set for lead agent (same as analysis tools)
LEAD_AGENT_TOOLS = [read_file, write_file, glob_files, grep_files, bash]
