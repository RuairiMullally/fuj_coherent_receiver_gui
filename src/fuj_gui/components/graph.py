"""PI / MPD rolling graph component."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc

# Trace colours
TRACE_COLORS = {
    "pi_xi": "#00b4d8",
    "pi_xq": "#90e0ef",
    "pi_yi": "#f77f00",
    "pi_yq": "#fcbf49",
    "mpd":   "#a8dadc",
}

_BG = "#1e1e2e"


def build_graph_panel() -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            dcc.Graph(
                id="pi-mpd-graph",
                style={"height": "400px"},
                config={"displayModeBar": False},
            )
        ),
        className="h-100",
    )


def empty_figure() -> dict:
    """Return a dark empty figure used as the initial graph state."""
    traces = [
        {
            "x": [],
            "y": [],
            "name": name.upper(),
            "type": "scatter",
            "mode": "lines",
            "line": {"color": color, "width": 1.5},
        }
        for name, color in TRACE_COLORS.items()
    ]
    return {
        "data": traces,
        "layout": {
            "title": {"text": "Peak Indicators & MPD", "font": {"color": "#cdd6f4"}},
            "paper_bgcolor": _BG,
            "plot_bgcolor": _BG,
            "font": {"color": "#cdd6f4"},
            "xaxis": {
                "title": "Time",
                "gridcolor": "#313244",
                "tickfont": {"color": "#cdd6f4"},
            },
            "yaxis": {
                "title": "Voltage (V)",
                "range": [0, 2.2],
                "gridcolor": "#313244",
                "tickfont": {"color": "#cdd6f4"},
            },
            "legend": {"font": {"color": "#cdd6f4"}},
            "margin": {"l": 50, "r": 20, "t": 40, "b": 50},
            "uirevision": "constant",
        },
    }
