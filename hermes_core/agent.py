"""Hermes Core — AI Agent with tool calling.

Supports OpenAI and Anthropic protocols via the OpenAI client.
Handles the conversation loop, tool execution, and response management.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI

from hermes_core.config import load_config
from hermes_core.models import get_model_context_length, estimate_request_tokens_rough
from hermes_core.prompt import build_system_prompt
from hermes_core.tools import get_tool_definitions, handle_function_call, _truncate_result
from hermes_core.compressor import compress_messages
from hermes_core.retry import jittered_backoff

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-4.1"
DEFAULT_MAX_ITERATIONS = 90
DEFAULT_MAX_TOKENS = 32000
COMPRESSION_HEADROOM_RATIO = 0.85


def _sanitize_surrogates(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


class AIAgent:
    """Minimal AI agent with tool calling and conversation management."""

    def __init__(
        self,
        model: Optional[str] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        enabled_toolsets: Optional[List[str]] = None,
        disabled_toolsets: Optional[List[str]] = None,
        quiet_mode: bool = False,
        platform: str = "cli",
        session_id: Optional[str] = None,
        skip_context_files: bool = False,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        stream_callback: Optional[Callable] = None,
    ):
        config = load_config()
        model_cfg = config.get("model", {})

        self.model = model or model_cfg.get("default", DEFAULT_MODEL)
        self.max_iterations = max_iterations or model_cfg.get("max_iterations", DEFAULT_MAX_ITERATIONS)
        self.max_tokens = max_tokens or model_cfg.get("max_tokens", DEFAULT_MAX_TOKENS)
        self.enabled_toolsets = enabled_toolsets or config.get("tools", {}).get("enabled")
        self.disabled_toolsets = disabled_toolsets or config.get("tools", {}).get("disabled")
        self.quiet_mode = quiet_mode or config.get("display", {}).get("quiet_mode", False)
        self.platform = platform
        self.session_id = session_id
        self.skip_context_files = skip_context_files
        self.stream_callback = stream_callback

        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._client: Optional[OpenAI] = None
        self._tool_schemas: List[Dict[str, Any]] = []
        self._api_call_count = 0
        self._interrupted = False
        self._steer_text: Optional[str] = None

        self._init_client()
        self._init_tools()

    def _init_client(self):
        kwargs: Dict[str, Any] = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url
        self._client = OpenAI(**kwargs)

    def _init_tools(self):
        self._tool_schemas = get_tool_definitions(
            enabled_toolsets=self.enabled_toolsets,
            disabled_toolsets=self.disabled_toolsets,
        )

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._init_client()
        return self._client

    def _call_api(self, messages: List[Dict[str, Any]]) -> Any:
        client = self._get_client()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if self._tool_schemas:
            kwargs["tools"] = self._tool_schemas

        return client.chat.completions.create(**kwargs)

    def _execute_tool_calls(
        self,
        assistant_message: Dict[str, Any],
        messages: List[Dict[str, Any]],
        task_id: str,
    ) -> None:
        tool_calls = assistant_message.get("tool_calls", [])
        if not tool_calls:
            return

        for tool_call in tool_calls:
            fn_name = tool_call["function"]["name"]
            fn_args = json.loads(tool_call["function"]["arguments"])
            tool_call_id = tool_call.get("id", "")

            logger.info("Tool call: %s", fn_name)

            try:
                result = handle_function_call(fn_name, fn_args, task_id=task_id)
            except Exception as e:
                result = json.dumps({"error": f"Tool execution failed: {e}"}, ensure_ascii=False)

            result = _sanitize_surrogates(result)
            result = _truncate_result(result)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result,
            })

    def _check_compression(self, messages: List[Dict[str, Any]]) -> bool:
        ctx_len = get_model_context_length(self.model)
        estimated = estimate_request_tokens_rough(messages, self._tool_schemas)
        threshold = int(ctx_len * COMPRESSION_HEADROOM_RATIO)
        return estimated > threshold

    def interrupt(self, message: Optional[str] = None):
        self._interrupted = True

    def clear_interrupt(self):
        self._interrupted = False

    def steer(self, text: str):
        self._steer_text = text

    def run_conversation(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._api_call_count = 0
        self._interrupted = False

        system_prompt = build_system_prompt(
            system_message=system_message,
            skip_context_files=self.skip_context_files,
            platform=self.platform,
        )
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        effective_task_id = task_id or f"task_{int(time.time())}"

        while self._api_call_count < self.max_iterations:
            if self._interrupted:
                break

            if self._check_compression(messages):
                logger.info("Compressing context...")
                messages = compress_messages(messages, self.model)

            try:
                response = self._call_api(messages)
            except Exception as e:
                logger.error("API call failed: %s", e)
                delay = jittered_backoff(self._api_call_count + 1)
                logger.info("Retrying in %.1fs...", delay)
                time.sleep(delay)
                self._api_call_count += 1
                continue

            self._api_call_count += 1
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            assistant_msg: Dict[str, Any] = {"role": "assistant"}

            if choice.message.content:
                assistant_msg["content"] = choice.message.content

            if choice.message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]

            messages.append(assistant_msg)

            if finish_reason == "stop" or (finish_reason is None and not choice.message.tool_calls):
                return {
                    "final_response": choice.message.content or "",
                    "messages": messages,
                }

            if choice.message.tool_calls:
                self._execute_tool_calls(assistant_msg, messages, effective_task_id)

                if self._steer_text:
                    messages.append({"role": "user", "content": self._steer_text})
                    self._steer_text = None

        return {
            "final_response": "Maximum iterations reached.",
            "messages": messages,
        }

    def chat(self, message: str) -> str:
        result = self.run_conversation(message)
        return result.get("final_response", "")

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
