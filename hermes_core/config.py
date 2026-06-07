"""Hermes Core — configuration management."""

import copy
import os
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG: Dict[str, Any] = {
    "model": {
        "default": "openai/gpt-4.1",
        "max_tokens": 32000,
        "max_iterations": 90,
    },
    "tools": {
        "enabled": None,
        "disabled": None,
    },
    "display": {
        "quiet_mode": False,
    },
    "agent": {
        "context_compression": True,
    },
}


def get_hermes_home() -> Path:
    home = os.environ.get("HERMES_HOME")
    if home:
        return Path(home)
    return Path.home() / ".hermes"


def get_config_path() -> Path:
    return get_hermes_home() / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _expand_env_vars(config: dict) -> dict:
    def _walk(obj):
        if isinstance(obj, str) and obj.startswith("$"):
            return os.environ.get(obj[1:], obj)
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v) for v in obj]
        return obj
    return _walk(config)


def load_config() -> Dict[str, Any]:
    get_hermes_home().mkdir(parents=True, exist_ok=True)
    config_path = get_config_path()
    config = copy.deepcopy(DEFAULT_CONFIG)

    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, user_config)
        except Exception:
            pass

    return _expand_env_vars(config)
