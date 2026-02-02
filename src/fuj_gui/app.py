"""Dash application factory."""

import dash
import dash_bootstrap_components as dbc
import logging

from .layout import get_layout
from .callbacks import register_callbacks
from .api_client import BackendAPIClient

logger = logging.getLogger(__name__)


def create_dash_app(base_url: str = "http://localhost:8000") -> dash.Dash:
    """Create and configure the Dash application.

    Args:
        base_url: Base URL for the backend API (default: http://localhost:8000)

    Returns:
        Configured Dash application instance
    """
    # Create Dash app with Bootstrap styling
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        url_base_pathname="/dashboard/",
        suppress_callback_exceptions=True,
        title="FUJ Coherent Receiver GUI"
    )

    # Set up the layout
    app.layout = get_layout()

    # Create API client
    api_client = BackendAPIClient(base_url=base_url)

    # Register callbacks
    register_callbacks(app, api_client)

    logger.info("Dash application created successfully")

    return app
