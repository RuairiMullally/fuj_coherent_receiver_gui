"""Dashboard layout for FIM24725 coherent receiver control."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def _make_voltage_control(
    label: str,
    input_id: str,
    btn_id: str,
    min_val: float,
    max_val: float,
    disabled: bool = False,
) -> dbc.Row:
    """Create a voltage control row with label, input, and set button."""
    return dbc.Row(
        [
            dbc.Col(
                dbc.Label(f"{label} ({min_val} \u2013 {max_val}V)"),
                width=5,
                className="align-self-center",
            ),
            dbc.Col(
                dbc.InputGroup(
                    [
                        dbc.Input(
                            id=input_id,
                            type="number",
                            min=min_val,
                            max=max_val,
                            step=0.001,
                            placeholder=str(min_val),
                            disabled=disabled,
                        ),
                        dbc.InputGroupText("V"),
                        dbc.Button(
                            "Set",
                            id=btn_id,
                            color="primary",
                            size="sm",
                            disabled=disabled,
                        ),
                    ],
                    size="sm",
                ),
                width=7,
            ),
        ],
        className="mb-2",
    )


def _lifecycle_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6("Lifecycle", className="card-title"),
                dbc.ButtonGroup(
                    [
                        dbc.Button(
                            "Startup",
                            id="startup-btn",
                            color="success",
                            className="me-1",
                        ),
                        dbc.Button(
                            "Shutdown",
                            id="shutdown-btn",
                            color="danger",
                        ),
                    ]
                ),
            ]
        ),
        className="mb-3",
    )


def _mode_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6("Mode", className="card-title"),
                dbc.RadioItems(
                    id="mode-toggle",
                    options=[
                        {"label": "AGC (Automatic)", "value": "AGC"},
                        {"label": "MGC (Manual)", "value": "MGC"},
                    ],
                    value="AGC",
                    inline=True,
                ),
            ]
        ),
        className="mb-3",
    )


def _voa_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6("Variable Optical Attenuator", className="card-title"),
                _make_voltage_control("VOA", "voa-input", "voa-set-btn", 0.0, 4.8),
            ]
        ),
        className="mb-3",
    )


def _oa_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6("Output Amplitude", className="card-title"),
                _make_voltage_control(
                    "OA_X", "oa-x-input", "oa-x-set-btn", 0.0, 3.3
                ),
                _make_voltage_control(
                    "OA_Y", "oa-y-input", "oa-y-set-btn", 0.0, 3.3
                ),
            ]
        ),
        className="mb-3",
    )


def _ga_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6("Gain Adjust (MGC Only)", className="card-title"),
                _make_voltage_control(
                    "GA_X",
                    "ga-x-input",
                    "ga-x-set-btn",
                    0.0,
                    3.3,
                    disabled=True,
                ),
                _make_voltage_control(
                    "GA_Y",
                    "ga-y-input",
                    "ga-y-set-btn",
                    0.0,
                    3.3,
                    disabled=True,
                ),
            ]
        ),
        className="mb-3",
    )


def _pi_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6("Peak Indicators", className="card-title"),
                dcc.Graph(
                    id="pi-graph",
                    config={"displayModeBar": False},
                    style={"height": "300px"},
                ),
            ]
        ),
        className="mb-3",
    )


def _mpd_card() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.H6("Monitor Photodiode", className="card-title"),
                dcc.Graph(
                    id="mpd-graph",
                    config={"displayModeBar": False},
                    style={"height": "250px"},
                ),
            ]
        ),
        className="mb-3",
    )


def build_layout() -> dbc.Container:
    """Build the complete dashboard layout."""
    return dbc.Container(
        [
            # Hidden stores and interval timer
            dcc.Interval(id="poll-interval", interval=1500, n_intervals=0),
            dcc.Store(
                id="pi-history",
                data={
                    "timestamps": [],
                    "pi_xi": [],
                    "pi_xq": [],
                    "pi_yi": [],
                    "pi_yq": [],
                },
            ),
            dcc.Store(id="mpd-history", data={"timestamps": [], "values": []}),
            dcc.Store(id="system-state", data={"state": "OFF", "mode": "AGC"}),
            # Header
            dbc.Row(
                [
                    dbc.Col(html.H2("FIM24725 Coherent Receiver"), width=8),
                    dbc.Col(
                        [
                            dbc.Badge(
                                "OFF",
                                id="state-badge",
                                color="secondary",
                                className="me-2 fs-6",
                            ),
                            dbc.Badge(
                                "AGC",
                                id="mode-badge",
                                color="info",
                                className="fs-6",
                            ),
                        ],
                        width=4,
                        className="text-end align-self-center",
                    ),
                ],
                className="my-3",
            ),
            # Alert area
            dbc.Alert(
                id="alert-message",
                is_open=False,
                dismissable=True,
                duration=5000,
            ),
            # Main content
            dbc.Row(
                [
                    # Left column: Controls
                    dbc.Col(
                        [
                            _lifecycle_card(),
                            _mode_card(),
                            _voa_card(),
                            _oa_card(),
                            _ga_card(),
                        ],
                        md=4,
                    ),
                    # Right column: Monitoring
                    dbc.Col(
                        [
                            _pi_card(),
                            _mpd_card(),
                        ],
                        md=8,
                    ),
                ]
            ),
        ],
        fluid=True,
    )
