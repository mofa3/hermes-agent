"""Hermes Core — terminal and process tools."""

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

FOREGROUND_MAX_TIMEOUT = 600

TERMINAL_SCHEMA = {
    "name": "terminal",
    "description": "Execute a shell command. Use this for running code, installing packages, git operations, builds, tests, and any CLI tool. Returns stdout+stderr with exit code. For long-running commands, use background=true.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute"},
            "background": {"type": "boolean", "description": "Run in background. Use for servers, watchers, or long tasks.", "default": False},
            "timeout": {"type": "integer", "description": f"Max seconds to wait (default: 180, max: {FOREGROUND_MAX_TIMEOUT})", "minimum": 1},
            "workdir": {"type": "string", "description": "Working directory for this command (absolute path)."},
            "notify_on_complete": {"type": "boolean", "description": "When true (and background=true), notify when process finishes.", "default": False},
        },
        "required": ["command"],
    },
}

PROCESS_SCHEMA = {
    "name": "process",
    "description": "Manage background processes started with terminal(background=true). Actions: 'list' (show all), 'poll' (check status + new output), 'log' (full output), 'wait' (block until done), 'kill' (terminate), 'write' (send stdin data), 'submit' (send data + Enter), 'close' (close stdin).",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "poll", "log", "wait", "kill", "write", "submit", "close"], "description": "Action to perform"},
            "session_id": {"type": "string", "description": "Process session ID. Required for all actions except 'list'."},
            "data": {"type": "string", "description": "Text to send to process stdin (for 'write' and 'submit')"},
            "timeout": {"type": "integer", "description": "Max seconds to block for 'wait' action.", "minimum": 1},
            "offset": {"type": "integer", "description": "Line offset for 'log' action (default: 0)", "default": 0},
        },
        "required": ["action"],
    },
}

_background_processes: dict[str, dict] = {}
_process_lock = threading.Lock()


def _resolve_workdir(workdir: str | None) -> str:
    if workdir:
        return os.path.expanduser(workdir)
    return os.getcwd()


def terminal(command: str, background: bool = False, timeout: int | None = None,
             workdir: str | None = None, notify_on_complete: bool = False,
             task_id: str | None = None) -> str:
    cwd = _resolve_workdir(workdir)

    if background:
        return _run_background(command, cwd, notify_on_complete)

    effective_timeout = min(timeout or 180, FOREGROUND_MAX_TIMEOUT)
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=effective_timeout, cwd=cwd, env={**os.environ},
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        return json.dumps({
            "exit_code": result.returncode,
            "output": output.strip() or "(no output)",
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {effective_timeout}s"})
    except Exception as e:
        return json.dumps({"error": f"Command failed: {e}"})


def _run_background(command: str, cwd: str, notify: bool) -> str:
    import uuid
    session_id = str(uuid.uuid4())[:8]

    proc = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd, env={**os.environ},
    )

    with _process_lock:
        _background_processes[session_id] = {
            "process": proc,
            "command": command,
            "cwd": cwd,
            "started": time.time(),
            "notify": notify,
            "output_lines": [],
            "read_offset": 0,
        }

    return json.dumps({
        "session_id": session_id,
        "message": f"Started background process [{session_id}]: {command}",
        "status": "running",
    })


def process(action: str, session_id: str | None = None, data: str | None = None,
            timeout: int | None = None, offset: int = 0) -> str:
    with _process_lock:
        if action == "list":
            items = []
            for sid, info in _background_processes.items():
                proc = info["process"]
                status = "running" if proc.poll() is None else f"exited({proc.returncode})"
                items.append({
                    "session_id": sid,
                    "command": info["command"],
                    "status": status,
                    "elapsed": round(time.time() - info["started"], 1),
                })
            return json.dumps({"processes": items} if items else {"message": "No background processes"})

        if not session_id or session_id not in _background_processes:
            return json.dumps({"error": f"Process not found: {session_id}"})

        info = _background_processes[session_id]
        proc = info["process"]

        if action == "kill":
            proc.kill()
            return json.dumps({"message": f"Killed process [{session_id}]"})

        if action == "write":
            try:
                proc.stdin.write(data or "")
                proc.stdin.flush()
                return json.dumps({"message": "Data sent"})
            except Exception as e:
                return json.dumps({"error": f"Write failed: {e}"})

        if action == "submit":
            try:
                proc.stdin.write((data or "") + "\n")
                proc.stdin.flush()
                return json.dumps({"message": "Data submitted"})
            except Exception as e:
                return json.dumps({"error": f"Submit failed: {e}"})

        if action == "close":
            try:
                proc.stdin.close()
                return json.dumps({"message": "stdin closed"})
            except Exception:
                return json.dumps({"message": "stdin already closed"})

        if action == "poll":
            return_code = proc.poll()
            status = "running" if return_code is None else f"exited({return_code})"
            return json.dumps({
                "session_id": session_id,
                "status": status,
                "elapsed": round(time.time() - info["started"], 1),
            })

        if action == "log":
            try:
                proc.stdout.seek(0)
                full_output = proc.stdout.read()
            except Exception:
                full_output = ""
            lines = full_output.split("\n")
            selected = lines[offset:offset + 500]
            return "\n".join(selected) if selected else "(no output)"

        if action == "wait":
            effective_timeout = timeout or 60
            try:
                return_code = proc.wait(timeout=effective_timeout)
                return json.dumps({
                    "session_id": session_id,
                    "exit_code": return_code,
                    "message": f"Process exited with code {return_code}",
                })
            except subprocess.TimeoutExpired:
                return json.dumps({"message": f"Process still running after {effective_timeout}s"})

    return json.dumps({"error": f"Unknown action: {action}"})
