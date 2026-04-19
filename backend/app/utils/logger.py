"""Structured logging utilities for DebatePanel backend."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import LOG_LEVEL


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs logs in JSON format."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
        }

        # Add optional context fields if present
        if hasattr(record, "session_id") and record.session_id:
            log_data["session_id"] = record.session_id
        if hasattr(record, "agent_id") and record.agent_id:
            log_data["agent_id"] = record.agent_id
        if hasattr(record, "operation") and record.operation:
            log_data["operation"] = record.operation

        log_data["message"] = record.getMessage()

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def get_logger(module_name: str) -> logging.Logger:
    """Create and configure a logger with structured JSON output.

    Args:
        module_name: Name of the module (typically __name__)

    Returns:
        Configured Logger instance with JSON formatting
    """
    logger = logging.getLogger(module_name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, LOG_LEVEL))
        logger.propagate = False

    return logger


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    operation: Optional[str] = None,
    **extra: Any,
) -> None:
    """Log a message with additional context fields.

    Args:
        logger: Logger instance to use
        level: Logging level (e.g., logging.INFO)
        message: Log message
        session_id: Optional session identifier
        agent_id: Optional agent identifier
        operation: Optional operation name
        **extra: Additional context fields
    """
    extra_fields: dict[str, Any] = {}
    if session_id:
        extra_fields["session_id"] = session_id
    if agent_id:
        extra_fields["agent_id"] = agent_id
    if operation:
        extra_fields["operation"] = operation
    extra_fields.update(extra)

    logger.log(level, message, extra=extra_fields)
