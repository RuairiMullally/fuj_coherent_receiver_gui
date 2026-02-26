"""FastAPI application factory for the FIM24725 coherent receiver API.

Entry point:
    uvicorn fuj_backend.api.app:create_app --factory --host 0.0.0.0 --port 8000

Configuration:
    All settings are loaded from environment variables (prefix FUJ_) or a .env
    file. Key options:
        FUJ_MCU_MODE=mock|real   (default: mock)
        FUJ_PSU1_IP=<ip>
        FUJ_PSU2_IP=<ip>
    See fuj_backend.config.Settings for the full list.

Thread safety:
    FIM24725Service uses threading.RLock (@synchronized on all public methods).
    All route handlers are sync `def` — FastAPI runs them in its default thread
    pool (anyio). Concurrent requests will block at the service lock, serialising
    hardware access automatically. No additional locking is required in the API.

Lifecycle:
    startup  — service is instantiated but startup() is NOT called.
               The device starts in OFF state; the user triggers startup via
               POST /api/v1/startup from the UI.
    shutdown — service.close() and MCU cleanup are called automatically.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from fuj_backend.api.exceptions import register_exception_handlers
from fuj_backend.api.limiter import limiter
from fuj_backend.api.log_buffer import LogBufferHandler
from fuj_backend.api.routes.controls import router as controls_router
from fuj_backend.api.routes.logs import router as logs_router
from fuj_backend.api.routes.service import router as service_router
from fuj_backend.api.routes.telemetry import router as telemetry_router
from fuj_backend.config import Settings
from fuj_backend.services.fim24725_service import FIM24725Service
from fuj_backend.services.logging import setup_service_logger
from fuj_backend.services.mcu_interface import MockMCU


def _setup_api_logger(log_dir: str, level: str) -> logging.Logger:
    """Configure the fim24725.api logger with daily-rotating file output."""
    logger = logging.getLogger("fim24725.api")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    fh = TimedRotatingFileHandler(
        log_path / "api.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(fh)
    return logger


def _make_mcu(settings: Settings) -> object:
    """Instantiate the correct MCU implementation based on settings."""
    if settings.mcu_mode == "real":
        from fuj_backend.hardware.arduino_mcu import ArduinoMCU
        return ArduinoMCU(settings.mcu_port)
    return MockMCU()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = Settings()

    # --- Logging setup ---
    root_logger = setup_service_logger()
    # Apply the configured level to file/console handlers so they only emit
    # records at that level and above. The root logger itself must stay at
    # DEBUG so that the log buffer (added below) can capture everything.
    configured_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    for h in root_logger.handlers:
        h.setLevel(configured_level)
    root_logger.setLevel(logging.DEBUG)

    api_logger = _setup_api_logger(settings.log_dir, settings.log_level)

    log_buffer = LogBufferHandler(maxlen=500)
    log_buffer.setLevel(logging.DEBUG)
    root_logger.addHandler(log_buffer)

    api_logger.info(
        f"Starting FIM24725 API — mcu_mode={settings.mcu_mode} "
        f"psu1={settings.psu1_ip} psu2={settings.psu2_ip}"
    )

    # --- MCU ---
    mcu = _make_mcu(settings)
    mcu_is_context_manager = hasattr(mcu, "__enter__")
    if mcu_is_context_manager:
        mcu.__enter__()

    # --- Service (not started — user triggers startup via API) ---
    service = FIM24725Service(
        psu1_ip=settings.psu1_ip,
        psu1_port=settings.psu1_port,
        psu1_local_ip=settings.psu1_local_ip,
        psu2_ip=settings.psu2_ip,
        psu2_port=settings.psu2_port,
        psu2_local_ip=settings.psu2_local_ip,
        mcu=mcu,
    )

    app.state.service = service
    app.state.settings = settings
    app.state.log_buffer = log_buffer
    app.state.limiter = limiter

    api_logger.info("Service instantiated (state=OFF). Ready to accept requests.")

    try:
        yield
    finally:
        api_logger.info("Shutting down — closing service and MCU")
        service.close()
        if mcu_is_context_manager:
            mcu.__exit__(None, None, None)
        api_logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Used as an application factory:
        uvicorn fuj_backend.api.app:create_app --factory
    """
    app = FastAPI(
        title="FIM24725 Coherent Receiver API",
        description=(
            "REST API for controlling the FIM24725 coherent receiver module. "
            "Exposes PSU rail control, MCU digital signals, and telemetry."
        ),
        version="1.0.0",
        lifespan=_lifespan,
    )

    # --- Rate limiting ---
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # --- CORS (local UI only) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1",
                        "http://localhost:8050", "http://127.0.0.1:8050"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # --- Trusted hosts (local deploy) ---
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0", "*"],
    )

    # --- Service exception handlers ---
    register_exception_handlers(app)

    # --- Routers ---
    app.include_router(service_router,   prefix="/api/v1",           tags=["service"])
    app.include_router(controls_router,  prefix="/api/v1/controls",  tags=["controls"])
    app.include_router(telemetry_router, prefix="/api/v1/telemetry", tags=["telemetry"])
    app.include_router(logs_router,      prefix="/api/v1",           tags=["logs"])

    return app
