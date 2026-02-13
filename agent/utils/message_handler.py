"""Message handling for processing agent responses."""

from typing import Any


# Track if a tool was just used (for formatting)
_tool_just_used = False


def process_assistant_message(msg: Any, tracker: Any, transcript: Any) -> None:
    """Process an AssistantMessage and write output to transcript.

    Args:
        msg: AssistantMessage to process
        tracker: SubagentTracker instance
        transcript: TranscriptWriter instance
    """
    global _tool_just_used

    # Update tracker context with parent_tool_use_id from message
    parent_id = getattr(msg, 'parent_tool_use_id', None)
    tracker.set_current_context(parent_id)

    for block in msg.content:
        block_type = type(block).__name__

        if block_type == 'TextBlock':
            # Add newline if a tool was just used
            if _tool_just_used:
                transcript.write("\n", end="")
                print()  # Add newline to console too
                _tool_just_used = False
            text = block.text
            transcript.write(text, end="")
            print(f"[📝 Text] {text}", flush=True)

        elif block_type == 'ThinkingBlock':
            # Print thinking block information
            thinking_text = getattr(block, 'thinking', getattr(block, 'text', ''))
            if thinking_text:
                print(f"\n[💭 Thinking ({len(thinking_text)} chars)]")
                # Optionally print a preview of the thinking
                preview_length = 200
                if len(thinking_text) > preview_length:
                    print(f"Preview: {thinking_text[:preview_length]}...")
                else:
                    print(f"Content: {thinking_text}")

        elif block_type == 'ToolUseBlock':
            # Mark that a tool was used
            _tool_just_used = True

            # Only handle Task tool (subagent spawning)
            if block.name == 'Task':
                subagent_type = block.input.get('subagent_type', 'unknown')
                description = block.input.get('description', 'no description')
                prompt = block.input.get('prompt', '')

                # Register with tracker and get the subagent ID
                subagent_id = tracker.register_subagent_spawn(
                    tool_use_id=block.id,
                    subagent_type=subagent_type,
                    description=description,
                    prompt=prompt
                )
                # User-facing output with subagent ID
                transcript.write(f"\n\n[🚀 Spawning {subagent_id}: {description}]\n", end="")
                print(f"[🚀 {subagent_id}]: starting prompt \n \n ", prompt)

        elif block_type == 'ToolResultBlock':
            # Mark that a tool was used
            _tool_just_used = True

            # Check if this is a Task tool result (subagent completion)
            tool_use_id = getattr(block, 'tool_use_id', None)
            if tool_use_id and tool_use_id in tracker.sessions:
                session = tracker.sessions[tool_use_id]
                subagent_id = session.subagent_id

                # Log completion to transcript (UI concern)
                # Note: State management (counters, events) handled by SubagentStop hook
                transcript.write(f"\n\n[✅ {session.subagent_type} completed: {session.description}]\n", end="")
                print(f"\n[✅ {subagent_id}]: task completed")

