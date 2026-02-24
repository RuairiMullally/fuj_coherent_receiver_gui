"""Dash application factory."""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc

from .callbacks import register_all_callbacks
from .components.layout import build_layout


def create_dash_app(
    requests_pathname_prefix: str = "/dashboard/",
) -> dash.Dash:
    """Create and configure the Dash application.

    Args:
        requests_pathname_prefix: URL prefix for Dash routes.

    Returns:
        Configured Dash app with layout and callbacks registered.
    """
    app = dash.Dash(
        __name__,
        requests_pathname_prefix=requests_pathname_prefix,
        external_stylesheets=[dbc.themes.FLATLY],
        suppress_callback_exceptions=True,
        title="FIM24725 Control",
    )

    app.layout = build_layout()
    register_all_callbacks(app)

    return app
