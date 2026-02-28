"""Log retrieval route: /logs.

Returns recent structured log lines from the in-memory ring buffer.
The Dash UI polls this endpoint to populate the debug log panel.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from fuj_backend.api.deps import get_log_buffer
from fuj_backend.api.limiter import limiter
from fuj_backend.api.log_buffer import LogBufferHandler
from fuj_backend.api.models import LogsResponse

router = APIRouter()


@router.get("/logs", response_model=LogsResponse)
@limiter.limit("60/minute")
def get_logs(
    request: Request,
    n: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Number of recent log lines to return (max 500)",
    ),
    since_seq: int = Query(
        default=-1,
        ge=-1,
        description="Return only lines with seq > this value; -1 returns the last n lines",
    ),
    log_buffer: LogBufferHandler = Depends(get_log_buffer),
) -> LogsResponse:
    """Return structured log lines from the in-memory ring buffer.

    Pass since_seq from the previous response to receive only new lines (delta
    polling). Omit or pass -1 to get the last n lines (initial load).
    """
    lines = log_buffer.since(since_seq) if since_seq >= 0 else log_buffer.recent(n)
    return LogsResponse(
        lines=lines,
        total_buffered=len(log_buffer),
        max_seq=log_buffer.max_seq(),
    )
