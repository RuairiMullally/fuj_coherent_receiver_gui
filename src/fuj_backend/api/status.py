from fastapi import APIRouter, Depends
from typing import Annotated
from datetime import datetime

from ..config import settings
from ..hardware import HardwareDriver
from ..dependencies import get_hardware

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/health")
async def health_check(
    hardware: Annotated[HardwareDriver, Depends(get_hardware)]
) -> dict:
    """
    Health check endpoint.

    Returns:
        Status information about the service
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.version,
        "hardware_mode": settings.hardware_mode,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/info")
async def get_info() -> dict:
    """
    Get service information.

    Returns:
        Service configuration and capabilities
    """
    return {
        "service": settings.app_name,
        "version": settings.version,
        "hardware_mode": settings.hardware_mode,
        "num_channels": settings.num_channels,
        "channel_limits": {
            "min": settings.channel_min_value,
            "max": settings.channel_max_value
        },
        "rate_limit": settings.max_rate_changes_per_second
    }
