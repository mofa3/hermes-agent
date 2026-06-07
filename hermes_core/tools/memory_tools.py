"""Hermes Core — memory and todo tools."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_SCHEMA = {
    "name": "memory",
    "description": "Save durable information to persistent memory that survives across sessions. Use for user preferences, environment facts, project conventions, and lessons learned. Actions: add, replace, remove. Targets: 'memory' (your notes) or 'user' (user profile).",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "replace", "remove"], "description": "The action to perform."},
            "target": {"type": "string", "enum": ["memory", "user"], "description": "Which memory store: 'memory' for personal notes, 'user' for user profile."},
            "content": {"type": "string", "description": "The entry content. Required for 'add' and 'replace'."},
            "old_text": {"type": "string", "description": "Existing text to identify the entry for 'replace' or 'remove'."},
        },
        "required": ["action", "target"],
    },
}

TODO_SCHEMA = {
    "name": "todo",
    "description": "Manage your task list for the current session. Use for complex tasks with 3+ steps. Call with no parameters to read the current list. Provide 'todos' array to create/update items. merge=false: replace entire list. merge=true: update existing items by id.",
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "Task items to write. Omit to read current list.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Unique item identifier"},
                        "content": {"type": "string", "description": "Task description"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "Current status"},
                    },
                    "required": ["id", "content", "status"],
                },
            },
            "merge": {"type": "boolean", "description": "Merge with existing list instead of replacing (default: false)", "default": False},
        },
        "required": [],
    },
}


def _get_memory_dir() -> Path:
    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    mem_dir = Path(hermes_home) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    return mem_dir


def _get_memory_file(target: str) -> Path:
    return _get_memory_dir() / f"{target}.json"


def _load_memory(target: str) -> list[str]:
    path = _get_memory_file(target)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
    return []


def _save_memory(target: str, entries: list[str]):
    path = _get_memory_file(target)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


def memory(action: str, target: str, content: str | None = None,
           old_text: str | None = None) -> str:
    if target not in ("memory", "user"):
        return json.dumps({"error": f"Invalid target: {target}. Use 'memory' or 'user'."})

    entries = _load_memory(target)

    if action == "add":
        if not content:
            return json.dumps({"error": "content is required for 'add' action"})
        entries.append(content)
        _save_memory(target, entries)
        return json.dumps({"success": True, "action": "add", "target": target, "total": len(entries)})

    if action == "replace":
        if not content or not old_text:
            return json.dumps({"error": "content and old_text are required for 'replace' action"})
        for i, entry in enumerate(entries):
            if old_text in entry:
                entries[i] = content
                _save_memory(target, entries)
                return json.dumps({"success": True, "action": "replace", "target": target, "total": len(entries)})
        return json.dumps({"error": f"old_text not found in {target} entries"})

    if action == "remove":
        if not old_text:
            return json.dumps({"error": "old_text is required for 'remove' action"})
        new_entries = [e for e in entries if old_text not in e]
        if len(new_entries) == len(entries):
            return json.dumps({"error": f"old_text not found in {target} entries"})
        _save_memory(target, new_entries)
        return json.dumps({"success": True, "action": "remove", "target": target, "total": len(new_entries)})

    return json.dumps({"error": f"Unknown action: {action}"})


_todo_list: list[dict] = []


def todo(todos: list[dict] | None = None, merge: bool = False) -> str:
    global _todo_list

    if todos is None:
        if not _todo_list:
            return json.dumps({"todos": [], "message": "No tasks yet"})
        return json.dumps({"todos": _todo_list})

    if not merge:
        _todo_list = todos
    else:
        existing_ids = {t["id"]: i for i, t in enumerate(_todo_list)}
        for item in todos:
            if item["id"] in existing_ids:
                _todo_list[existing_ids[item["id"]]] = item
            else:
                _todo_list.append(item)

    return json.dumps({"todos": _todo_list})
