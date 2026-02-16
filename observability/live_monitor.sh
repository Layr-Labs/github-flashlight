#!/bin/bash
# Automated live monitoring setup script
# This script:
# 1. Gets the current session ID
# 2. Starts the HTTP server with session context
# 3. Opens the visualization in your browser

set -e  # Exit on error

# Configuration
PORT=8000
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  Live Monitoring Setup - Flashlight Agent Visualization   ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Get log subdirectories (session and tool calls)
echo "🔍 Step 1/3: Getting log subdirectories..."

# Get both session file and tool calls file paths
LOG_PATHS=$("$SCRIPT_DIR/get_log_subdirectories.sh" "$PROJECT_DIR" 2>&1)
if [[ $? -eq 0 ]]; then
    CLAUDE_SESSION_FILE=$(echo "$LOG_PATHS" | sed -n '1p')
    TOOL_CALLS_FILE=$(echo "$LOG_PATHS" | sed -n '2p')
    SESSION_ID=$(basename "$CLAUDE_SESSION_FILE" .jsonl)
    echo "✅ Session ID: $SESSION_ID"
    echo "✅ Tool calls file: $TOOL_CALLS_FILE"
else
    echo "⚠️  Could not get log subdirectories"
    CLAUDE_SESSION_FILE=""
    TOOL_CALLS_FILE=""
    SESSION_ID=""
fi

echo "   Serving from: $PROJECT_DIR"
echo ""

# Step 2: Start the HTTP server with session context
echo "🚀 Step 2/3: Starting HTTP server on port $PORT..."

# Convert session file to relative path from home directory
if [[ -n "$CLAUDE_SESSION_FILE" ]]; then
    SESSION_FILE_RELATIVE="${CLAUDE_SESSION_FILE#$HOME/}"
    export FLASHLIGHT_SESSION_FILE="$SESSION_FILE_RELATIVE"
else
    export FLASHLIGHT_SESSION_FILE=""
fi

# Export tool calls file path
if [[ -n "$TOOL_CALLS_FILE" ]]; then
    TOOL_CALLS_FILE_RELATIVE="${TOOL_CALLS_FILE#$HOME/}"
    export FLASHLIGHT_TOOL_CALLS_FILE="$TOOL_CALLS_FILE_RELATIVE"
else
    export FLASHLIGHT_TOOL_CALLS_FILE=""
fi

# Start server from HOME directory (allows serving both .claude and project files)
cd "$HOME"
python3 "$SCRIPT_DIR/serve_logs.py" "$PORT" &
SERVER_PID=$!

# Give server time to start
sleep 2

# Check if server is running
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "❌ Error: Server failed to start"
    exit 1
fi

echo "✅ Server running (PID: $SERVER_PID)"
echo ""

# Step 3: Open visualization
echo "🌐 Step 3/3: Opening visualization..."
VISUAL_PATH="$SCRIPT_DIR/session_profiler.html"

# Detect OS and open browser
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$VISUAL_PATH"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "$VISUAL_PATH" 2>/dev/null || sensible-browser "$VISUAL_PATH" 2>/dev/null
else
    echo "⚠️  Please manually open: $VISUAL_PATH"
fi

echo "✅ Visualization opened in browser"
echo ""

# Show status
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  Live Monitoring Active                                   ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  SESSION_FILE: $CLAUDE_SESSION_FILE"
echo "║  TOOL_CALLS_FILE: $TOOL_CALLS_FILE"
echo "║  Server URL: http://localhost:$PORT"
echo "║  API Endpoints:"
echo "║    - http://localhost:$PORT/get/session_id"
echo "║    - http://localhost:$PORT/get/tool_calls_file"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  The visualization will automatically load your session   ║"
echo "║  and enable live monitoring.                              ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  Press Ctrl+C to stop the server and exit                ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Trap to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping server (PID: $SERVER_PID)..."
    kill $SERVER_PID 2>/dev/null
    echo "✅ Server stopped. Goodbye!"
    exit 0
}

trap cleanup INT TERM

# Wait for server process
wait $SERVER_PID
