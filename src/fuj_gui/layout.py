"""Dash UI layout components."""

import dash_bootstrap_components as dbc
from dash import html, dcc

from .styles import (
    SLIDER_STYLE,
    VALUE_DISPLAY_STYLE,
    CHANNEL_LABEL_STYLE,
    HEADER_STYLE,
    CONTAINER_STYLE,
)


def create_channel_control(channel_id: int):
    """Create a single channel control row (label + slider + value display).

    Args:
        channel_id: Channel ID (1-8)

    Returns:
        Dash Bootstrap Row component with label, slider, and value display
    """
    return dbc.Row(
        [
            dbc.Col(
                html.Label(
                    f"Channel {channel_id}",
                    style=CHANNEL_LABEL_STYLE
                ),
                width=2
            ),
            dbc.Col(
                dcc.Slider(
                    id={"type": "channel-slider", "index": channel_id},
                    min=0,
                    max=1000,
                    step=1,
                    value=0,
                    marks={
                        0: "0.000",
                        250: "0.250",
                        500: "0.500",
                        750: "0.750",
                        1000: "1.000"
                    },
                    tooltip={
                        "placement": "bottom",
                        "always_visible": False
                    },
                    updatemode="drag",
                ),
                width=8,
                style=SLIDER_STYLE
            ),
            dbc.Col(
                html.Div(
                    "0.000",
                    id={"type": "value-display", "index": channel_id},
                    style=VALUE_DISPLAY_STYLE
                ),
                width=2
            )
        ],
        className="mb-3 align-items-center"
    )


def get_layout():
    """Create the main Dash layout.

    Returns:
        Dash Bootstrap Container with all UI components
    """
    return dbc.Container(
        [
            # Header
            dbc.Row(
                dbc.Col(
                    html.H1(
                        "FUJ Coherent Receiver GUI",
                        style=HEADER_STYLE
                    )
                )
            ),

            # Alert for errors/status messages
            dbc.Row(
                dbc.Col(
                    dbc.Alert(
                        "",
                        id="alert-message",
                        is_open=False,
                        duration=5000,
                        dismissable=True,
                        color="danger"
                    )
                )
            ),

            # 8 Channel controls
            *[create_channel_control(i) for i in range(1, 9)],

            # Hidden store for state persistence (future use)
            dcc.Store(id="channel-store")
        ],
        fluid=False,
        style=CONTAINER_STYLE
    )
