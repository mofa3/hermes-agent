"""Centralized logging setup for Hermes Agent — minimal core."""

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Sequence

_logging_initialized = False
_session_context = threading.local()

_LOG_FORMAT = "%(asctime)s %(levelname)s%(session_tag)s %(name)s: %(message)s"

_NOISY_LOGGERS = (
    "openai", "openai._base_client", "httpx", "httpcore",
    "asyncio", "hpack", "urllib3", "charset_normalizer", "markdown_it",
)


def _get_hermes_home() -> Path:
    home = os.environ.get("HERMES_HOME")
    if home:
        return Path(home)
    return Path.home() / ".hermes"


def _get_config_path() -> Path:
    return _get_hermes_home() / "config.yaml"


def set_session_context(session_id: str) -> None:
    _session_context.session_id = session_id


def clear_session_context() -> None:
    _session_context.session_id = None


def _install_session_record_factory() -> None:
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, "_hermes_session_injector", False):
        return

    def _session_record_factory(*args, **kwargs):
        record = current_factory(*args, **kwargs)
        sid = getattr(_session_context, "session_id", None)
        record.session_tag = f" [{sid}]" if sid else ""
        return record

    _session_record_factory._hermes_session_injector = True
    logging.setLogRecordFactory(_session_record_factory)


_install_session_record_factory()


def _read_logging_config():
    try:
        import yaml
        config_path = _get_config_path()
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            log_cfg = cfg.get("logging", {})
            if isinstance(log_cfg, dict):
                return (
                    log_cfg.get("level"),
                    log_cfg.get("max_size_mb"),
                    log_cfg.get("backup_count"),
                )
    except Exception:
        pass
    return (None, None, None)


def setup_logging(
    *,
    hermes_home: Optional[Path] = None,
    log_level: Optional[str] = None,
    max_size_mb: Optional[int] = None,
    backup_count: Optional[int] = None,
    mode: Optional[str] = None,
    force: bool = False,
) -> Path:
    global _logging_initialized
    if _logging_initialized and not force:
        home = hermes_home or _get_hermes_home()
        return home / "logs"

    home = hermes_home or _get_hermes_home()
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cfg_level, cfg_max_size, cfg_backup = _read_logging_config()

    level_name = (log_level or cfg_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    max_bytes = (max_size_mb or cfg_max_size or 5) * 1024 * 1024
    backups = backup_count or cfg_backup or 3

    root = logging.getLogger()

    handler = RotatingFileHandler(
        str(log_dir / "agent.log"),
        maxBytes=max_bytes, backupCount=backups, encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(handler)

    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _logging_initialized = True
    return log_dir
