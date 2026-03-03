"""GUI configuration loaded from environment variables (prefix FUJ_GUI_) or .env file."""

from pydantic_settings import BaseSettings


class GUISettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    gui_host: str = "127.0.0.1"
    gui_port: int = 8050
    debug: bool = False
    poll_interval_ms: int = 500
    log_poll_interval_ms: int = 2000
    graph_history_s: int = 60

    model_config = {"env_file": ".env", "env_prefix": "FUJ_GUI_"}
