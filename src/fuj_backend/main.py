"""Application entry point — FastAPI + Dash on a single port.

Run with:
    python -m uvicorn fuj_backend.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.wsgi import WSGIMiddleware

from .api import router as api_router
from .config import Settings
from .dependencies import clear_service, set_service
from .services import FIM24725Service, MockMCU

logger = logging.getLogger(__name__)


def _create_service(settings: Settings) -> FIM24725Service:
    """Build FIM24725Service from application settings."""
    mcu = MockMCU() if settings.hardware_mode == "simulator" else None
    return FIM24725Service(
        psu1_ip=settings.psu1_ip,
        psu1_port=settings.psu1_port,
        psu2_ip=settings.psu2_ip,
        psu2_port=settings.psu2_port,
        psu1_local_ip=settings.psu1_local_ip,
        psu2_local_ip=settings.psu2_local_ip,
        mcu=mcu,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the FIM24725Service lifecycle."""
    settings = Settings()
    service = _create_service(settings)
    app.state.service = service
    app.state.settings = settings
    set_service(service)
    logger.info("FIM24725 service ready (mode=%s)", settings.hardware_mode)
    yield
    service.close()
    clear_service()
    logger.info("FIM24725 service closed")


# --- Build the ASGI application ---

app = FastAPI(
    title="FIM24725 Coherent Receiver Control",
    version="0.1.0",
    lifespan=lifespan,
)

# REST API at /api/*
app.include_router(api_router, prefix="/api")

# Dash GUI at /dashboard/* (WSGI mounted on ASGI)
from fuj_gui import create_dash_app  # noqa: E402

_dash_app = create_dash_app(requests_pathname_prefix="/dashboard/")
app.mount("/dashboard", WSGIMiddleware(_dash_app.server))
