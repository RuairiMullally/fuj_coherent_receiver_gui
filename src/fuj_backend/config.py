"""Application configuration for FIM24725 coherent receiver control.

All settings can be overridden via environment variables (prefix: FUJ_)
or a .env file in the working directory.

Examples:
    FUJ_MCU_MODE=real FUJ_PSU1_IP=10.10.10.137 uvicorn ...
    or place a .env file:
        FUJ_MCU_MODE=real
        FUJ_PSU1_IP=10.10.10.137
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # PSU1 — power rails (VCC_3V3, VPD_5V0) and VOA control
    # Network interface: 10.10.10.x
    # ------------------------------------------------------------------
    psu1_ip: str = "10.10.10.137"
    psu1_port: int = 20001
    psu1_local_ip: str = "10.10.10.50"

    # ------------------------------------------------------------------
    # PSU2 — analog control rails (GA_X, GA_Y, OA_X, OA_Y)
    # Network interface: 10.10.20.x
    # ------------------------------------------------------------------
    psu2_ip: str = "10.10.20.137"
    psu2_port: int = 20002
    psu2_local_ip: str = "10.10.20.50"

    # ------------------------------------------------------------------
    # MCU configuration
    # mcu_mode: "real" opens the serial port; "mock" uses MockMCU (no hardware needed)
    # ------------------------------------------------------------------
    mcu_mode: Literal["real", "mock"] = "mock"
    mcu_port: str = "/dev/arduino"

    # ------------------------------------------------------------------
    # API server
    # ------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = "INFO"
    log_dir: str = "logs"

    # ------------------------------------------------------------------
    # Rate limits (slowapi / limits library format: "N/period")
    # period options: second, minute, hour, day
    # ------------------------------------------------------------------
    rate_control: str = "10/minute"    # startup / shutdown / mode / set* endpoints
    rate_status: str = "120/minute"    # GET /status — 2/sec suits a 500ms UI poll
    rate_telemetry: str = "120/minute" # GET /telemetry/*
    rate_logs: str = "30/minute"       # GET /logs

    model_config = {
        "env_file": ".env",
        "env_prefix": "FUJ_",
        "env_file_encoding": "utf-8",
    }
