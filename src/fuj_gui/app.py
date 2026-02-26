"""Dash application factory for the FIM24725 coherent receiver UI.

Entry points:
    fuj-gui                    (console script)
    python -m fuj_gui.app
    python -c "from fuj_gui.app import create_app; app = create_app(); app.run(...)"

Configuration:
    All settings loaded from environment variables (prefix FUJ_GUI_) or a .env file.
    Key options:
        FUJ_GUI_API_BASE_URL=http://localhost:8000
        FUJ_GUI_GUI_HOST=127.0.0.1
        FUJ_GUI_GUI_PORT=8050
        FUJ_GUI_DEBUG=false
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Dash, dcc, html

from fuj_gui import api_client
from fuj_gui.components import (
    build_controls_panel,
    build_graph_panel,
    build_header,
    build_logs_panel,
    empty_figure,
)
from fuj_gui.config import GUISettings


def create_app(settings: GUISettings | None = None) -> Dash:
    """Create and configure the Dash application."""
    settings = settings or GUISettings()
    api_client.init_client(settings.api_base_url)

    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        title="FIM24725 Control",
        suppress_callback_exceptions=True,
    )
    app.layout = _build_layout(settings)

    from fuj_gui.callbacks import register_all
    register_all(app, settings)

    return app


def _build_layout(settings: GUISettings) -> html.Div:
    return html.Div(
        [
            # Hidden stores and intervals
            dcc.Store(id="status-store", storage_type="memory"),
            dcc.Store(id="graph-store", storage_type="memory"),
            dcc.Store(id="mode-initialized-store", storage_type="memory", data=False),
            dcc.Interval(
                id="interval-status",
                interval=settings.poll_interval_ms,
                n_intervals=0,
            ),
            dcc.Interval(
                id="interval-logs",
                interval=settings.log_poll_interval_ms,
                n_intervals=0,
            ),

            dbc.Container(
                [
                    # Header
                    build_header(),

                    html.Hr(className="my-2"),

                    # Controls + Graph row
                    dbc.Row(
                        [
                            dbc.Col(build_controls_panel(), md=4),
                            dbc.Col(build_graph_panel(), md=8),
                        ],
                        className="mb-3",
                    ),

                    # Logs
                    dbc.Row(
                        dbc.Col(build_logs_panel()),
                        className="mb-3",
                    ),
                ],
                fluid=True,
                className="py-3",
            ),
        ]
    )


def main() -> None:
    settings = GUISettings()
    app = create_app(settings)
    app.run(
        host=settings.gui_host,
        port=settings.gui_port,
        debug=settings.debug,
    )


if __name__ == "__main__":
    main()
