"""Message handling for processing agent responses.

NOTE: This module is deprecated after the migration from claude-agent-sdk
to LangGraph. Message processing is now handled by LangGraph's built-in
message passing and the FlashlightCallbackHandler in agent/callbacks.py.

This module is retained as a stub for backward compatibility.
"""

from typing import Any
import logging

logger = logging.getLogger(__name__)


def process_assistant_message(msg: Any, tracker: Any, transcript: Any) -> None:
    """Process an assistant message (deprecated stub).

    This function previously processed claude-agent-sdk AssistantMessage
    objects. It is no longer used in the LangGraph-based pipeline.
    Message processing is now handled by FlashlightCallbackHandler.

    Args:
        msg: Message to process (no longer used).
        tracker: Tracker instance (no longer used).
        transcript: TranscriptWriter instance (no longer used).
    """
    logger.warning(
        "process_assistant_message() is deprecated. "
        "Use FlashlightCallbackHandler instead."
    )
