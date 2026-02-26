"""Scrollable log panel component."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

_LEVEL_STYLES: dict[str, dict] = {
    "DEBUG":    {"color": "#6c757d"},
    "INFO":     {"color": "#ffffff"},
    "WARNING":  {"color": "#ffc107"},
    "ERROR":    {"color": "#dc3545"},
    "CRITICAL": {"color": "#dc3545", "fontWeight": "bold"},
}


def build_logs_panel() -> dbc.Card:
    return dbc.Card(
        [
            dbc.CardHeader(
                dbc.Row(
                    [
                        dbc.Col("Logs", width="auto", className="fw-bold"),
                        dbc.Col(
                            dbc.Switch(
                                id="log-debug-toggle",
                                label="Debug",
                                value=False,
                                style={"marginBottom": "0"},
                            ),
                            className="d-flex align-items-center justify-content-end",
                        ),
                    ],
                    align="center",
                    justify="between",
                    className="g-0",
                ),
            ),
            dbc.CardBody(
                html.Div(
                    id="log-panel",
                    style={
                        "height": "20vh",
                        "minHeight": "150px",
                        "overflowY": "scroll",
                        "fontFamily": "monospace",
                        "fontSize": "0.8rem",
                        "backgroundColor": "#1e1e2e",
                        "padding": "8px",
                    },
                    children=[html.Div(id="log-bottom", style={"height": "0"})],
                ),
                style={"padding": "0"},
            ),
        ]
    )


def format_log_line(entry: dict) -> html.Div:
    """Convert a log entry dict to a colour-coded Div element."""
    level = entry.get("level", "INFO")
    style = _LEVEL_STYLES.get(level, _LEVEL_STYLES["INFO"])
    logger = entry.get("logger", "")
    message = entry.get("message", "")
    timestamp = entry.get("timestamp", "")

    text = f"[{level:<8}] {logger} — {message}"
    return html.Div(
        text,
        style=style,
        title=timestamp,
    )
