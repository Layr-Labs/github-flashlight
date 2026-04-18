#!/usr/bin/env python3
"""
Simple HTTP server for LangGraph session profiler.

Serves the tool_calls.jsonl log file for real-time visualization.
Auto-discovers the latest log file from the project's logs directory.

Usage:
    python serve_logs.py [port]

Examples:
    python serve_logs.py                    # Serve on port 8000
    python serve_logs.py 8080               # Serve on port 8080
"""

import http.server
import socketserver
import sys
import os
import json
from pathlib import Path


def find_latest_tool_calls_file():
    """Find the latest tool_calls.jsonl file in the project logs."""
    # Check common locations
    search_paths = [
        Path(__file__).parent.parent / "logs" / "latest" / "tool_calls.jsonl",
        Path.cwd() / "logs" / "latest" / "tool_calls.jsonl",
        Path.cwd().parent / "logs" / "latest" / "tool_calls.jsonl",
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    # Search recursively in logs directory
    logs_dir = Path(__file__).parent.parent / "logs"
    if logs_dir.exists():
        tool_call_files = list(logs_dir.rglob("tool_calls.jsonl"))
        if tool_call_files:
            # Return the most recently modified
            return max(tool_call_files, key=lambda p: p.stat().st_mtime)
    
    return None


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler with CORS enabled and auto-discovery."""

    # Store paths as class variables
    tool_calls_file = None
    base_dir = None

    def do_GET(self):
        """Handle GET requests with custom endpoints."""
        # API endpoint: get tool calls file path
        if self.path == '/get/tool_calls_file':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            # Auto-discover if not set
            if not self.tool_calls_file:
                found = find_latest_tool_calls_file()
                if found:
                    # Make path relative to base_dir for serving
                    try:
                        self.tool_calls_file = str(found.relative_to(self.base_dir))
                    except ValueError:
                        self.tool_calls_file = str(found)

            response = {'tool_calls_file': self.tool_calls_file}
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return

        # Legacy endpoint for backward compatibility
        if self.path == '/get/session_id':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {'session_file': None}  # Deprecated
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return

        # Serve files normally
        return super().do_GET()

    def end_headers(self):
        # Enable CORS for all origins
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        # Disable caching so browser always gets latest file
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight CORS requests."""
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        """Log requests with timestamp."""
        timestamp = self.log_date_time_string()
        message = format % args
        # Only log actual requests, not noise
        if 'GET' in message and '/get/' not in message:
            sys.stderr.write(f"  {timestamp} - {message}\n")


def main():
    # Parse command line arguments
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)

    # Determine base directory (project root)
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    
    # Change to project directory for serving
    os.chdir(project_dir)
    CORSRequestHandler.base_dir = project_dir

    # Check for tool calls file from environment or auto-discover
    tool_calls_file = os.environ.get('FLASHLIGHT_TOOL_CALLS_FILE')
    if not tool_calls_file:
        found = find_latest_tool_calls_file()
        if found:
            try:
                tool_calls_file = str(found.relative_to(project_dir))
            except ValueError:
                tool_calls_file = str(found)

    CORSRequestHandler.tool_calls_file = tool_calls_file

    # Create server
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), CORSRequestHandler) as httpd:
        print()
        print("╔════════════════════════════════════════════════════════════╗")
        print("║         LangGraph Session Profiler - Log Server            ║")
        print("╠════════════════════════════════════════════════════════════╣")
        print(f"║  Server:  http://localhost:{port:<32}║")
        
        if tool_calls_file:
            # Truncate long paths
            display_path = tool_calls_file if len(tool_calls_file) < 45 else "..." + tool_calls_file[-42:]
            print(f"║  Logs:    {display_path:<49}║")
        else:
            print("║  Logs:    (auto-discover on request)                       ║")
        
        print("╠════════════════════════════════════════════════════════════╣")
        print("║  Open session_profiler.html and click 'Connect to Agent'   ║")
        print("║  Press Ctrl+C to stop                                       ║")
        print("╚════════════════════════════════════════════════════════════╝")
        print()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
            sys.exit(0)


if __name__ == "__main__":
    main()
