"""Log panel polling callback."""

from __future__ import annotations

from dash import ClientsideFunction, Input, Output, clientside_callback
from dash.exceptions import PreventUpdate

from fuj_gui import api_client as _api
from fuj_gui.components.logs import format_log_line


def register(app, settings) -> None:  # noqa: ARG001
    _register_log_poll(app)
    _register_autoscroll(app)


def _register_log_poll(app) -> None:
    @app.callback(
        Output("log-panel", "children"),
        Input("interval-logs", "n_intervals"),
    )
    def poll_logs(n_intervals):
        data = _api.get_client().get_logs(n=100)
        if "error" in data:
            raise PreventUpdate

        lines = data.get("lines", [])
        from dash import html
        children = [format_log_line(line) for line in lines]
        # Sentinel div at the bottom for auto-scroll
        children.append(html.Div(id="log-bottom", style={"height": "0"}))
        return children


def _register_autoscroll(app) -> None:
    clientside_callback(
        """
        function(children) {
            var el = document.getElementById('log-bottom');
            if (el) { el.scrollIntoView({behavior: 'instant'}); }
            return window.dash_clientside.no_update;
        }
        """,
        Output("log-panel", "data-scroll"),
        Input("log-panel", "children"),
        prevent_initial_call=True,
    )
