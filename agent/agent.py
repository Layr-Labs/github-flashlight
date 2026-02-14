"""Entry point for code analysis agent using AgentDefinition for subagents."""

import asyncio
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AgentDefinition, HookMatcher

from agent.utils.subagent_tracker import SubagentTracker
from agent.utils.transcript import setup_session, TranscriptWriter
from agent.utils.message_handler import process_assistant_message
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
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Paths to prompt files
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt from the prompts directory."""
    prompt_path = PROMPTS_DIR / filename
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


async def chat():
    """Start interactive chat with the code analysis agent."""

    # Check API key first, before creating any files
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nError: ANTHROPIC_API_KEY not found.")
        print("Set it in a .env file or export it in your shell.")
        print("Get your key at: https://console.anthropic.com/settings/keys\n")
        return

    # Setup session directory and transcript
    transcript_file, session_dir = setup_session()

    # Create transcript writer
    transcript = TranscriptWriter(transcript_file)

    # Load prompts
    lead_agent_prompt = load_prompt("lead_agent.txt")
    base_code_analyzer_prompt = load_prompt("code_analyzer.txt")
    architecture_documenter_prompt = load_prompt("subagents/architecture_documenter.txt")
    website_generator_prompt = load_prompt("website_generator.txt")

    # Load analysis templates and enhance code analyzer prompt
    templates_dir = Path(__file__).parent.parent / "templates" / "analysis-template"
    template_loader = TemplateLoader(templates_dir)

    # Build enhanced code analyzer prompt with templates
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

    # Initialize subagent tracker with transcript writer and session directory
    tracker = SubagentTracker(
        transcript_writer=transcript,
        session_dir=session_dir,
        verbose=VERBOSE
    )

    # Define specialized subagents
    agents = {
        "code-library-analyzer": AgentDefinition(
            description=(
                "Use this agent to perform deep analysis of a specific library code component. "
                "The code-analyzer uses Glob, Grep, Read, and Bash to explore code structure, "
                "identify key components, trace data flows, and document architecture. "
                "Receives upstream dependency context when analyzing library components with dependencies. "
                "Produces structured analysis reports in Markdown format "
                "in /tmp/{SERVICE_NAME}/service_analyses/. "
                "Each library should get its own code-library-analyzer instance."
            ),
            tools=["Glob", "Grep", "Read", "Bash", "Write"],
            prompt=code_analyzer_prompt,
            model="sonnet"  # Use sonnet for complex code analysis
        ),
        "application-analyzer": AgentDefinition(
            description=(
                "Use this agent to perform deep analysis of an application code component. "
                "The code-analyzer uses Glob, Grep, Read, and Bash to explore code structure, "
                "identify key components, trace data flows, and document architecture. "
                "Receives upstream dependency context when analyzing library components with dependencies. "
                "Produces structured analysis reports in Markdown format "
                "in /tmp/{SERVICE_NAME}/service_analyses/. "
                "Each application should get its own application-analyzer instance."
            ),
            tools=["Glob", "Grep", "Read", "Bash", "Write"],
            prompt=code_analyzer_prompt,
            model="sonnet"  # Use sonnet for complex code analysis
        ),
        "architecture-documenter": AgentDefinition(
            description=(
                "Use this agent AFTER all application analyses complete to synthesize architecture documentation. "
                "Runs once after analysis phase, reads all completed analyses and graphs, creates comprehensive docs."
            ),
            tools=["Glob", "Read", "Write"],
            prompt=architecture_documenter_prompt,
            model="sonnet"  # Use sonnet for comprehensive synthesis
        ),
        "website-generator": AgentDefinition(
            description=(
                "Use this agent AFTER architecture documentation is complete to generate a web frontend. "
                "The website-generator reads all service analyses, dependency graphs, and architecture docs "
                "from /tmp/{SERVICE_NAME}/, then creates a complete React SPA with D3.js interactive "
                "dependency graph visualization in /tmp/{SERVICE_NAME}/website/. Generates all necessary "
                "files: package.json, components, styles, and build instructions. Spawn this agent once "
                "at the very end to create the interactive website."
            ),
            tools=["Glob", "Read", "Write", "Bash"],
            prompt=website_generator_prompt,
            model="sonnet"  # Use sonnet for comprehensive web app generation
        )
    }

    # Set up hooks for tracking subagent states
    # and lifecycle movements
    # 
    hooks = {
        'PreToolUse': [
            HookMatcher(
                matcher=None,  # Match all tools
                hooks=[tracker.pre_tool_use_hook]
            )
        ],
        'PostToolUse': [
            HookMatcher(
                matcher=None,  # Match all tools
                hooks=[tracker.post_tool_use_hook]
            )
        ],
        'SubagentStop': [
            HookMatcher(
                matcher=None,  # Match all tools
                hooks=[tracker.post_subagent_stop_hook]
            )
        ]
    }

    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        setting_sources=["project"],  # Load skills from project .claude directory
        system_prompt=lead_agent_prompt,
        allowed_tools=["Task", "Glob", "Read", "Bash", "Write"],  # Lead agent has discovery tools
        agents=agents,
        hooks=hooks,
        model="sonnet",  # Use sonnet for orchestration and discovery
        max_thinking_tokens=9999  # Enable thinking blocks for lead agent (10k token budget)
    )

    print("\n" + "=" * 50)
    print("  Code Analysis Agent")
    print("=" * 50)
    print("\nAnalyze codebases with dependency-aware")
    print("multi-agent analysis.")

    # Show logging mode
    if DEBUG:
        print("\n🔍 DEBUG MODE ENABLED - Full API trace logging")
    elif VERBOSE:
        print("\n🔍 VERBOSE MODE ENABLED - Detailed SDK interaction logging")

    print("\nProvide a path to analyze, or type 'exit' to quit.\n")

    try:
        async with ClaudeSDKClient(options=options) as client:
            while True:
                # Get input
                try:
                    user_input = input("\nYou: ").strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not user_input or user_input.lower() in ["exit", "quit", "q"]:
                    break

                # Write user input to transcript (file only, not console)
                transcript.write_to_file(f"\nYou: {user_input}\n")
                
                await client.query(prompt=user_input)

                transcript.write("\nAgent: ", end="")

                # Stream and process response
                message_count = 0
                api_call_count = 0
                async for msg in client.receive_response():
                    message_count += 1
                    msg_type = type(msg).__name__

                    if VERBOSE:
                        logger.debug(f"   Message {message_count}: {msg_type}")

                    # Track API calls by counting AssistantMessages (each represents an API round-trip)
                    if msg_type == 'AssistantMessage':
                        api_call_count += 1
                        print(f"\n🌐 [CLAUDE CALL #{api_call_count}] Claude AssistantMessage completed", flush=True)
                        process_assistant_message(msg, tracker, transcript)

                if VERBOSE:
                    logger.info(f"✓ RESPONSE COMPLETE ({message_count} messages, {api_call_count} API calls)")

                transcript.write("\n")
    finally:
        transcript.write("\n\nGoodbye!\n")
        transcript.close()
        tracker.close()
        print(f"\nSession logs saved to: {session_dir}")
        print(f"  - Transcript: {transcript_file}")
        print(f"  - Tool calls: {session_dir / 'tool_calls.jsonl'}")


if __name__ == "__main__":
    asyncio.run(chat())
