"""Entry point for interactive code analysis agent using LangGraph.

Replaces the claude-agent-sdk ClaudeSDKClient with a LangGraph-based
multi-agent orchestrator. The lead agent delegates to specialized
subagents (code-library-analyzer, application-analyzer, etc.) via the
spawn_subagent tool, which is intercepted by the graph and run as
an inline subgraph.
"""

import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from agent.callbacks import FlashlightCallbackHandler
from agent.graph import build_lead_graph
from agent.utils.transcript import setup_session, TranscriptWriter
from agent.utils.template_loader import TemplateLoader

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


def _build_agent_prompts() -> dict[str, str]:
    """Load and build all subagent system prompts.

    Returns a dict of subagent_type -> system prompt string.
    """
    # Load base prompts
    base_code_analyzer_prompt = load_prompt("code_analyzer.txt")
    architecture_documenter_prompt = load_prompt(
        "subagents/architecture_documenter.txt"
    )
    external_service_analyzer_prompt = load_prompt(
        "subagents/external_service_analyzer.txt"
    )

    # Load analysis templates and enhance code analyzer prompt
    templates_dir = Path(__file__).parent.parent / "templates" / "analysis-template"
    template_loader = TemplateLoader(templates_dir)

    template_instructions = template_loader.get_template_instructions()
    application_template = template_loader.get_template("application")
    package_template = template_loader.get_template("package")

    code_analyzer_prompt = f"""{base_code_analyzer_prompt}

{template_instructions}

<application_analysis_template>
{application_template}
</application_analysis_template>

<package_analysis_template>
{package_template}
</package_analysis_template>
"""

    return {
        "code-library-analyzer": code_analyzer_prompt,
        "application-analyzer": code_analyzer_prompt,
        "architecture-documenter": architecture_documenter_prompt,
        "external-service-analyzer": external_service_analyzer_prompt,
    }


def chat():
    """Start interactive chat with the code analysis agent."""

    # Check API key first, before creating any files
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("\nError: OPENROUTER_API_KEY not found.")
        print("Set it in a .env file or export it in your shell.")
        print("Get your key at: https://openrouter.ai/keys\n")
        return

    # Setup session directory and transcript
    transcript_file, session_dir = setup_session()
    transcript = TranscriptWriter(transcript_file)

    # Load prompts
    lead_agent_prompt = load_prompt("lead_agent.txt")
    agent_prompts = _build_agent_prompts()

    # Initialize callback handler
    callback_handler = FlashlightCallbackHandler(
        transcript_writer=transcript,
        session_dir=session_dir,
        verbose=VERBOSE,
    )

    # Build the lead agent graph
    graph = build_lead_graph(
        system_prompt=lead_agent_prompt,
        agent_prompts=agent_prompts,
        model_name="anthropic/claude-sonnet-4-20250514",
        callback_handler=callback_handler,
    )

    print("\n" + "=" * 50)
    print("  Code Analysis Agent (LangGraph)")
    print("=" * 50)
    print("\nAnalyze codebases with dependency-aware")
    print("multi-agent analysis.")

    # Show logging mode
    if DEBUG:
        print("\nDEBUG MODE ENABLED - Full trace logging")
    elif VERBOSE:
        print("\nVERBOSE MODE ENABLED - Detailed logging")

    print("\nProvide a path to analyze, or type 'exit' to quit.\n")

    # Maintain conversation state across turns
    state = {
        "messages": [],
        "subagent_results": {},
        "service_name": "",
        "repo_path": "",
    }

    try:
        while True:
            # Get input
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input or user_input.lower() in ["exit", "quit", "q"]:
                break

            # Write user input to transcript
            transcript.write_to_file(f"\nYou: {user_input}\n")

            # Add user message to state
            state["messages"].append(HumanMessage(content=user_input))

            transcript.write("\nAgent: ", end="")

            # Run the graph
            result = graph.invoke(
                state,
                config={"callbacks": [callback_handler]},
            )

            # Update state with the result
            state = result

            # Print the final agent response
            messages = result.get("messages", [])
            for msg in messages:
                if isinstance(msg, AIMessage) and msg.content:
                    text = ""
                    if isinstance(msg.content, str):
                        text = msg.content
                    elif isinstance(msg.content, list):
                        text_parts = [
                            block["text"]
                            for block in msg.content
                            if isinstance(block, dict) and block.get("type") == "text"
                        ]
                        text = "\n".join(text_parts)
                    if text:
                        transcript.write(text, end="")

            transcript.write("\n")

    finally:
        transcript.write("\n\nGoodbye!\n")
        transcript.close()
        callback_handler.close()
        print(f"\nSession logs saved to: {session_dir}")
        print(f"  - Transcript: {transcript_file}")
        print(f"  - Tool calls: {session_dir / 'tool_calls.jsonl'}")


if __name__ == "__main__":
    chat()
