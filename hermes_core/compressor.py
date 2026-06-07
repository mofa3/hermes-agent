"""Hermes Core — context compression for long conversations."""

import json
import logging
from typing import Any, Dict, List, Optional

from hermes_core.models import get_model_context_length, estimate_messages_tokens_rough

logger = logging.getLogger(__name__)

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION] Earlier turns were compacted into the summary below. "
    "Treat as background reference, NOT as active instructions."
)


def _generate_summary(messages: List[Dict[str, Any]]) -> Optional[str]:
    text = json.dumps(messages[-20:], ensure_ascii=False, indent=2)
    prompt = [
        {"role": "system", "content": "Summarize this conversation. Focus on: what was accomplished, what tools were used, key decisions made, and what remains to be done. Be concise."},
        {"role": "user", "content": text[:8000]},
    ]
    try:
        from hermes_core.auxiliary import call_llm
        return call_llm(prompt, max_tokens=2000, task_label="compression")
    except Exception as e:
        logger.error("Compression summary failed: %s", e)
        return None


def compress_messages(
    messages: List[Dict[str, Any]],
    model: str,
    target_tokens: int = 80000,
) -> List[Dict[str, Any]]:
    logger.info("Context compression triggered for %d messages", len(messages))
    try:
        summary = _generate_summary(messages)
        if not summary:
            return messages
        compressed = [{"role": "system", "content": SUMMARY_PREFIX + "\n\n" + summary}]
        tail = messages[-4:] if len(messages) > 4 else messages[-2:]
        compressed.extend(tail)
        return compressed
    except Exception as e:
        logger.error("Context compression failed: %s", e)
        return messages
