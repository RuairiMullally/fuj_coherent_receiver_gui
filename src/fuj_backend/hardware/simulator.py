import logging
from typing import Dict
from .driver import HardwareDriver

logger = logging.getLogger(__name__)


class SimulatorDriver(HardwareDriver):
    """Simulated hardware driver for development and testing."""

    def __init__(self, num_channels: int = 8):
        self.num_channels = num_channels
        self._channels: Dict[int, float] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the simulator with default values."""
        logger.info("Initializing hardware simulator with %d channels", self.num_channels)
        self._channels = {i: 0.0 for i in range(1, self.num_channels + 1)}
        self._initialized = True
        logger.info("Hardware simulator initialized successfully")

    async def set_channel(self, channel_id: int, value: float) -> None:
        """Set a channel to a specific value in the simulator."""
        if not self._initialized:
            raise RuntimeError("Hardware not initialized")

        if channel_id not in self._channels:
            raise ValueError(f"Invalid channel ID: {channel_id}")

        old_value = self._channels[channel_id]
        self._channels[channel_id] = value
        logger.info(
            "Channel %d: %.3f -> %.3f (simulated)",
            channel_id,
            old_value,
            value
        )

    async def get_channel(self, channel_id: int) -> float:
        """Get the current value of a channel from the simulator."""
        if not self._initialized:
            raise RuntimeError("Hardware not initialized")

        if channel_id not in self._channels:
            raise ValueError(f"Invalid channel ID: {channel_id}")

        return self._channels[channel_id]

    async def get_all_channels(self) -> Dict[int, float]:
        """Get all channel values from the simulator."""
        if not self._initialized:
            raise RuntimeError("Hardware not initialized")

        return self._channels.copy()

    async def shutdown(self) -> None:
        """Shutdown the simulator."""
        logger.info("Shutting down hardware simulator")
        self._initialized = False
        self._channels.clear()
        logger.info("Hardware simulator shutdown complete")
