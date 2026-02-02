import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.wsgi import WSGIMiddleware

from .config import settings
from .hardware import SimulatorDriver, SafetyManager
from .dependencies import set_hardware, set_safety_manager
from .api import channels_router, status_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager - handles startup and shutdown.
    """
    # Startup
    logger.info("Starting %s v%s", settings.app_name, settings.version)
    logger.info("Hardware mode: %s", settings.hardware_mode)

    # Initialize hardware
    if settings.hardware_mode == "simulator":
        hardware = SimulatorDriver(num_channels=settings.num_channels)
    else:
        # TODO: Initialize real hardware driver when implemented
        raise NotImplementedError("Real hardware mode not yet implemented")

    await hardware.initialize()
    set_hardware(hardware)

    # Initialize safety manager
    safety = SafetyManager(
        min_value=settings.channel_min_value,
        max_value=settings.channel_max_value,
        max_rate_changes_per_second=settings.max_rate_changes_per_second
    )
    set_safety_manager(safety)

    logger.info("Backend initialization complete")

    yield

    # Shutdown
    logger.info("Shutting down backend")
    await hardware.shutdown()
    logger.info("Backend shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Backend API for controlling coherent receiver hardware",
    lifespan=lifespan
)

# CORS middleware for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Dash GUI
try:
    from fuj_gui import create_dash_app
    dash_app = create_dash_app()
    app.mount("/dashboard", WSGIMiddleware(dash_app.server))
    logger.info("Dash GUI mounted at /dashboard")
except ImportError as e:
    logger.warning(f"fuj_gui module not found. GUI disabled. Error: {e}")

# Register routers
app.include_router(status_router)
app.include_router(channels_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "fuj_backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
