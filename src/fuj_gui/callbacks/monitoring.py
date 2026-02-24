"""Dash callbacks for PI/MPD monitoring and time-series graphs."""

from __future__ import annotations

import time

import plotly.graph_objs as go
from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate

from fuj_backend.dependencies import get_service

MAX_HISTORY = 300  # ~7.5 minutes at 1.5s polling

STATE_COLORS = {
    "OFF": "secondary",
    "STARTING": "warning",
    "READY": "success",
    "FAULT": "danger",
    "SHUTTING_DOWN": "warning",
}


def _build_pi_figure(pi_hist: dict) -> go.Figure:
    """Build the Peak Indicators time-series graph."""
    timestamps = pi_hist.get("timestamps", [])
    if timestamps:
        t0 = timestamps[0]
        x_vals = [t - t0 for t in timestamps]
    else:
        x_vals = []

    fig = go.Figure()
    for name, color in [
        ("pi_xi", "#1f77b4"),
        ("pi_xq", "#ff7f0e"),
        ("pi_yi", "#2ca02c"),
        ("pi_yq", "#d62728"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=pi_hist.get(name, []),
                mode="lines",
                name=name.upper().replace("_", " "),
                line=dict(color=color),
            )
        )

    fig.update_layout(
        xaxis_title="Time (s)",
        yaxis_title="Voltage (V)",
        yaxis=dict(range=[0, 2.1]),
        height=280,
        margin=dict(l=50, r=20, t=10, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def _build_mpd_figure(mpd_hist: dict) -> go.Figure:
    """Build the MPD time-series graph."""
    timestamps = mpd_hist.get("timestamps", [])
    if timestamps:
        t0 = timestamps[0]
        x_vals = [t - t0 for t in timestamps]
    else:
        x_vals = []

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=mpd_hist.get("values", []),
            mode="lines",
            name="MPD",
            line=dict(color="#9467bd"),
        )
    )

    fig.update_layout(
        xaxis_title="Time (s)",
        yaxis_title="Value",
        yaxis=dict(range=[0, 1.1]),
        height=230,
        margin=dict(l=50, r=20, t=10, b=40),
    )
    return fig


def register_monitoring_callbacks(app: Dash) -> None:
    """Register monitoring and polling callbacks."""

    @app.callback(
        Output("pi-history", "data"),
        Output("mpd-history", "data"),
        Output("system-state", "data"),
        Output("state-badge", "children"),
        Output("state-badge", "color"),
        Output("mode-badge", "children"),
        Output("pi-graph", "figure"),
        Output("mpd-graph", "figure"),
        Input("poll-interval", "n_intervals"),
        State("pi-history", "data"),
        State("mpd-history", "data"),
    )
    def poll_and_update(n_intervals, pi_hist, mpd_hist):
        try:
            service = get_service()
        except RuntimeError:
            raise PreventUpdate

        current_state = service.state.value
        current_mode = service.mode.value
        now = time.time()

        state_color = STATE_COLORS.get(current_state, "secondary")

        # Only read PI/MPD when system is READY
        pi = None
        mpd_val = None
        if current_state == "READY":
            try:
                pi = service.read_peak_indicators()
                mpd_val = service.read_mpd()
            except Exception:
                pass  # Skip this tick on read failure

        # Append to PI history
        if pi is not None:
            pi_hist["timestamps"].append(now)
            pi_hist["pi_xi"].append(pi.pi_xi)
            pi_hist["pi_xq"].append(pi.pi_xq)
            pi_hist["pi_yi"].append(pi.pi_yi)
            pi_hist["pi_yq"].append(pi.pi_yq)
            for key in pi_hist:
                pi_hist[key] = pi_hist[key][-MAX_HISTORY:]

        # Append to MPD history
        if mpd_val is not None:
            mpd_hist["timestamps"].append(now)
            mpd_hist["values"].append(mpd_val)
            for key in mpd_hist:
                mpd_hist[key] = mpd_hist[key][-MAX_HISTORY:]

        pi_fig = _build_pi_figure(pi_hist)
        mpd_fig = _build_mpd_figure(mpd_hist)

        sys_data = {"state": current_state, "mode": current_mode}

        return (
            pi_hist,
            mpd_hist,
            sys_data,
            current_state,
            state_color,
            current_mode,
            pi_fig,
            mpd_fig,
        )
