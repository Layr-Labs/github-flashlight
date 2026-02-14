#!/bin/bash

# Get the current session ID by finding the most recently modified session file or directory
# Usage: ./get_session_id.sh [project_dir]

# Default to current working directory
PROJECT_DIR="${1:-$(pwd)}"

# Convert path to Claude project directory format (replace / with -)
CLAUDE_PROJECT_DIR="$HOME/.claude/projects/$(echo "$PROJECT_DIR" | sed 's/\//-/g')"

if [[ ! -d "$CLAUDE_PROJECT_DIR" ]]; then
    echo "Error: Claude project directory not found: $CLAUDE_PROJECT_DIR" >&2
    exit 1
fi

# Find most recently modified .jsonl file or directory
# Using both to handle sessions with or without subdirectories
LATEST=$(find "$CLAUDE_PROJECT_DIR" -maxdepth 1 \( -name "*.jsonl" -o -type d \) -not -name "." -not -name ".." -not -name "memory" 2>/dev/null | \
    xargs stat -f "%m %N" 2>/dev/null | \
    sort -rn | \
    head -1 | \
    awk '{print $2}')

if [[ -z "$LATEST" ]]; then
    echo "Error: No session files found" >&2
    exit 1
fi

# Extract UUID from path
SESSION_ID=$(basename "$LATEST" .jsonl | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

if [[ -z "$SESSION_ID" ]]; then
    echo "Error: Could not extract session ID" >&2
    exit 1
fi

# Extract project name from the Claude project directory path
PROJECT_NAME=$(basename "$CLAUDE_PROJECT_DIR")

echo "$HOME/.claude/projects/$PROJECT_NAME/$SESSION_ID.jsonl"
