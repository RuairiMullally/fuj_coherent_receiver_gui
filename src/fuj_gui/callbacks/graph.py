"""Rolling PI / MPD graph callbacks — implemented as clientside functions.

Both callbacks run entirely in the browser (assets/graph_callbacks.js).
Neither makes a network request; both read directly from status-store and
graph-settings-store which are already available client-side.

graph-store format (maintained by update_graph_store):
    {
        "t":      ["2026-02-25T14:32:01.123Z", ...],  # ISO datetime strings
        "pi_xi":  [0.512, ...],
        "pi_xq":  [0.480, ...],
        "pi_yi":  [0.523, ...],
        "pi_yq":  [0.491, ...],
        "mpd":    [0.823, ...],  # differential: MPD+ - MPD-
        "mpd_n":  [0.234, ...],  # MPD- raw
    }

graph-settings-store (initialised once in app.py from GUISettings):
    {"max_points": 120, "window_s": 60}
"""

from __future__ import annotations

from dash import ClientsideFunction, Input, Output, State, clientside_callback


def register(app, settings) -> None:  # noqa: ARG001
    _register_store_update(app)
    _register_graph_render(app)


def _register_store_update(app) -> None:
    clientside_callback(
        ClientsideFunction(
            namespace="graph_callbacks",
            function_name="update_graph_store",
        ),
        Output("graph-store", "data"),
        Input("status-store", "data"),
        State("graph-store", "data"),
        State("graph-settings-store", "data"),
    )


def _register_graph_render(app) -> None:
    clientside_callback(
        ClientsideFunction(
            namespace="graph_callbacks",
            function_name="render_graph",
        ),
        Output("pi-mpd-graph", "figure"),
        Input("graph-store", "data"),
        State("graph-settings-store", "data"),
    )
