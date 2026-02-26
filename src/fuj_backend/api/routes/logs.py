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
@limiter.limit("30/minute")
def get_logs(
    request: Request,
    n: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Number of recent log lines to return (max 500)",
    ),
    log_buffer: LogBufferHandler = Depends(get_log_buffer),
) -> LogsResponse:
    """Return the last n structured log lines from service and hardware loggers."""
    return LogsResponse(
        lines=log_buffer.recent(n),
        total_buffered=len(log_buffer),
    )
