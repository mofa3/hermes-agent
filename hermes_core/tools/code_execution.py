"""Hermes Core — code execution sandbox tool."""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

EXECUTE_CODE_SCHEMA = {
    "name": "execute_code",
    "description": "Execute Python code in a sandboxed environment. The code runs in a temporary directory. Use this for calculations, data processing, or calling other tools programmatically. Available tools in sandbox: web_search, terminal. Import them with: from hermes_core.tools.web_tools import web_search",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
        },
        "required": ["code"],
    },
}


def execute_code(code: str, task_id: str | None = None) -> str:
    if not code.strip():
        return json.dumps({"error": "No code provided"})

    with tempfile.TemporaryDirectory(prefix="hermes_sandbox_") as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        script_path.write_text(code, encoding="utf-8")

        try:
            result = subprocess.run(
                ["python3", str(script_path)],
                capture_output=True, text=True, timeout=60,
                cwd=tmpdir, env={**os.environ, "PYTHONPATH": os.getcwd()},
            )
            output = result.stdout
            if result.stderr:
                output += "\n[stderr]\n" + result.stderr
            return json.dumps({
                "exit_code": result.returncode,
                "output": output.strip() or "(no output)",
            })
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Code execution timed out (60s)"})
        except Exception as e:
            return json.dumps({"error": f"Execution failed: {e}"})
