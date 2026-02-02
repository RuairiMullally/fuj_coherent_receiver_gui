from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application configuration settings."""

    # Application
    app_name: str = "FUJ Coherent Receiver Backend"
    version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Hardware
    hardware_mode: Literal["simulator", "real"] = "simulator"
    num_channels: int = 8

    # Channel limits
    channel_min_value: float = 0.0
    channel_max_value: float = 1.0

    # Safety
    max_rate_changes_per_second: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
