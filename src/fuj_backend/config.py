"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, populated from environment variables."""

    debug: bool = False
    hardware_mode: str = "simulator"  # "simulator" or "real"
    host: str = "0.0.0.0"
    port: int = 8000

    # PSU network addresses
    psu1_ip: str = "10.10.10.137"
    psu1_port: int = 20001
    psu1_local_ip: str = "10.10.10.50"
    psu2_ip: str = "10.10.10.138"
    psu2_port: int = 20002
    psu2_local_ip: str = "10.10.10.51"

    # GUI polling interval (milliseconds)
    poll_interval_ms: int = 1500

    model_config = {"case_sensitive": False}
