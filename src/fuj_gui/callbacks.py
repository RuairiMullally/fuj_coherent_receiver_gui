"""Dash callbacks for UI interactivity."""

import logging
from dash import Input, Output, State, MATCH, ALL, callback_context
from dash.exceptions import PreventUpdate

from .api_client import BackendAPIClient

logger = logging.getLogger(__name__)


def register_callbacks(app, api_client: BackendAPIClient):
    """Register all Dash callbacks.

    Args:
        app: Dash application instance
        api_client: Backend API client instance
    """

    @app.callback(
        Output({"type": "value-display", "index": MATCH}, "children"),
        Output("alert-message", "children"),
        Output("alert-message", "is_open"),
        Output("alert-message", "color"),
        Input({"type": "channel-slider", "index": MATCH}, "value"),
        State({"type": "channel-slider", "index": MATCH}, "id"),
        prevent_initial_call=True
    )
    def update_channel(slider_value, slider_id):
        """Handle slider value changes.

        Args:
            slider_value: Raw slider value (0-1000)
            slider_id: Slider component ID dictionary

        Returns:
            Tuple of (value_display_text, alert_message, alert_visible, alert_color)
        """
        if slider_value is None:
            raise PreventUpdate

        channel_id = slider_id["index"]
        value = slider_value / 1000.0

        # Update backend via API
        result = api_client.update_channel(channel_id, value)

        if "error" in result:
            # Error occurred - show alert
            logger.warning(f"Channel {channel_id} update failed: {result['error']}")
            return (
                f"{value:.3f}",  # Still update display
                result["error"],  # Error message
                True,  # Show alert
                "danger"  # Red alert
            )

        # Success
        logger.info(f"Slider {channel_id} updated → {value:.3f}")
        return (
            f"{value:.3f}",  # Update value display
            "",  # No alert message
            False,  # Hide alert
            "success"  # Green (though hidden)
        )

    @app.callback(
        [Output({"type": "channel-slider", "index": ALL}, "value"),
         Output({"type": "value-display", "index": ALL}, "children")],
        Input("channel-store", "data"),
        prevent_initial_call=False
    )
    def initialize_channels(store_data):
        """Initialize channel sliders on page load.

        Fetches current channel states from backend and updates all sliders.

        Args:
            store_data: Data from dcc.Store (unused, just triggers callback)

        Returns:
            Tuple of (slider_values_list, value_display_list)
        """
        # Fetch all channels from backend
        result = api_client.get_all_channels()

        if "error" in result:
            logger.error(f"Failed to initialize channels: {result['error']}")
            # Return defaults (all zeros)
            return [0] * 8, ["0.000"] * 8

        # Extract channel values from response
        try:
            channels = result.get("channels", [])
            slider_values = []
            display_values = []

            for i in range(1, 9):
                # Find channel in response
                channel_data = next((ch for ch in channels if ch["id"] == i), None)
                if channel_data:
                    value = channel_data.get("value", 0.0)
                else:
                    value = 0.0

                slider_values.append(int(value * 1000))
                display_values.append(f"{value:.3f}")

            logger.info("Channels initialized from backend")
            return slider_values, display_values

        except Exception as e:
            logger.error(f"Error parsing channel data: {e}")
            return [0] * 8, ["0.000"] * 8
