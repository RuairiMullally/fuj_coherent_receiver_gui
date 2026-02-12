"""Logging configuration for FIM24725 service layer.

Provides dedicated file logging with daily rotation, similar to the HAL logger.
Log file: logs/fim24725_service.log
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_service_logger: logging.Logger | None = None


def setup_service_logger() -> logging.Logger:
    """Configure dedicated service layer logger with daily rotation.

    Log file: logs/fim24725_service.log
    Rotation: Daily at midnight, 30-day retention

    Log format:
        2026-02-12 10:30:45.123 | fim24725.service | INFO | Message here

    Returns:
        Configured logger for 'fim24725' namespace
    """
    global _service_logger

    logger = logging.getLogger("fim24725")
    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.DEBUG)

    # Create logs directory if needed
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "fim24725_service.log"

    # File handler with daily rotation
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=30,  # Keep 30 days of logs
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    # Also log to console at INFO level for visibility
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logger.addHandler(console_handler)

    _service_logger = logger
    return logger


def get_service_logger() -> logging.Logger:
    """Get the configured service logger, initializing if needed.

    Returns:
        The 'fim24725' logger instance
    """
    global _service_logger
    if _service_logger is None:
        return setup_service_logger()
    return _service_logger
