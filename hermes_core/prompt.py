"""Hermes Core — system prompt assembly."""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CONTEXT_THREAT_PATTERNS = [
    (r"ignore\s+(previous|all|above|prior)\s+instructions", "prompt_injection"),
    (r"do\s+not\s+tell\s+the\s+user", "deception_hide"),
    (r"system\s+prompt\s+override", "sys_prompt_override"),
    (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
    (r"<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->", "html_comment_injection"),
    (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl"),
]

DEFAULT_AGENT_IDENTITY = (
    "You are Hermes Agent, an intelligent AI assistant. "
    "You are helpful, knowledgeable, and direct. You assist users with a wide "
    "range of tasks including answering questions, writing and editing code, "
    "analyzing information, creative work, and executing actions via your tools. "
    "You communicate clearly, admit uncertainty when appropriate, and prioritize "
    "being genuinely useful over being verbose."
)

TOOL_USE_GUIDANCE = (
    "# Tool-use enforcement\n"
    "You MUST use your tools to take action. "
    "Keep working until the task is actually complete. "
    "Every response should either (a) contain tool calls that make progress, or "
    "(b) deliver a final result to the user."
)

CONTEXT_FILE_MAX_CHARS = 20_000
_HERMES_MD_NAMES = (".hermes.md", "HERMES.md")


def _scan_context_content(content: str, filename: str) -> str:
    findings = []
    for pattern, pid in _CONTEXT_THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(pid)
    if findings:
        logger.warning("Context file %s blocked: %s", filename, ", ".join(findings))
        return f"[BLOCKED: {filename} — potential prompt injection]"
    return content


def _find_git_root(start: Path) -> Optional[Path]:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _find_hermes_md(cwd: Path) -> Optional[Path]:
    stop_at = _find_git_root(cwd)
    current = cwd.resolve()
    for directory in [current, *current.parents]:
        for name in _HERMES_MD_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
        if stop_at and directory == stop_at:
            break
    return None


def _strip_yaml_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            body = content[end + 4:].lstrip("\n")
            return body if body else content
    return content


def _truncate_content(content: str, filename: str, max_chars: int = CONTEXT_FILE_MAX_CHARS) -> str:
    if len(content) <= max_chars:
        return content
    head_chars = int(max_chars * 0.7)
    tail_chars = int(max_chars * 0.2)
    head = content[:head_chars]
    tail = content[-tail_chars:]
    marker = f"\n\n[...truncated {filename}]\n\n"
    return head + marker + tail


def _load_hermes_md(cwd_path: Path) -> str:
    hermes_md_path = _find_hermes_md(cwd_path)
    if not hermes_md_path:
        return ""
    try:
        content = hermes_md_path.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        content = _strip_yaml_frontmatter(content)
        rel = hermes_md_path.name
        try:
            rel = str(hermes_md_path.relative_to(cwd_path))
        except ValueError:
            pass
        content = _scan_context_content(content, rel)
        result = f"## {rel}\n\n{content}"
        return _truncate_content(result, ".hermes.md")
    except Exception as e:
        logger.debug("Could not read %s: %s", hermes_md_path, e)
        return ""


def _load_agents_md(cwd_path: Path) -> str:
    for name in ["AGENTS.md", "agents.md"]:
        candidate = cwd_path / name
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8").strip()
                if content:
                    content = _scan_context_content(content, name)
                    result = f"## {name}\n\n{content}"
                    return _truncate_content(result, "AGENTS.md")
            except Exception as e:
                logger.debug("Could not read %s: %s", candidate, e)
    return ""


def _load_claude_md(cwd_path: Path) -> str:
    for name in ["CLAUDE.md", "claude.md"]:
        candidate = cwd_path / name
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8").strip()
                if content:
                    content = _scan_context_content(content, name)
                    result = f"## {name}\n\n{content}"
                    return _truncate_content(result, "CLAUDE.md")
            except Exception as e:
                logger.debug("Could not read %s: %s", candidate, e)
    return ""


def build_context_files_prompt(cwd: Optional[str] = None) -> str:
    if cwd is None:
        cwd = os.getcwd()
    cwd_path = Path(cwd).resolve()
    project_context = (
        _load_hermes_md(cwd_path)
        or _load_agents_md(cwd_path)
        or _load_claude_md(cwd_path)
    )
    if not project_context:
        return ""
    return "# Project Context\n\nThe following project context files have been loaded and should be followed:\n\n" + project_context


def build_system_prompt(
    system_message: Optional[str] = None,
    skip_context_files: bool = False,
    platform: str = "cli",
) -> str:
    parts = []

    if system_message:
        parts.append(system_message)
    else:
        parts.append(DEFAULT_AGENT_IDENTITY)

    parts.append(TOOL_USE_GUIDANCE)

    if not skip_context_files:
        ctx = build_context_files_prompt()
        if ctx:
            parts.append(ctx)

    return "\n\n".join(parts)
