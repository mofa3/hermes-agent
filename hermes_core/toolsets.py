"""Hermes Core — toolset definitions."""

from typing import Dict, List, Optional, Set

_CORE_TOOLS = [
    "web_search", "web_extract",
    "terminal", "process",
    "read_file", "write_file", "patch", "search_files",
    "todo", "memory",
    "execute_code",
]

TOOLSETS: Dict[str, dict] = {
    "web": {
        "description": "Web research and content extraction tools",
        "tools": ["web_search", "web_extract"],
    },
    "terminal": {
        "description": "Terminal/command execution and process management tools",
        "tools": ["terminal", "process"],
    },
    "file": {
        "description": "File manipulation tools: read, write, patch, search",
        "tools": ["read_file", "write_file", "patch", "search_files"],
    },
    "todo": {
        "description": "Task planning and tracking for multi-step work",
        "tools": ["todo"],
    },
    "memory": {
        "description": "Persistent memory across sessions",
        "tools": ["memory"],
    },
    "code_execution": {
        "description": "Run Python scripts that call tools programmatically",
        "tools": ["execute_code"],
    },
    "core": {
        "description": "All core tools",
        "tools": _CORE_TOOLS,
    },
}


def resolve_enabled_tools(
    enabled: Optional[List[str]] = None,
    disabled: Optional[List[str]] = None,
) -> Set[str]:
    if enabled is not None:
        tools: Set[str] = set()
        for ts_name in enabled:
            ts = TOOLSETS.get(ts_name, {})
            tools.update(ts.get("tools", []))
        return tools

    if disabled is not None:
        tools: Set[str] = set()
        for ts in TOOLSETS.values():
            tools.update(ts.get("tools", []))
        for ts_name in disabled:
            ts = TOOLSETS.get(ts_name, {})
            tools.difference_update(ts.get("tools", []))
        return tools

    tools = set()
    for ts in TOOLSETS.values():
        tools.update(ts.get("tools", []))
    return tools


def get_all_toolsets() -> Dict[str, dict]:
    return dict(TOOLSETS)


def validate_toolset(name: str) -> bool:
    return name in TOOLSETS
