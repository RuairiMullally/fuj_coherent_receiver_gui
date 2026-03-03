"""Log panel callbacks.

Architecture:
- poll_logs: fetches only NEW lines from the API (since_seq delta), merges
  them into log-store (client-side accumulation, capped at _MAX_LOG_LINES).
- render_logs: re-renders the panel from log-store whenever the store changes
  or the debug toggle changes. No network call; pure local filtering.
- autoscroll: clientside JS that scrolls to the bottom only when the user is
  already near the bottom, preserving scroll position when reading history.
"""

from __future__ import annotations

from dash import Input, Output, State, clientside_callback
from dash.exceptions import PreventUpdate

from fuj_gui import api_client as _api
from fuj_gui.components.logs import format_log_line

_MAX_LOG_LINES = 500


def register(app, settings) -> None:  # noqa: ARG001
    _register_log_poll(app)
    _register_log_render(app)
    _register_autoscroll(app)


def _register_log_poll(app) -> None:
    @app.callback(
        Output("log-store", "data"),
        Input("interval-logs", "n_intervals"),
        State("log-store", "data"),
    )
    def poll_logs(n_intervals, log_state):
        log_state = log_state or {"lines": [], "last_seq": -1}
        last_seq = log_state["last_seq"]

        data = _api.get_client().get_logs(since_seq=last_seq)
        if "error" in data:
            raise PreventUpdate

        new_lines = data.get("lines", [])
        max_seq = data.get("max_seq", last_seq)

        if not new_lines:
            raise PreventUpdate

        all_lines = log_state["lines"] + new_lines
        if len(all_lines) > _MAX_LOG_LINES:
            all_lines = all_lines[-_MAX_LOG_LINES:]

        return {"lines": all_lines, "last_seq": max_seq}


def _register_log_render(app) -> None:
    @app.callback(
        Output("log-panel", "children"),
        Input("log-store", "data"),
        Input("log-debug-toggle", "value"),
    )
    def render_logs(log_state, show_debug):
        if not log_state:
            raise PreventUpdate

        lines = log_state.get("lines", [])
        if not show_debug:
            lines = [l for l in lines if l.get("level") != "DEBUG"]

        return [format_log_line(line) for line in lines]


def _register_autoscroll(app) -> None:
    clientside_callback(
        """
        function(children) {
            var el = document.getElementById('log-panel');
            if (el) {
                // Only auto-scroll if the user is already near the bottom.
                // This preserves scroll position when reading history.
                var atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
                if (atBottom) {
                    el.scrollTop = el.scrollHeight;
                }
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("log-panel", "data-scroll"),
        Input("log-panel", "children"),
        prevent_initial_call=True,
    )
