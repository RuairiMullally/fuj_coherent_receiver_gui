"""Global exception handlers for the FIM24725 REST API.

Maps service-layer exceptions to appropriate HTTP status codes and a
consistent JSON error body:
    {"detail": "<message>", "error_type": "<ClassName>"}
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from fuj_backend.services.exceptions import (
    BoundsError,
    FIM24725Error,
    MCUError,
    SequenceError,
    StateError,
    VerificationError,
)


def _error_body(exc: Exception) -> dict[str, str]:
    return {"detail": str(exc), "error_type": type(exc).__name__}


async def state_error_handler(request: Request, exc: StateError) -> JSONResponse:
    return JSONResponse(status_code=409, content=_error_body(exc))


async def bounds_error_handler(request: Request, exc: BoundsError) -> JSONResponse:
    return JSONResponse(status_code=422, content=_error_body(exc))


async def verification_error_handler(
    request: Request, exc: VerificationError
) -> JSONResponse:
    return JSONResponse(status_code=502, content=_error_body(exc))


async def mcu_error_handler(request: Request, exc: MCUError) -> JSONResponse:
    return JSONResponse(status_code=502, content=_error_body(exc))


async def sequence_error_handler(
    request: Request, exc: SequenceError
) -> JSONResponse:
    return JSONResponse(status_code=409, content=_error_body(exc))


async def fim24725_error_handler(
    request: Request, exc: FIM24725Error
) -> JSONResponse:
    """Fallback handler for any unhandled FIM24725Error subclass."""
    return JSONResponse(status_code=500, content=_error_body(exc))


def register_exception_handlers(app: object) -> None:
    """Register all service exception handlers on the FastAPI app."""
    app.add_exception_handler(StateError, state_error_handler)
    app.add_exception_handler(BoundsError, bounds_error_handler)
    app.add_exception_handler(VerificationError, verification_error_handler)
    app.add_exception_handler(MCUError, mcu_error_handler)
    app.add_exception_handler(SequenceError, sequence_error_handler)
    # FIM24725Error must be registered last — it is the base class
    app.add_exception_handler(FIM24725Error, fim24725_error_handler)
