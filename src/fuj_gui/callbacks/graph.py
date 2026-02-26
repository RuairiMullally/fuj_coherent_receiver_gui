"""Rolling PI / MPD graph callbacks.

graph-store format:
    {
        "t":      ["2026-02-25T14:32:01", ...],
        "pi_xi":  [0.512, ...],
        "pi_xq":  [0.480, ...],
        "pi_yi":  [0.523, ...],
        "pi_yq":  [0.491, ...],
        "mpd":    [0.823, ...],
    }
"""

from __future__ import annotations

import datetime

from dash import Input, Output, State
from dash.exceptions import PreventUpdate

from fuj_gui.components.graph import TRACE_COLORS, empty_figure, _BG


def register(app, settings) -> None:
    _register_store_update(app, settings)
    _register_graph_render(app)


def _register_store_update(app, settings) -> None:
    max_points = settings.graph_history_s * (1000 // settings.poll_interval_ms)

    @app.callback(
        Output("graph-store", "data"),
        Input("status-store", "data"),
        State("graph-store", "data"),
    )
    def update_graph_store(status_data, graph_data):
        if not status_data:
            raise PreventUpdate

        pi = status_data.get("peak_indicators") or {}
        mpd_value = status_data.get("mpd_value")

        # Only append when we have real telemetry
        if not pi and mpd_value is None:
            raise PreventUpdate

        if graph_data is None:
            graph_data = {"t": [], "pi_xi": [], "pi_xq": [], "pi_yi": [], "pi_yq": [], "mpd": []}

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        graph_data["t"].append(ts)
        graph_data["pi_xi"].append(pi.get("pi_xi"))
        graph_data["pi_xq"].append(pi.get("pi_xq"))
        graph_data["pi_yi"].append(pi.get("pi_yi"))
        graph_data["pi_yq"].append(pi.get("pi_yq"))
        graph_data["mpd"].append(mpd_value)

        # Trim to rolling window
        if len(graph_data["t"]) > max_points:
            trim = len(graph_data["t"]) - max_points
            for key in graph_data:
                graph_data[key] = graph_data[key][trim:]

        return graph_data


def _register_graph_render(app) -> None:
    @app.callback(
        Output("pi-mpd-graph", "figure"),
        Input("graph-store", "data"),
    )
    def render_graph(graph_data):
        if not graph_data or not graph_data.get("t"):
            return empty_figure()

        t = graph_data["t"]
        keys = ["pi_xi", "pi_xq", "pi_yi", "pi_yq", "mpd"]

        traces = [
            {
                "x": t,
                "y": graph_data[key],
                "name": key.upper(),
                "type": "scatter",
                "mode": "lines",
                "line": {"color": TRACE_COLORS[key], "width": 1.5},
            }
            for key in keys
        ]

        return {
            "data": traces,
            "layout": {
                "title": {"text": "Peak Indicators & MPD", "font": {"color": "#cdd6f4"}},
                "paper_bgcolor": _BG,
                "plot_bgcolor": _BG,
                "font": {"color": "#cdd6f4"},
                "xaxis": {
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
