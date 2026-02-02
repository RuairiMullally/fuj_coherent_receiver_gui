import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from typing import Annotated

from ..models import Channel, ChannelState, ChannelUpdate
from ..hardware import HardwareDriver, SafetyManager
from ..dependencies import get_hardware, get_safety_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("", response_model=ChannelState)
async def get_all_channels(
    hardware: Annotated[HardwareDriver, Depends(get_hardware)]
) -> ChannelState:
    """
    Get the current state of all channels.

    Returns:
        ChannelState containing all channel values and timestamp
    """
    try:
        channel_values = await hardware.get_all_channels()

        channels = [
            Channel(
                id=channel_id,
                value=value,
                last_updated=datetime.now()
            )
            for channel_id, value in channel_values.items()
        ]

        return ChannelState(channels=channels, timestamp=datetime.now())

    except Exception as e:
        logger.error("Failed to get channels: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{channel_id}", response_model=Channel)
async def get_channel(
    channel_id: int,
    hardware: Annotated[HardwareDriver, Depends(get_hardware)]
) -> Channel:
    """
    Get the current state of a specific channel.

    Args:
        channel_id: Channel ID (1-8)

    Returns:
        Channel state
    """
    if not 1 <= channel_id <= 8:
        raise HTTPException(status_code=400, detail="Channel ID must be between 1 and 8")

    try:
        value = await hardware.get_channel(channel_id)
        return Channel(
            id=channel_id,
            value=value,
            last_updated=datetime.now()
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to get channel %d: %s", channel_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{channel_id}", response_model=Channel)
async def update_channel(
    channel_id: int,
    update: ChannelUpdate,
    hardware: Annotated[HardwareDriver, Depends(get_hardware)],
    safety: Annotated[SafetyManager, Depends(get_safety_manager)]
) -> Channel:
    """
    Update a channel value with safety validation.

    Args:
        channel_id: Channel ID (1-8)
        update: New channel value

    Returns:
        Updated channel state
    """
    if not 1 <= channel_id <= 8:
        raise HTTPException(status_code=400, detail="Channel ID must be between 1 and 8")

    try:
        # Safety validation
        safety.validate_value(update.value)

        # Rate limit check
        if not safety.check_rate_limit(channel_id):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Too many changes too quickly."
            )

        # Get old value for logging
        old_value = await hardware.get_channel(channel_id)

        # Set new value
        await hardware.set_channel(channel_id, update.value)

        # Audit log
        safety.log_change(channel_id, old_value, update.value)

        return Channel(
            id=channel_id,
            value=update.value,
            last_updated=datetime.now()
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update channel %d: %s", channel_id, e)
        raise HTTPException(status_code=500, detail=str(e))
