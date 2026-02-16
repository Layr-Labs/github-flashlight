#!/usr/bin/env python3
"""
Simple HTTP server to serve JSONL log files for real-time visualization.

Usage:
    python serve_logs.py [port] [directory]

Examples:
    python serve_logs.py                    # Serve current directory on port 8000
    python serve_logs.py 8080               # Serve current directory on port 8080
    python serve_logs.py 8000 ../logs       # Serve ../logs directory on port 8000
"""

import http.server
import socketserver
import sys
import os
import json
from pathlib import Path


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler with CORS enabled for cross-origin requests."""

    # Store session file path as class variable
    session_file = None
    tool_calls_file = None

    def do_GET(self):
        """Handle GET requests with custom endpoint for session info."""
        # Check if this is a request for session ID
        if self.path == '/get/session_id':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            # Return session file path as JSON
            response = {
                'session_file': self.session_file
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return

        # Check if this is a request for tool calls file
        if self.path == '/get/tool_calls_file':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            # Return tool calls file path as JSON
            response = {
                'tool_calls_file': self.tool_calls_file
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return

        # Otherwise, use default file serving behavior
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
        """Log requests with timestamp and more details."""
        timestamp = self.log_date_time_string()
        # Show the requested path clearly
        message = format % args
        if 'GET' in message or 'POST' in message:
            sys.stderr.write("📥 %s - %s\n" % (timestamp, message))
        else:
            sys.stderr.write("%s - %s\n" % (timestamp, message))


def main():
    # Print initial working directory at start
    print(f"Initial working directory: {os.getcwd()}")

    # Parse command line arguments
    port = 8000
    directory = '.'

    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)

    if len(sys.argv) > 2:
        directory = sys.argv[2]
        if not os.path.isdir(directory):
            print(f"Directory not found: {directory}")
            sys.exit(1)

    # Change to the target directory
    os.chdir(directory)
    abs_path = Path.cwd()

    # Check for session file from environment (set by live_monitor.sh)
    session_file = os.environ.get('FLASHLIGHT_SESSION_FILE')
    tool_calls_file = os.environ.get('FLASHLIGHT_TOOL_CALLS_FILE')

    # Store session file in handler class
    CORSRequestHandler.session_file = session_file
    CORSRequestHandler.tool_calls_file = tool_calls_file

    # Print current working directory for debugging
    print(f"\nCurrent working directory: {abs_path}\n")

    # Create server with SO_REUSEADDR to allow immediate port reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), CORSRequestHandler) as httpd:
        print(f"╔{'═' * 60}╗")
        print(f"║  Live Log Server - Real-time JSONL Visualization Support{' ' * 2}║")
        print(f"╠{'═' * 60}╣")
        print(f"║  Serving directory: {str(abs_path):<40}║")
        print(f"║  Server address:    http://localhost:{port:<27}║")

        if session_file or tool_calls_file:
            print(f"╠{'═' * 60}╣")
            print(f"║  Session Context:                                          ║")
            if session_file:
                print(f"║  Session File: {session_file:<43}║")
                print(f"║  API Endpoint:  /get/session_id                            ║")
            if tool_calls_file:
                print(f"║  Tool Calls File: {tool_calls_file:<40}║")
                print(f"║  API Endpoint:  /get/tool_calls_file                       ║")

        print(f"╠{'═' * 60}╣")
        print(f"║  Usage in visualization:                                   ║")
        print(f"║  1. Open session_profiler.html in your browser            ║")

        if session_file:
            print(f"║  2. Session will be auto-loaded from environment          ║")
        else:
            print(f"║  2. URL is pre-filled (adjust path if needed)             ║")

        print(f"║  3. Live monitoring will start automatically              ║")
        print(f"╠{'═' * 60}╣")
        print(f"║  Press Ctrl+C to stop the server                          ║")
        print(f"╚{'═' * 60}╝\n")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped.")
            sys.exit(0)


if __name__ == "__main__":
    main()
