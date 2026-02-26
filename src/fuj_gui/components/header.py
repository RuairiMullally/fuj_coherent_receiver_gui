"""Header row component: state badge, mode toggle, startup/shutdown buttons.

Also places the startup modal, shutdown modal, and error toast in the layout.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

# State → badge colour
STATE_COLORS: dict[str, str] = {
    "OFF": "secondary",
    "STARTING": "info",
    "READY": "success",
    "SHUTTING_DOWN": "warning",
    "FAULT": "danger",
}


def build_header() -> html.Div:
    """Return the full header section (row + modals + toast)."""
    return html.Div(
        [
            _header_row(),
            _startup_modal(),
            _shutdown_modal(),
            _error_toast(),
        ]
    )


def _header_row() -> dbc.Row:
    return dbc.Row(
        [
            # State badge
            dbc.Col(
                dbc.Badge(
                    "OFF",
                    id="state-badge",
                    color="secondary",
                    className="fs-6 px-3 py-2",
                ),
                width="auto",
                className="d-flex align-items-center",
            ),
            # Mode toggle (AGC / MGC)
            dbc.Col(
                dbc.Switch(
                    id="mode-switch",
                    label="MGC",
                    value=False,
                    disabled=True,
                    className="ms-3",
                ),
                width="auto",
                className="d-flex align-items-center",
            ),
            # Spacer
            dbc.Col(width=True),
            # Startup button
            dbc.Col(
                dbc.Button(
                    "STARTUP",
                    id="startup-btn",
                    color="success",
                    disabled=False,
                    className="me-2",
                ),
                width="auto",
            ),
            # Shutdown button
            dbc.Col(
                dbc.Button(
                    "SHUTDOWN",
                    id="shutdown-btn",
                    color="danger",
                    disabled=True,
                ),
                width="auto",
            ),
        ],
        className="mb-3 align-items-center",
    )


def _startup_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Confirm Startup")),
            dbc.ModalBody(
                [
                    html.P("Select the initial operating mode:"),
                    dbc.RadioItems(
                        id="startup-modal-mode",
                        options=[
                            {"label": "AGC — Automatic Gain Control", "value": "AGC"},
                            {"label": "MGC — Manual Gain Control", "value": "MGC"},
                        ],
                        value="AGC",
                        inline=False,
                    ),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "Cancel",
                        id="startup-modal-cancel",
                        color="secondary",
                        className="me-2",
                    ),
                    dbc.Button(
                        "Confirm",
                        id="startup-modal-confirm",
                        color="success",
                    ),
                ]
            ),
        ],
        id="startup-modal",
        is_open=False,
        centered=True,
    )


def _shutdown_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Confirm Shutdown")),
            dbc.ModalBody(
                "This will disable all power rails and the module."
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "Cancel",
                        id="shutdown-modal-cancel",
                        color="secondary",
                        className="me-2",
                    ),
                    dbc.Button(
                        "Confirm",
                        id="shutdown-modal-confirm",
                        color="danger",
                    ),
                ]
            ),
        ],
        id="shutdown-modal",
        is_open=False,
        centered=True,
    )


def _error_toast() -> dbc.Toast:
    return dbc.Toast(
        id="error-toast",
        header="Error",
        is_open=False,
        dismissable=True,
        duration=5000,
        icon="danger",
        style={"position": "fixed", "top": 20, "right": 20, "zIndex": 9999},
        children=html.Div(id="error-toast-body"),
    )
