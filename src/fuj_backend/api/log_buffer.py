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

    seq: int        # Monotonic sequence number — used for delta polling
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
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        ts = datetime.datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        self._buffer.append(
            LogLine(
                seq=self._seq,
                timestamp=ts,
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
            )
        )
        self._seq += 1

    def recent(self, n: int) -> list[LogLine]:
        """Return up to the last n records (oldest-first)."""
        lines = list(self._buffer)
        return lines[-n:] if n < len(lines) else lines

    def since(self, seq: int) -> list[LogLine]:
        """Return all records with seq > given value (oldest-first)."""
        return [l for l in self._buffer if l.seq > seq]

    def max_seq(self) -> int:
        """Highest seq in the buffer, or -1 if empty."""
        return self._buffer[-1].seq if self._buffer else -1

    def __len__(self) -> int:
        return len(self._buffer)
