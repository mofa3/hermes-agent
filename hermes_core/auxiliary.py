"""Hermes Core — auxiliary LLM client for compression and summarization."""

import logging
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


def call_llm(
    messages: List[Dict[str, Any]],
    max_tokens: int = 2000,
    task_label: str = "auxiliary",
) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        logger.warning("No API key available for auxiliary LLM call (%s)", task_label)
        return None

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model="openai/gpt-4.1-mini",
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("Auxiliary LLM call failed (%s): %s", task_label, e)
        return None
