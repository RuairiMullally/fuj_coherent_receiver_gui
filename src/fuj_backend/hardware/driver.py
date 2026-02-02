from abc import ABC, abstractmethod
from typing import Dict


class HardwareDriver(ABC):
    """Abstract base class for hardware drivers."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize hardware connection."""
        pass

    @abstractmethod
    async def set_channel(self, channel_id: int, value: float) -> None:
        """
        Set a channel to a specific value.

        Args:
            channel_id: Channel ID (1-8)
            value: Value to set (0.0-1.0)
        """
        pass

    @abstractmethod
    async def get_channel(self, channel_id: int) -> float:
        """
        Get the current value of a channel.

        Args:
            channel_id: Channel ID (1-8)

        Returns:
            Current channel value (0.0-1.0)
        """
        pass

    @abstractmethod
    async def get_all_channels(self) -> Dict[int, float]:
        """
        Get all channel values.

        Returns:
            Dictionary mapping channel IDs to their values
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Safely shutdown hardware connection."""
        pass
