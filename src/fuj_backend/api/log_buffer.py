"""In-memory log ring buffer for the /logs API endpoint.

Captures structured log records from the fim24725 logger hierarchy so the
Dash UI can poll recent log activity without reading log files directly.
"""

from __future__ import annotations

import datetime
import logging
from collections import deque
from dataclasses import dataclass


@dataclass
class LogLine:
    """Single structured log record."""

    timestamp: str  # ISO-8601: "YYYY-MM-DDTHH:MM:SS"
    level: str      # DEBUG / INFO / WARNING / ERROR / CRITICAL
    logger: str     # Logger name, e.g. "fim24725.service"
    message: str


class LogBufferHandler(logging.Handler):
    """logging.Handler that appends records to a bounded deque.

    Attach to the root 'fim24725' logger to capture all service and
    hardware log output in one place for the UI log panel.

    Usage:
        handler = LogBufferHandler(maxlen=500)
        handler.setLevel(logging.DEBUG)
        logging.getLogger("fim24725").addHandler(handler)
    """

    def __init__(self, maxlen: int = 500) -> None:
        super().__init__()
        self._buffer: deque[LogLine] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        ts = datetime.datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        self._buffer.append(
            LogLine(
                timestamp=ts,
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
            )
        )

    def recent(self, n: int) -> list[LogLine]:
        """Return up to the last n records (oldest-first)."""
        lines = list(self._buffer)
        return lines[-n:] if n < len(lines) else lines

    def __len__(self) -> int:
        return len(self._buffer)
