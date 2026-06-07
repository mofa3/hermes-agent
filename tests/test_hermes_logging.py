"""Tests for hermes_logging — centralized logging setup."""

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

import hermes_logging


@pytest.fixture(autouse=True)
def _reset_logging_state():
    hermes_logging._logging_initialized = False
    root = logging.getLogger()
    pre_existing = []
    for h in list(root.handlers):
        if isinstance(h, RotatingFileHandler):
            root.removeHandler(h)
            h.close()
        else:
            pre_existing.append(h)
    hermes_logging._install_session_record_factory()
    yield
    for h in list(root.handlers):
        if h not in pre_existing:
            root.removeHandler(h)
            h.close()
    hermes_logging._logging_initialized = False
    hermes_logging.clear_session_context()


@pytest.fixture
def hermes_home(tmp_path):
    home = Path(os.environ["HERMES_HOME"])
    return home


class TestSetupLogging:
    def test_creates_log_directory(self, hermes_home):
        log_dir = hermes_logging.setup_logging(hermes_home=hermes_home)
        assert log_dir == hermes_home / "logs"
        assert log_dir.is_dir()

    def test_creates_agent_log_handler(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        root = logging.getLogger()
        agent_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and "agent.log" in getattr(h, "baseFilename", "")
        ]
        assert len(agent_handlers) == 1
        assert agent_handlers[0].level == logging.INFO

    def test_idempotent_no_duplicate_handlers(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        hermes_logging.setup_logging(hermes_home=hermes_home)
        root = logging.getLogger()
        agent_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and "agent.log" in getattr(h, "baseFilename", "")
        ]
        assert len(agent_handlers) == 1

    def test_force_reinitializes(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        hermes_logging.setup_logging(hermes_home=hermes_home, force=True)
        root = logging.getLogger()
        agent_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and "agent.log" in getattr(h, "baseFilename", "")
        ]
        assert len(agent_handlers) >= 1

    def test_custom_log_level(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home, log_level="DEBUG")
        root = logging.getLogger()
        agent_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and "agent.log" in getattr(h, "baseFilename", "")
        ]
        assert agent_handlers[0].level == logging.DEBUG

    def test_custom_max_size_and_backup(self, hermes_home):
        hermes_logging.setup_logging(
            hermes_home=hermes_home, max_size_mb=10, backup_count=5
        )
        root = logging.getLogger()
        agent_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and "agent.log" in getattr(h, "baseFilename", "")
        ]
        assert agent_handlers[0].maxBytes == 10 * 1024 * 1024
        assert agent_handlers[0].backupCount == 5

    def test_suppresses_noisy_loggers(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        assert logging.getLogger("openai").level >= logging.WARNING
        assert logging.getLogger("httpx").level >= logging.WARNING
        assert logging.getLogger("httpcore").level >= logging.WARNING

    def test_writes_to_agent_log(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        test_logger = logging.getLogger("test_hermes_logging.write_test")
        test_logger.info("test message for agent.log")
        for h in logging.getLogger().handlers:
            h.flush()
        agent_log = hermes_home / "logs" / "agent.log"
        assert agent_log.exists()
        content = agent_log.read_text()
        assert "test message for agent.log" in content

    def test_reads_config_yaml(self, hermes_home):
        import yaml
        config = {"logging": {"level": "DEBUG", "max_size_mb": 2, "backup_count": 1}}
        (hermes_home / "config.yaml").write_text(yaml.dump(config))
        hermes_logging.setup_logging(hermes_home=hermes_home)
        root = logging.getLogger()
        agent_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and "agent.log" in getattr(h, "baseFilename", "")
        ]
        assert agent_handlers[0].level == logging.DEBUG
        assert agent_handlers[0].maxBytes == 2 * 1024 * 1024
        assert agent_handlers[0].backupCount == 1

    def test_explicit_params_override_config(self, hermes_home):
        import yaml
        config = {"logging": {"level": "DEBUG"}}
        (hermes_home / "config.yaml").write_text(yaml.dump(config))
        hermes_logging.setup_logging(hermes_home=hermes_home, log_level="WARNING")
        root = logging.getLogger()
        agent_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and "agent.log" in getattr(h, "baseFilename", "")
        ]
        assert agent_handlers[0].level == logging.WARNING

    def test_record_factory_installed(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        factory = logging.getLogRecordFactory()
        assert getattr(factory, "_hermes_session_injector", False)
        record = factory("test", logging.INFO, "", 0, "msg", (), None)
        assert hasattr(record, "session_tag")


class TestSessionContext:
    def test_session_tag_in_log_output(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        hermes_logging.set_session_context("abc123")
        test_logger = logging.getLogger("test.session_tag")
        test_logger.info("tagged message")
        for h in logging.getLogger().handlers:
            h.flush()
        agent_log = hermes_home / "logs" / "agent.log"
        content = agent_log.read_text()
        assert "[abc123]" in content
        assert "tagged message" in content

    def test_no_session_tag_without_context(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        hermes_logging.clear_session_context()
        test_logger = logging.getLogger("test.no_session")
        test_logger.info("untagged message")
        for h in logging.getLogger().handlers:
            h.flush()
        agent_log = hermes_home / "logs" / "agent.log"
        content = agent_log.read_text()
        assert "untagged message" in content

    def test_clear_session_context(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        hermes_logging.set_session_context("xyz789")
        hermes_logging.clear_session_context()
        test_logger = logging.getLogger("test.cleared")
        test_logger.info("after clear")
        for h in logging.getLogger().handlers:
            h.flush()
        agent_log = hermes_home / "logs" / "agent.log"
        content = agent_log.read_text()
        assert "[xyz789]" not in content

    def test_session_context_thread_isolated(self, hermes_home):
        hermes_logging.setup_logging(hermes_home=hermes_home)
        def thread_a():
            hermes_logging.set_session_context("thread_a_session")
            logging.getLogger("test.thread_a").info("from thread A")
            for h in logging.getLogger().handlers:
                h.flush()
        def thread_b():
            hermes_logging.set_session_context("thread_b_session")
            logging.getLogger("test.thread_b").info("from thread B")
            for h in logging.getLogger().handlers:
                h.flush()
        ta = threading.Thread(target=thread_a)
        tb = threading.Thread(target=thread_b)
        ta.start()
        ta.join()
        tb.start()
        tb.join()
        agent_log = hermes_home / "logs" / "agent.log"
        content = agent_log.read_text()
        for line in content.splitlines():
            if "from thread A" in line:
                assert "[thread_a_session]" in line
                assert "[thread_b_session]" not in line
            if "from thread B" in line:
                assert "[thread_b_session]" in line
                assert "[thread_a_session]" not in line


class TestRecordFactory:
    def test_record_has_session_tag(self):
        factory = logging.getLogRecordFactory()
        record = factory("test", logging.INFO, "", 0, "msg", (), None)
        assert hasattr(record, "session_tag")

    def test_empty_tag_without_context(self):
        hermes_logging.clear_session_context()
        factory = logging.getLogRecordFactory()
        record = factory("test", logging.INFO, "", 0, "msg", (), None)
        assert record.session_tag == ""

    def test_tag_with_context(self):
        hermes_logging.set_session_context("sess_42")
        factory = logging.getLogRecordFactory()
        record = factory("test", logging.INFO, "", 0, "msg", (), None)
        assert record.session_tag == " [sess_42]"

    def test_idempotent_install(self):
        hermes_logging._install_session_record_factory()
        factory_a = logging.getLogRecordFactory()
        hermes_logging._install_session_record_factory()
        factory_b = logging.getLogRecordFactory()
        assert factory_a is factory_b

    def test_works_with_any_handler(self):
        hermes_logging.set_session_context("any_handler_test")
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(session_tag)s %(message)s"))
        logger = logging.getLogger("_test_any_handler")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            logger.info("hello")
        finally:
            logger.removeHandler(handler)


class TestReadLoggingConfig:
    def test_returns_none_when_no_config(self, hermes_home):
        level, max_size, backup = hermes_logging._read_logging_config()
        assert level is None
        assert max_size is None
        assert backup is None

    def test_reads_logging_section(self, hermes_home):
        import yaml
        config = {"logging": {"level": "DEBUG", "max_size_mb": 10, "backup_count": 5}}
        (hermes_home / "config.yaml").write_text(yaml.dump(config))
        level, max_size, backup = hermes_logging._read_logging_config()
        assert level == "DEBUG"
        assert max_size == 10
        assert backup == 5

    def test_handles_missing_logging_section(self, hermes_home):
        import yaml
        config = {"model": "test"}
        (hermes_home / "config.yaml").write_text(yaml.dump(config))
        level, max_size, backup = hermes_logging._read_logging_config()
        assert level is None
