"""Hermes Core — file tools: read, write, patch, search."""

import json
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_READ_CHARS = 100_000

READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": "Read a text file with line numbers and pagination. Use this instead of cat/head/tail in terminal. Output format: 'LINE_NUM|CONTENT'. Use offset and limit for large files. Reads exceeding ~100K characters are rejected; use offset and limit to read specific sections.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read (absolute, relative, or ~/path)"},
            "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed, default: 1)", "default": 1, "minimum": 1},
            "limit": {"type": "integer", "description": "Maximum number of lines to read (default: 500, max: 2000)", "default": 500, "maximum": 2000},
        },
        "required": ["path"],
    },
}

WRITE_FILE_SCHEMA = {
    "name": "write_file",
    "description": "Write content to a file, completely replacing existing content. Use this instead of echo/cat heredoc in terminal. Creates parent directories automatically. OVERWRITES the entire file — use 'patch' for targeted edits.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write (will be created if it doesn't exist, overwritten if it does)"},
            "content": {"type": "string", "description": "Complete content to write to the file"},
        },
        "required": ["path", "content"],
    },
}

PATCH_SCHEMA = {
    "name": "patch",
    "description": "Targeted find-and-replace edits in files. Use this instead of sed/awk in terminal. Returns a unified diff.\n\nReplace mode (default): find a unique string and replace it.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to edit"},
            "old_string": {"type": "string", "description": "Text to find in the file. Must be unique unless replace_all=true."},
            "new_string": {"type": "string", "description": "Replacement text. Can be empty string to delete the matched text."},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences (default: false)", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    },
}

SEARCH_FILES_SCHEMA = {
    "name": "search_files",
    "description": "Search file contents or find files by name. Use this instead of grep/rg/find/ls in terminal.\n\nContent search (target='content'): Regex search inside files.\nFile search (target='files'): Find files by glob pattern.",
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern for content search, or glob pattern for file search"},
            "target": {"type": "string", "enum": ["content", "files"], "description": "'content' searches inside file contents, 'files' searches for files by name", "default": "content"},
            "path": {"type": "string", "description": "Directory or file to search in (default: current working directory)", "default": "."},
            "file_glob": {"type": "string", "description": "Filter files by pattern in grep mode (e.g., '*.py')"},
            "limit": {"type": "integer", "description": "Maximum number of results (default: 50)", "default": 50},
            "output_mode": {"type": "string", "enum": ["content", "files_only", "count"], "description": "Output format", "default": "content"},
        },
        "required": ["pattern"],
    },
}


def _resolve_path(filepath: str) -> Path:
    return Path(os.path.expanduser(filepath)).resolve()


def read_file(path: str, offset: int = 1, limit: int = 500) -> str:
    filepath = _resolve_path(path)
    if not filepath.exists():
        return json.dumps({"error": f"File not found: {path}"})
    if filepath.is_dir():
        return json.dumps({"error": f"Path is a directory: {path}"})

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return json.dumps({"error": f"Failed to read file: {e}"})

    lines = text.split("\n")
    total_lines = len(lines)
    start = max(0, offset - 1)
    end = min(start + limit, total_lines)
    selected = lines[start:end]

    output_lines = []
    for i, line in enumerate(selected, start=start + 1):
        output_lines.append(f"{i}|{line}")

    result = "\n".join(output_lines)
    if len(result) > MAX_READ_CHARS:
        result = result[:MAX_READ_CHARS] + f"\n\n[...truncated at {MAX_READ_CHARS} chars, {total_lines} total lines]"

    return result


def write_file(path: str, content: str) -> str:
    filepath = _resolve_path(path)
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        size = filepath.stat().st_size
        return json.dumps({"success": True, "path": str(filepath), "size": size})
    except Exception as e:
        return json.dumps({"error": f"Failed to write file: {e}"})


def patch(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    filepath = _resolve_path(path)
    if not filepath.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return json.dumps({"error": f"Failed to read file: {e}"})

    count = content.count(old_string)
    if count == 0:
        return json.dumps({"error": f"old_string not found in file: {path}"})
    if count > 1 and not replace_all:
        return json.dumps({"error": f"Found {count} matches for old_string. Use replace_all=true or provide more context to make it unique."})

    new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

    try:
        filepath.write_text(new_content, encoding="utf-8")
        return json.dumps({"success": True, "path": str(filepath), "replacements": count if replace_all else 1})
    except Exception as e:
        return json.dumps({"error": f"Failed to write file: {e}"})


def search_files(pattern: str, target: str = "content", path: str = ".",
                 file_glob: str = None, limit: int = 50,
                 output_mode: str = "content") -> str:
    search_path = _resolve_path(path)

    if target == "files":
        try:
            import glob as glob_mod
            results = sorted(Path(search_path).rglob(pattern))[:limit]
            lines = [str(p) for p in results]
            return "\n".join(lines) if lines else json.dumps({"result": "No files found"})
        except Exception as e:
            return json.dumps({"error": f"File search failed: {e}"})

    if target == "content":
        try:
            rg_args = ["rg", "--line-number", "--no-heading", "--color=never"]
            if file_glob:
                rg_args.extend(["--glob", file_glob])
            if output_mode == "files_only":
                rg_args.append("-l")
            elif output_mode == "count":
                rg_args.append("-c")
            rg_args.extend([pattern, str(search_path)])

            result = subprocess.run(
                rg_args, capture_output=True, text=True, timeout=30,
            )
            output = result.stdout.strip()
            if not output:
                return json.dumps({"result": "No matches found"})

            lines = output.split("\n")[:limit]
            return "\n".join(lines)
        except FileNotFoundError:
            return _python_grep(pattern, search_path, file_glob, limit, output_mode)
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Search timed out"})
        except Exception as e:
            return json.dumps({"error": f"Search failed: {e}"})

    return json.dumps({"error": f"Unknown target: {target}"})


def _python_grep(pattern: str, search_path: Path, file_glob: str | None,
                 limit: int, output_mode: str) -> str:
    """Python fallback for content search when ripgrep is not installed."""
    import fnmatch
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return json.dumps({"error": f"Invalid regex pattern: {e}"})

    results = []
    files_searched = 0
    for filepath in search_path.rglob("*"):
        if files_searched > 500:
            break
        if not filepath.is_file():
            continue
        if filepath.name.startswith("."):
            continue
        if file_glob and not fnmatch.fnmatch(filepath.name, file_glob):
            continue
        try:
            if filepath.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        files_searched += 1

        try:
            lines = filepath.read_text(errors="replace").split("\n")
        except Exception:
            continue

        match_count = 0
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                match_count += 1
                if output_mode == "content" and len(results) < limit:
                    results.append(f"{filepath}:{i}:{line}")
                elif output_mode == "count":
                    pass
                elif output_mode == "files_only":
                    if str(filepath) not in results:
                        results.append(str(filepath))
                    break

        if output_mode == "count" and match_count > 0:
            results.append(f"{filepath}:{match_count}")

    if not results:
        return json.dumps({"result": "No matches found"})
    return "\n".join(results[:limit])
