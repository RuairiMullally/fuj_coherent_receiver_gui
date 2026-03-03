"""WSGI entry point for production use with Gunicorn.

    gunicorn fuj_gui.wsgi:server --workers 1 --threads 4 --bind 0.0.0.0:8050 --timeout 120

Why 1 worker?  Dash's dcc.Store(storage_type="memory") lives in server-side Python
memory. Multiple workers each have isolated memory — the rolling graph history would
be split across workers, losing data on successive requests. Single worker + threads
is the correct topology for this app.

create_app() is called once at module load time. GUISettings reads FUJ_GUI_* env vars
at that point. The fuj-gui console script (main()) is unchanged for local development.
"""

from fuj_gui.app import create_app

_app = create_app()
server = _app.server  # Flask WSGI callable that Gunicorn serves
