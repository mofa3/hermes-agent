"""Hermes Core — model metadata and context length utilities."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PROVIDER_PREFIXES = frozenset({
    "openrouter", "anthropic", "deepseek", "openai", "google",
    "xai", "ollama", "custom", "local",
})

DEFAULT_CONTEXT_LENGTHS: Dict[str, int] = {
    "claude-opus-4": 1000000,
    "claude-sonnet-4": 1000000,
    "claude": 200000,
    "gpt-5": 400000,
    "gpt-4.1": 1047576,
    "gpt-4": 128000,
    "gemini": 1048576,
    "deepseek": 128000,
    "llama": 131072,
    "grok": 131072,
    "qwen": 131072,
}

DEFAULT_FALLBACK_CONTEXT = 128000
_CHARS_PER_TOKEN = 4


def _strip_provider_prefix(model: str) -> str:
    if ":" not in model or model.startswith("http"):
        return model
    prefix, suffix = model.split(":", 1)
    if prefix.strip().lower() in _PROVIDER_PREFIXES:
        return suffix
    return model


def get_model_context_length(model: str) -> int:
    model = _strip_provider_prefix(model).lower()
    for key, length in sorted(DEFAULT_CONTEXT_LENGTHS.items(), key=lambda x: -len(x[0])):
        if key in model:
            return length
    return DEFAULT_FALLBACK_CONTEXT


def estimate_tokens_rough(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def estimate_messages_tokens_rough(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens_rough(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += estimate_tokens_rough(str(part.get("text", "")))
        total += 4
    return total


def estimate_request_tokens_rough(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> int:
    total = estimate_messages_tokens_rough(messages)
    if tools:
        for tool in tools:
            total += estimate_tokens_rough(str(tool))
    return total
