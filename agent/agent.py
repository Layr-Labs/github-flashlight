"""Entry point for interactive code analysis agent using Burr.

Uses Burr's explicit state machine paradigm for:
- Clear observability (state/transitions are declared, not inferred)
- Built-in tracking UI at http://localhost:7241
- Native parallel execution for multi-component analysis
- State persistence and checkpointing

Architecture:
    receive_input -> read_discovery -> analyze_current_depth (loop) -> synthesize -> respond

Each component analyzer runs as a separate tracked Burr application.
"""

import os
import logging
from pathlib import Path

from dotenv import load_dotenv

from agent.burr_app import build_analysis_pipeline
from agent.utils.transcript import setup_session, TranscriptWriter

# Load environment variables
load_dotenv()

# Setup logging based on environment variable
VERBOSE = os.environ.get("AGENT_VERBOSE", "false").lower() in ("true", "1", "yes")
DEBUG = os.environ.get("AGENT_DEBUG", "false").lower() in ("true", "1", "yes")

# Configure logging
log_level = logging.DEBUG if DEBUG else (logging.INFO if VERBOSE else logging.WARNING)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Paths to prompt files
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / filename
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def analyze(service_name: str):
    """Run analysis on a service using the structured pipeline.

    Args:
        service_name: Name of the service (must have discovery files in /tmp/{service_name}/)
    """
    # Check API key first
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("\nError: OPENROUTER_API_KEY not found.")
        print("Set it in a .env file or export it in your shell.")
        print("Get your key at: https://openrouter.ai/keys\n")
        return

    # Setup session directory and transcript
    transcript_file, session_dir = setup_session()
    transcript = TranscriptWriter(transcript_file)

    # Build the structured analysis pipeline
    app = build_analysis_pipeline(
        service_name=service_name,
        project_name=f"flashlight-{service_name}",
    )

    print("\n" + "=" * 60)
    print("  Flashlight - Code Analysis Agent (Burr)")
    print("=" * 60)
    print(f"\nAnalyzing: {service_name}")
    print(f"\n  Burr UI: http://localhost:7241")
    print(
        "  (Run '.burr-ui-venv/bin/python -m uvicorn burr.tracking.server.run:app --port 7241')"
    )

    # Show logging mode
    if DEBUG:
        print("\n  DEBUG MODE ENABLED - Full trace logging")
    elif VERBOSE:
        print("\n  VERBOSE MODE ENABLED - Detailed logging")

    print("=" * 60 + "\n")

    try:
        transcript.write_to_file(f"\nAnalyzing {service_name}...\n")

        # Run the structured pipeline
        # receive_input -> read_discovery -> analyze_current_depth (loop) -> synthesize -> respond
        action, result, state = app.run(
            halt_after=["respond"],
            inputs={"task": f"Analyze {service_name}"},
        )

        # Extract and display the response
        response = state.get("final_response", "")
        print(f"\n{response}\n")

        # Write response to transcript
        transcript.write_to_file(f"\n{response}\n")

        # Show analysis stats
        analyses = state.get("component_analyses", {})
        print(f"[Analyzed {len(analyses)} components]")

    except Exception as e:
        logger.error(f"Error during analysis: {e}", exc_info=True)
        print(f"\nError: {e}")

    finally:
        transcript.write_to_file("\n\nAnalysis complete.\n")
        transcript.close()
        print(f"\nSession logs saved to: {session_dir}")
        print(f"  - Transcript: {transcript_file}")


def extract_service_name(input_str: str) -> str:
    """Extract a valid service name from a path or URL.

    Examples:
        https://github.com/org/repo -> repo
        /path/to/my-project -> my-project
        my-service -> my-service
    """
    import re

    # Handle GitHub URLs
    if "github.com" in input_str:
        # Extract repo name from URL
        match = re.search(r"github\.com/[^/]+/([^/]+?)(?:\.git)?(?:/.*)?$", input_str)
        if match:
            return match.group(1)

    # Handle file paths
    if "/" in input_str:
        return Path(input_str).name

    return input_str


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Flashlight analysis on a codebase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a repo (discovery must be done first via CLI)
  python -m agent.agent --repo https://github.com/org/repo
  python -m agent.agent my-service
  
  # Run full analysis with discovery:
  python -m agent.cli analyze https://github.com/org/repo
        """,
    )
    parser.add_argument("repo", nargs="?", help="Repository URL, path, or service name")
    parser.add_argument(
        "--repo",
        dest="repo_flag",
        help="Repository URL, path, or service name (alternative syntax)",
    )

    args = parser.parse_args()

    # Get repo from either positional or flag
    input_arg = args.repo_flag or args.repo

    if not input_arg:
        parser.print_help()
        sys.exit(1)

    service_name = extract_service_name(input_arg)

    # Check if discovery files exist
    work_dir = Path(f"/tmp/{service_name}")
    if not (work_dir / "service_discovery" / "components.json").exists():
        print(f"\nError: Discovery files not found for '{service_name}'")
        print(f"  Expected: {work_dir}/service_discovery/components.json")
        print("\nRun discovery first using the CLI:")
        print(f"  python -m agent.cli analyze {input_arg}")
        sys.exit(1)

    analyze(service_name)
