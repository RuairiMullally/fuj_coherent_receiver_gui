"""FastAPI dependency injection for the FIM24725 API.

Thread safety note:
    FIM24725Service uses threading.RLock (@synchronized on all public methods).
    All route handlers in this API are sync `def` functions — FastAPI runs them
    in its default thread pool (anyio). Concurrent requests will block at the
    service lock, serialising hardware access automatically. No additional
    locking is required in the API layer.
"""

from __future__ import annotations

from fastapi import Request

from fuj_backend.api.log_buffer import LogBufferHandler
from fuj_backend.config import Settings
from fuj_backend.services.fim24725_service import FIM24725Service


def get_service(request: Request) -> FIM24725Service:
    """Return the application-lifetime FIM24725Service singleton."""
    return request.app.state.service


def get_settings(request: Request) -> Settings:
    """Return the application Settings instance."""
    return request.app.state.settings


def get_log_buffer(request: Request) -> LogBufferHandler:
    """Return the in-memory log buffer for the /logs endpoint."""
    return request.app.state.log_buffer
