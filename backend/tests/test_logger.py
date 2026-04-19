"""Unit tests for logger module."""

import json
import logging
import os
from io import StringIO

import pytest


class TestLoggerCreation:
    """Tests for logger creation."""

    def test_get_logger_returns_logger_instance(self):
        from app.utils.logger import get_logger

        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_has_correct_name(self):
        from app.utils.logger import get_logger

        logger = get_logger("test_module")
        assert logger.name == "test_module"

    def test_get_logger_has_json_formatter(self):
        from app.utils.logger import get_logger

        logger = get_logger("test_module")
        assert len(logger.handlers) > 0
        assert isinstance(logger.handlers[0].formatter, logging.Formatter)


class TestJSONFormat:
    """Tests for JSON log format."""

    def test_log_output_is_valid_json(self):
        from app.utils.logger import get_logger

        logger = get_logger("test_json")
        output = StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(logger.handlers[0].formatter)
        logger.handlers = [handler]

        logger.info("test message")
        log_line = output.getvalue()
        parsed = json.loads(log_line)
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "module" in parsed
        assert "message" in parsed

    def test_log_includes_session_id(self):
        from app.utils.logger import get_logger

        logger = get_logger("test_session")
        output = StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(logger.handlers[0].formatter)
        logger.handlers = [handler]

        logger.info("test", extra={"session_id": "sess-123"})
        log_line = output.getvalue()
        parsed = json.loads(log_line)
        assert parsed["session_id"] == "sess-123"

    def test_log_includes_agent_id(self):
        from app.utils.logger import get_logger

        logger = get_logger("test_agent")
        output = StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(logger.handlers[0].formatter)
        logger.handlers = [handler]

        logger.info("test", extra={"agent_id": "agent-456"})
        log_line = output.getvalue()
        parsed = json.loads(log_line)
        assert parsed["agent_id"] == "agent-456"

    def test_log_includes_operation(self):
        from app.utils.logger import get_logger

        logger = get_logger("test_operation")
        output = StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(logger.handlers[0].formatter)
        logger.handlers = [handler]

        logger.info("test", extra={"operation": "debate_start"})
        log_line = output.getvalue()
        parsed = json.loads(log_line)
        assert parsed["operation"] == "debate_start"


class TestLogLevelConfiguration:
    """Tests for log level configuration."""

    def test_default_log_level_is_debug(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        from app import config

        assert config.LOG_LEVEL == "DEBUG"

    def test_log_level_from_env_var(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        from importlib import reload
        import app.config as config_module

        reload(config_module)
        assert config_module.LOG_LEVEL == "INFO"

    def test_invalid_log_level_raises_error(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "INVALID")
        with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
            from importlib import reload
            import app.config as config_module

            reload(config_module)

    def test_logger_uses_configured_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        from importlib import reload
        import app.config as config_module

        reload(config_module)
        from app.utils import logger as logger_module

        reload(logger_module)

        test_logger = logger_module.get_logger("test_level")
        assert test_logger.level == logging.WARNING
