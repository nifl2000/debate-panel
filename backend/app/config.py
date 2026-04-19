"""Application configuration module.

Provides centralized configuration management for the DebatePanel backend.
"""

import os
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Log level configuration - defaults to DEBUG
LOG_LEVEL: LogLevel = os.environ.get("LOG_LEVEL", "DEBUG").upper()

# Validate LOG_LEVEL
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
if LOG_LEVEL not in VALID_LOG_LEVELS:
    raise ValueError(
        f"Invalid LOG_LEVEL '{LOG_LEVEL}'. Must be one of: {VALID_LOG_LEVELS}"
    )
