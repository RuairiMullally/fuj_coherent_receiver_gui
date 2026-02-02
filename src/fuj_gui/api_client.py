"""API client for communicating with the FastAPI backend."""

import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BackendAPIClient:
    """Synchronous HTTP client for backend API communication.

    Uses synchronous httpx.Client because Dash callbacks are synchronous.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the API client.

        Args:
            base_url: Base URL for the backend API (default: http://localhost:8000)
        """
        self.base_url = base_url.rstrip('/')
        self.client = httpx.Client(timeout=10.0)

    def get_all_channels(self) -> Dict[str, Any]:
        """Fetch all channel states from the backend.

        Returns:
            Dictionary with channel states or error information
        """
        try:
            response = self.client.get(f"{self.base_url}/api/channels")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get channels: {e}")
            return {"error": f"Failed to fetch channels: {str(e)}"}

    def get_channel(self, channel_id: int) -> Dict[str, Any]:
        """Fetch a single channel state from the backend.

        Args:
            channel_id: Channel ID (1-8)

        Returns:
            Dictionary with channel state or error information
        """
        try:
            response = self.client.get(f"{self.base_url}/api/channels/{channel_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get channel {channel_id}: {e}")
            return {"error": f"Failed to fetch channel {channel_id}: {str(e)}"}

    def update_channel(self, channel_id: int, value: float) -> Dict[str, Any]:
        """Update a channel value on the backend.

        Args:
            channel_id: Channel ID (1-8)
            value: Channel value (0.0-1.0)

        Returns:
            Dictionary with updated channel state or error information
        """
        try:
            response = self.client.put(
                f"{self.base_url}/api/channels/{channel_id}",
                json={"value": round(value, 3)}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"Rate limit exceeded for channel {channel_id}")
                return {"error": "Rate limit exceeded. Please slow down."}
            elif e.response.status_code == 400:
                logger.error(f"Validation error for channel {channel_id}: {e}")
                try:
                    error_detail = e.response.json().get("detail", str(e))
                except Exception:
                    error_detail = str(e)
                return {"error": f"Validation error: {error_detail}"}
            else:
                logger.error(f"HTTP error updating channel {channel_id}: {e}")
                return {"error": f"HTTP error: {e.response.status_code}"}
        except httpx.HTTPError as e:
            logger.error(f"Network error updating channel {channel_id}: {e}")
            return {"error": "Network error. Please try again."}

    def close(self):
        """Close the HTTP client and cleanup resources."""
        self.client.close()
