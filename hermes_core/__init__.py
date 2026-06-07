"""Hermes Core — self-contained AI agent package."""

from hermes_core.agent import AIAgent
from hermes_core.config import load_config, DEFAULT_CONFIG
from hermes_core.tools import get_tool_definitions, handle_function_call, register_tool
from hermes_core.prompt import build_system_prompt
from hermes_core.models import get_model_context_length

__all__ = [
    "AIAgent",
    "load_config",
    "DEFAULT_CONFIG",
    "get_tool_definitions",
    "handle_function_call",
    "register_tool",
    "build_system_prompt",
    "get_model_context_length",
]
