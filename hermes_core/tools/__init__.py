"""Hermes Core — tool registry, dispatch, and built-in tool implementations."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

TOOL_RESULT_MAX_CHARS = 50_000


class ToolRegistry:
    """Minimal tool registry for registering and dispatching tool calls."""

    def __init__(self):
        self._tools: Dict[str, dict] = {}

    def register(
        self,
        name: str,
        schema: dict,
        handler: Callable,
        check_fn: Optional[Callable] = None,
        requires_env: Optional[List[str]] = None,
    ):
        self._tools[name] = {
            "name": name,
            "schema": schema,
            "handler": handler,
            "check_fn": check_fn,
            "requires_env": requires_env or [],
        }

    def get_definitions(self, tool_names: Optional[Set[str]] = None) -> List[dict]:
        result = []
        for name, entry in sorted(self._tools.items()):
            if tool_names and name not in tool_names:
                continue
            if entry["check_fn"]:
                try:
                    if not entry["check_fn"]():
                        continue
                except Exception:
                    continue
            schema = {**entry["schema"], "name": name}
            result.append({"type": "function", "function": schema})
        return result

    def dispatch(self, name: str, args: dict, **kwargs) -> str:
        entry = self._tools.get(name)
        if not entry:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            return entry["handler"](args, **kwargs)
        except Exception as e:
            logger.exception("Tool %s dispatch error: %s", name, e)
            return json.dumps({"error": f"Tool execution failed: {e}"})

    def get_all_tool_names(self) -> List[str]:
        return sorted(self._tools.keys())


_registry = ToolRegistry()


def register_tool(
    name: str,
    schema: dict,
    handler: Callable,
    check_fn: Optional[Callable] = None,
    requires_env: Optional[List[str]] = None,
):
    _registry.register(name, schema, handler, check_fn, requires_env)


def get_tool_definitions(
    enabled_toolsets: Optional[List[str]] = None,
    disabled_toolsets: Optional[List[str]] = None,
) -> List[dict]:
    from hermes_core.toolsets import resolve_enabled_tools
    tool_names = resolve_enabled_tools(enabled_toolsets, disabled_toolsets)
    return _registry.get_definitions(tool_names)


def handle_function_call(name: str, args: dict, **kwargs) -> str:
    return _registry.dispatch(name, args, **kwargs)


def _truncate_result(result: str, max_chars: int = TOOL_RESULT_MAX_CHARS) -> str:
    if len(result) <= max_chars:
        return result
    head = result[:int(max_chars * 0.7)]
    tail = result[-int(max_chars * 0.2):]
    return head + f"\n\n[...truncated {len(result) - max_chars} chars]\n\n" + tail


def _register_builtin_tools():
    from hermes_core.tools.file_tools import (
        READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, PATCH_SCHEMA, SEARCH_FILES_SCHEMA,
        read_file, write_file, patch, search_files,
    )
    from hermes_core.tools.terminal_tool import (
        TERMINAL_SCHEMA, PROCESS_SCHEMA,
        terminal, process,
    )
    from hermes_core.tools.web_tools import (
        WEB_SEARCH_SCHEMA, WEB_EXTRACT_SCHEMA,
        web_search, web_extract, _check_web_requirements,
    )
    from hermes_core.tools.memory_tools import (
        MEMORY_SCHEMA, TODO_SCHEMA,
        memory, todo,
    )
    from hermes_core.tools.code_execution import (
        EXECUTE_CODE_SCHEMA,
        execute_code,
    )

    _registry.register("read_file", READ_FILE_SCHEMA,
                       lambda a, **kw: read_file(a.get("path", ""), a.get("offset", 1), a.get("limit", 500)))
    _registry.register("write_file", WRITE_FILE_SCHEMA,
                       lambda a, **kw: write_file(a.get("path", ""), a.get("content", "")))
    _registry.register("patch", PATCH_SCHEMA,
                       lambda a, **kw: patch(a.get("path", ""), a.get("old_string", ""), a.get("new_string", ""), a.get("replace_all", False)))
    _registry.register("search_files", SEARCH_FILES_SCHEMA,
                       lambda a, **kw: search_files(a.get("pattern", ""), a.get("target", "content"), a.get("path", "."), a.get("file_glob"), a.get("limit", 50), a.get("output_mode", "content")))

    _registry.register("terminal", TERMINAL_SCHEMA,
                       lambda a, **kw: terminal(a.get("command", ""), a.get("background", False), a.get("timeout"), a.get("workdir"), a.get("notify_on_complete", False), kw.get("task_id")))
    _registry.register("process", PROCESS_SCHEMA,
                       lambda a, **kw: process(a.get("action", ""), a.get("session_id"), a.get("data"), a.get("timeout"), a.get("offset", 0)))

    _registry.register("web_search", WEB_SEARCH_SCHEMA,
                       lambda a, **kw: web_search(a.get("query", "")),
                       check_fn=_check_web_requirements)
    _registry.register("web_extract", WEB_EXTRACT_SCHEMA,
                       lambda a, **kw: web_extract(a.get("urls", [])),
                       check_fn=_check_web_requirements)

    _registry.register("memory", MEMORY_SCHEMA,
                       lambda a, **kw: memory(a.get("action", ""), a.get("target", "memory"), a.get("content"), a.get("old_text")))
    _registry.register("todo", TODO_SCHEMA,
                       lambda a, **kw: todo(a.get("todos"), a.get("merge", False)))

    _registry.register("execute_code", EXECUTE_CODE_SCHEMA,
                       lambda a, **kw: execute_code(a.get("code", ""), kw.get("task_id")))


_register_builtin_tools()
