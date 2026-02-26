"""Callback registration entry point."""

from fuj_gui.callbacks import graph, logs, status
from fuj_gui.config import GUISettings


def register_all(app, settings: GUISettings) -> None:
    """Register all callbacks with the Dash app."""
    status.register(app, settings)
    graph.register(app, settings)
    logs.register(app, settings)
