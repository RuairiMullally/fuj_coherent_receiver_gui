"""Status polling and control callbacks.

Registers:
- Poll callback: status-store ← interval-status
- Header update: state-badge, mode-switch disabled, buttons ← status-store
- Mode init (once): mode-switch.value ← first non-empty status-store
- Control placeholder + disabled update ← status-store
- Mode toggle callback
- Startup/shutdown modal open + confirm callbacks
- SET button callbacks (voa, oa-x, oa-y, ga-x, ga-y)

Mode switch design note:
    update_header does NOT write mode-switch.value. Writing it on every 500ms
    poll would race with the user's click (Dash cannot distinguish programmatic
    from user-initiated value changes). Instead:
      - _register_mode_init sets the value exactly once on first status load.
      - toggle_mode, startup_confirm, and shutdown_confirm update it explicitly
        after each API call confirms the new mode.
"""

from __future__ import annotations

from dash import Input, Output, State, callback_context, no_update
from dash.exceptions import PreventUpdate

from fuj_gui import api_client as _api
from fuj_gui.config import GUISettings

_STATE_COLORS = {
    "OFF": "secondary",
    "STARTING": "info",
    "READY": "success",
    "SHUTTING_DOWN": "warning",
    "FAULT": "danger",
}

_GA_SUFFIXES = ("ga-x", "ga-y")
_ALL_CONTROL_SUFFIXES = ("voa", "oa-x", "oa-y", "ga-x", "ga-y")


def register(app, settings: GUISettings) -> None:  # noqa: ARG001
    _register_poll(app)
    _register_header_update(app)
    _register_mode_init(app)
    _register_control_placeholders(app)
    _register_mode_toggle(app)
    _register_startup_modal_open(app)
    _register_startup_confirm(app)
    _register_shutdown_modal_open(app)
    _register_shutdown_confirm(app)
    _register_set_buttons(app)


# ---------------------------------------------------------------------------
# 1. Status poll
# ---------------------------------------------------------------------------

def _register_poll(app) -> None:
    @app.callback(
        Output("status-store", "data"),
        Output("error-toast", "is_open"),
        Output("error-toast-body", "children"),
        Input("interval-status", "n_intervals"),
        prevent_initial_call=False,
    )
    def poll_status(n_intervals):
        data = _api.get_client().get_status()
        if "error" in data:
            return no_update, True, data["error"]
        return data, False, ""


# ---------------------------------------------------------------------------
# 2. Header update — badge + button disabled states only.
#    Does NOT write mode-switch.value (see module docstring).
# ---------------------------------------------------------------------------

def _register_header_update(app) -> None:
    @app.callback(
        Output("state-badge", "children"),
        Output("state-badge", "color"),
        Output("mode-switch", "disabled"),
        Output("startup-btn", "disabled"),
        Output("shutdown-btn", "disabled"),
        Input("status-store", "data"),
    )
    def update_header(data):
        if not data:
            raise PreventUpdate

        state = data.get("state", "OFF")

        badge_color = _STATE_COLORS.get(state, "secondary")
        mode_disabled = state != "READY"
        startup_disabled = state != "OFF"
        shutdown_disabled = state in ("OFF", "SHUTTING_DOWN")

        return state, badge_color, mode_disabled, startup_disabled, shutdown_disabled


# ---------------------------------------------------------------------------
# 3. Mode switch — one-time initialisation on first status load.
#    After the flag flips to True this callback permanently raises PreventUpdate,
#    so subsequent polls never touch mode-switch.value again.
# ---------------------------------------------------------------------------

def _register_mode_init(app) -> None:
    @app.callback(
        Output("mode-switch", "value"),
        Output("mode-initialized-store", "data"),
        Input("status-store", "data"),
        State("mode-initialized-store", "data"),
        prevent_initial_call=True,
    )
    def init_mode_once(status_data, initialized):
        if initialized or not status_data:
            raise PreventUpdate
        mode = status_data.get("mode", "AGC")
        return (mode == "MGC"), True


# ---------------------------------------------------------------------------
# 4. Control placeholders + disabled state (inputs AND buttons) + GA badges
# ---------------------------------------------------------------------------

def _register_control_placeholders(app) -> None:
    _rail_key_map = {
        "voa":  "VOA_CTRL",
        "oa-x": "OA_X",
        "oa-y": "OA_Y",
        "ga-x": "GA_X",
        "ga-y": "GA_Y",
    }

    outputs = []
    for s in _ALL_CONTROL_SUFFIXES:
        outputs.append(Output(f"input-{s}", "placeholder"))
        outputs.append(Output(f"input-{s}", "disabled"))
        outputs.append(Output(f"btn-set-{s}", "disabled"))
    for s in _GA_SUFFIXES:
        outputs.append(Output(f"prestage-badge-{s}", "style"))

    @app.callback(
        outputs,
        Input("status-store", "data"),
    )
    def update_controls(data):
        if not data:
            raise PreventUpdate

        state = data.get("state", "OFF")
        mode = data.get("mode", "AGC")
        rails = data.get("rails", {})
        ready = state == "READY"

        result = []
        for s in _ALL_CONTROL_SUFFIXES:
            rail_name = _rail_key_map[s]
            rail = rails.get(rail_name, {})
            voltage = rail.get("voltage")
            placeholder = f"{voltage:.3f}" if voltage is not None else "—"
            result.append(placeholder)   # input placeholder
            result.append(not ready)     # input disabled
            result.append(not ready)     # button disabled

        # GA pre-staging badges: visible in AGC mode when READY
        show_prestage = ready and mode == "AGC"
        badge_style = {"display": "inline"} if show_prestage else {"display": "none"}
        result.append(badge_style)
        result.append(badge_style)

        return result


# ---------------------------------------------------------------------------
# 5. Mode toggle
# ---------------------------------------------------------------------------

def _register_mode_toggle(app) -> None:
    @app.callback(
        Output("status-store", "data", allow_duplicate=True),
        Output("error-toast", "is_open", allow_duplicate=True),
        Output("error-toast-body", "children", allow_duplicate=True),
        Output("mode-switch", "value", allow_duplicate=True),
        Input("mode-switch", "value"),
        State("status-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_mode(switch_value, store_data):
        if not store_data:
            raise PreventUpdate

        current_mode = store_data.get("mode", "AGC")
        target_mode = "MGC" if switch_value else "AGC"

        if target_mode == current_mode:
            raise PreventUpdate

        result = _api.get_client().set_mode(target_mode)
        if "error" in result:
            # Revert the switch to the server-confirmed mode
            return no_update, True, result["error"], (current_mode == "MGC")

        status = _api.get_client().get_status()
        if "error" in status:
            return no_update, True, status["error"], no_update

        confirmed_mode = status.get("mode", "AGC")
        return status, False, "", (confirmed_mode == "MGC")


# ---------------------------------------------------------------------------
# 6. Startup modal open
# ---------------------------------------------------------------------------

def _register_startup_modal_open(app) -> None:
    @app.callback(
        Output("startup-modal", "is_open"),
        Input("startup-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_startup_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return True


# ---------------------------------------------------------------------------
# 7. Startup confirm
# ---------------------------------------------------------------------------

def _register_startup_confirm(app) -> None:
    @app.callback(
        Output("startup-modal", "is_open", allow_duplicate=True),
        Output("status-store", "data", allow_duplicate=True),
        Output("error-toast", "is_open", allow_duplicate=True),
        Output("error-toast-body", "children", allow_duplicate=True),
        Output("mode-switch", "value", allow_duplicate=True),
        Input("startup-modal-confirm", "n_clicks"),
        Input("startup-modal-cancel", "n_clicks"),
        State("startup-modal-mode", "value"),
        prevent_initial_call=True,
    )
    def handle_startup_modal(confirm_clicks, cancel_clicks, mode):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        if trigger_id == "startup-modal-cancel":
            return False, no_update, False, "", no_update

        if not confirm_clicks:
            raise PreventUpdate

        startup_mode = mode or "AGC"
        result = _api.get_client().startup(startup_mode)
        if "error" in result:
            return False, no_update, True, result["error"], no_update

        status = _api.get_client().get_status()
        if "error" in status:
            return False, no_update, True, status["error"], no_update

        confirmed_mode = status.get("mode", "AGC")
        return False, status, False, "", (confirmed_mode == "MGC")


# ---------------------------------------------------------------------------
# 8. Shutdown modal open
# ---------------------------------------------------------------------------

def _register_shutdown_modal_open(app) -> None:
    @app.callback(
        Output("shutdown-modal", "is_open"),
        Input("shutdown-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_shutdown_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return True


# ---------------------------------------------------------------------------
# 9. Shutdown confirm
# ---------------------------------------------------------------------------

def _register_shutdown_confirm(app) -> None:
    @app.callback(
        Output("shutdown-modal", "is_open", allow_duplicate=True),
        Output("status-store", "data", allow_duplicate=True),
        Output("error-toast", "is_open", allow_duplicate=True),
        Output("error-toast-body", "children", allow_duplicate=True),
        Output("mode-switch", "value", allow_duplicate=True),
        Input("shutdown-modal-confirm", "n_clicks"),
        Input("shutdown-modal-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_shutdown_modal(confirm_clicks, cancel_clicks):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        if trigger_id == "shutdown-modal-cancel":
            return False, no_update, False, "", no_update

        if not confirm_clicks:
            raise PreventUpdate

        result = _api.get_client().shutdown()
        if "error" in result:
            return False, no_update, True, result["error"], no_update

        status = _api.get_client().get_status()
        if "error" in status:
            return False, no_update, True, status["error"], no_update

        # Shutdown always returns device to OFF/AGC
        return False, status, False, "", False


# ---------------------------------------------------------------------------
# 10. SET button callbacks
# ---------------------------------------------------------------------------

def _register_set_buttons(app) -> None:
    _api_method_map = {
        "voa":  lambda v: _api.get_client().set_voa(v),
        "oa-x": lambda v: _api.get_client().set_oa_x(v),
        "oa-y": lambda v: _api.get_client().set_oa_y(v),
        "ga-x": lambda v: _api.get_client().set_ga_x(v),
        "ga-y": lambda v: _api.get_client().set_ga_y(v),
    }

    for suffix, api_call in _api_method_map.items():
        _make_set_callback(app, suffix, api_call)


def _make_set_callback(app, suffix: str, api_call) -> None:
    @app.callback(
        Output("status-store", "data", allow_duplicate=True),
        Output("error-toast", "is_open", allow_duplicate=True),
        Output("error-toast-body", "children", allow_duplicate=True),
        Input(f"btn-set-{suffix}", "n_clicks"),
        State(f"input-{suffix}", "value"),
        State("status-store", "data"),
        prevent_initial_call=True,
    )
    def _set_control(n_clicks, value, store_data, _suffix=suffix, _call=api_call):
        if not n_clicks or value is None:
            raise PreventUpdate

        result = _call(float(value))
        if "error" in result:
            return no_update, True, result["error"]

        status = _api.get_client().get_status()
        if "error" in status:
            return no_update, True, status["error"]

        return status, False, ""
