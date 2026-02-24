"""Dash callbacks for control operations (startup, shutdown, voltage, mode)."""

from __future__ import annotations

from dash import Dash, Input, Output, State, no_update
from dash.exceptions import PreventUpdate

from fuj_backend.dependencies import get_service
from fuj_backend.services.exceptions import StateError
from fuj_backend.services.models import OperatingMode


def register_control_callbacks(app: Dash) -> None:
    """Register all control-related callbacks."""

    # --- Startup ---

    @app.callback(
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("startup-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_startup(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        service = get_service()
        try:
            service.startup()
            return "Startup complete. System READY.", "success", True
        except StateError as e:
            return f"Cannot start: {e}", "warning", True
        except Exception as e:
            return f"Startup failed: {e}", "danger", True

    # --- Shutdown ---

    @app.callback(
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("shutdown-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_shutdown(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        service = get_service()
        try:
            service.shutdown()
            return "Shutdown complete. System OFF.", "success", True
        except Exception as e:
            return f"Shutdown failed: {e}", "danger", True

    # --- VOA ---

    @app.callback(
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("voa-set-btn", "n_clicks"),
        State("voa-input", "value"),
        prevent_initial_call=True,
    )
    def handle_set_voa(n_clicks, volts):
        if not n_clicks or volts is None:
            raise PreventUpdate
        service = get_service()
        try:
            service.set_voa(float(volts))
            return f"VOA set to {volts}V", "success", True
        except StateError as e:
            return f"Cannot set VOA: {e}", "warning", True
        except Exception as e:
            return f"VOA error: {e}", "danger", True

    # --- OA_X ---

    @app.callback(
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("oa-x-set-btn", "n_clicks"),
        State("oa-x-input", "value"),
        prevent_initial_call=True,
    )
    def handle_set_oa_x(n_clicks, volts):
        if not n_clicks or volts is None:
            raise PreventUpdate
        service = get_service()
        try:
            service.set_oa_x(float(volts))
            return f"OA_X set to {volts}V", "success", True
        except StateError as e:
            return f"Cannot set OA_X: {e}", "warning", True
        except Exception as e:
            return f"OA_X error: {e}", "danger", True

    # --- OA_Y ---

    @app.callback(
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("oa-y-set-btn", "n_clicks"),
        State("oa-y-input", "value"),
        prevent_initial_call=True,
    )
    def handle_set_oa_y(n_clicks, volts):
        if not n_clicks or volts is None:
            raise PreventUpdate
        service = get_service()
        try:
            service.set_oa_y(float(volts))
            return f"OA_Y set to {volts}V", "success", True
        except StateError as e:
            return f"Cannot set OA_Y: {e}", "warning", True
        except Exception as e:
            return f"OA_Y error: {e}", "danger", True

    # --- GA_X ---

    @app.callback(
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("ga-x-set-btn", "n_clicks"),
        State("ga-x-input", "value"),
        prevent_initial_call=True,
    )
    def handle_set_ga_x(n_clicks, volts):
        if not n_clicks or volts is None:
            raise PreventUpdate
        service = get_service()
        try:
            service.set_ga_x(float(volts))
            return f"GA_X set to {volts}V", "success", True
        except StateError as e:
            return f"Cannot set GA_X: {e}", "warning", True
        except Exception as e:
            return f"GA_X error: {e}", "danger", True

    # --- GA_Y ---

    @app.callback(
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("ga-y-set-btn", "n_clicks"),
        State("ga-y-input", "value"),
        prevent_initial_call=True,
    )
    def handle_set_ga_y(n_clicks, volts):
        if not n_clicks or volts is None:
            raise PreventUpdate
        service = get_service()
        try:
            service.set_ga_y(float(volts))
            return f"GA_Y set to {volts}V", "success", True
        except StateError as e:
            return f"Cannot set GA_Y: {e}", "warning", True
        except Exception as e:
            return f"GA_Y error: {e}", "danger", True

    # --- Mode Toggle ---

    @app.callback(
        Output("ga-x-input", "disabled"),
        Output("ga-x-set-btn", "disabled"),
        Output("ga-y-input", "disabled"),
        Output("ga-y-set-btn", "disabled"),
        Output("alert-message", "children", allow_duplicate=True),
        Output("alert-message", "color", allow_duplicate=True),
        Output("alert-message", "is_open", allow_duplicate=True),
        Input("mode-toggle", "value"),
        prevent_initial_call=True,
    )
    def handle_mode_change(mode_value):
        is_agc = mode_value == "AGC"
        service = get_service()

        # If system is not READY, just update UI state without calling service
        if service.state.value != "READY":
            return is_agc, is_agc, is_agc, is_agc, no_update, no_update, no_update

        try:
            service.set_mode(OperatingMode(mode_value))
            return (
                is_agc,
                is_agc,
                is_agc,
                is_agc,
                f"Mode switched to {mode_value}",
                "success",
                True,
            )
        except Exception as e:
            return (
                is_agc,
                is_agc,
                is_agc,
                is_agc,
                f"Mode switch failed: {e}",
                "danger",
                True,
            )
