"""Dash callback registration."""

from __future__ import annotations

from dash import Dash

from .controls import register_control_callbacks
from .monitoring import register_monitoring_callbacks


def register_all_callbacks(app: Dash) -> None:
    """Register all Dash callbacks with the app."""
    register_control_callbacks(app)
    register_monitoring_callbacks(app)
