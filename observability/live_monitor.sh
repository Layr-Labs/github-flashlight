#!/bin/bash
# LangGraph Session Profiler - Live Monitor
#
# Starts the log server and opens the profiler dashboard.
# The dashboard will auto-connect to the running agent session.

set -e

PORT=${1:-8888}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo ""
echo "Starting LangGraph Session Profiler..."
echo ""

# Kill any existing server on this port
lsof -ti:$PORT 2>/dev/null | xargs kill 2>/dev/null || true
sleep 1

# Start the server
cd "$PROJECT_DIR"
python3 "$SCRIPT_DIR/serve_logs.py" "$PORT" &
SERVER_PID=$!

# Wait for server to start
sleep 2

# Check if server is running
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "Error: Server failed to start"
    exit 1
fi

# Open the profiler in browser
PROFILER_PATH="$SCRIPT_DIR/session_profiler.html"
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$PROFILER_PATH"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "$PROFILER_PATH" 2>/dev/null || sensible-browser "$PROFILER_PATH" 2>/dev/null
else
    echo "Please open: $PROFILER_PATH"
fi

# Cleanup on exit
cleanup() {
    echo ""
    echo "Stopping server..."
    kill $SERVER_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Wait for server
wait $SERVER_PID
