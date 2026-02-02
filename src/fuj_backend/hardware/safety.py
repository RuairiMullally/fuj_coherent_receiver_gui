import logging
from datetime import datetime, timedelta
from typing import Dict, List
from collections import deque

logger = logging.getLogger(__name__)


class SafetyManager:
    """
    Manages safety constraints for hardware operations.

    - Enforces value limits
    - Rate limiting to prevent too-rapid changes
    - Logs all operations for audit trail
    """

    def __init__(
        self,
        min_value: float = 0.0,
        max_value: float = 1.0,
        max_rate_changes_per_second: int = 10
    ):
        self.min_value = min_value
        self.max_value = max_value
        self.max_rate = max_rate_changes_per_second

        # Track recent changes for rate limiting (channel_id -> deque of timestamps)
        self._change_history: Dict[int, deque] = {}

    def validate_value(self, value: float) -> None:
        """
        Validate that a value is within acceptable limits.

        Args:
            value: The value to validate

        Raises:
            ValueError: If value is out of bounds
        """
        if not (self.min_value <= value <= self.max_value):
            raise ValueError(
                f"Value {value} out of bounds [{self.min_value}, {self.max_value}]"
            )

    def check_rate_limit(self, channel_id: int) -> bool:
        """
        Check if a channel change would exceed the rate limit.

        Args:
            channel_id: The channel to check

        Returns:
            True if the change is allowed, False if rate limited
        """
        now = datetime.now()

        # Initialize history for this channel if needed
        if channel_id not in self._change_history:
            self._change_history[channel_id] = deque()

        history = self._change_history[channel_id]

        # Remove changes older than 1 second
        cutoff = now - timedelta(seconds=1)
        while history and history[0] < cutoff:
            history.popleft()

        # Check if we're at the limit
        if len(history) >= self.max_rate:
            logger.warning(
                "Rate limit exceeded for channel %d (%d changes in last second)",
                channel_id,
                len(history)
            )
            return False

        # Record this change
        history.append(now)
        return True

    def log_change(self, channel_id: int, old_value: float, new_value: float) -> None:
        """
        Log a channel change for audit trail.

        Args:
            channel_id: The channel that changed
            old_value: Previous value
            new_value: New value
        """
        logger.info(
            "AUDIT: Channel %d changed from %.3f to %.3f",
            channel_id,
            old_value,
            new_value
        )
