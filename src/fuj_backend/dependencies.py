"""Service singleton holder for cross-module access.

Both FastAPI routes and Dash callbacks need the FIM24725Service instance.
This module provides a simple holder that avoids circular imports and
global mutable state at module level.

The lifespan context manager in main.py calls set_service() on startup
and clear_service() on shutdown.
"""

from __future__ import annotations

from typing import Optional

from .services import FIM24725Service

_service: Optional[FIM24725Service] = None


def get_service() -> FIM24725Service:
    """Get the active FIM24725Service instance.

    Raises:
        RuntimeError: If the service has not been initialized yet.
    """
    if _service is None:
        raise RuntimeError("Service not initialized")
    return _service


def set_service(service: FIM24725Service) -> None:
    """Store the service instance (called during app startup)."""
    global _service
    _service = service


def clear_service() -> None:
    """Clear the service reference (called during app shutdown)."""
    global _service
    _service = None
