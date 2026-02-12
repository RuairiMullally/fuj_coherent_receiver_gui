"""FIM24725 Coherent Receiver Service Layer.

This package provides high-level control of the FIM24725 coherent optical
receiver module through a safe, state-managed API.

Main entry point:
    FIM24725Service - High-level service facade

Example:
    from fuj_backend.services import FIM24725Service, OperatingMode

    service = FIM24725Service(
        psu1_ip="192.168.1.10", psu1_port=20001,
        psu2_ip="192.168.1.11", psu2_port=20002,
    )

    try:
        service.startup()
        service.set_voa(2.4)
        service.set_oa_x(1.65)
        service.set_mode(OperatingMode.MGC)
        service.set_ga_x(1.0)
    finally:
        service.shutdown()
"""

from __future__ import annotations

from .exceptions import (
    BoundsError,
    FIM24725Error,
    MCUError,
    RailError,
    SequenceError,
    StateError,
    VerificationError,
)
from .fim24725_service import FIM24725Service
from .logging import get_service_logger, setup_service_logger
from .mcu_interface import MCUInterface, MockMCU
from .models import (
    FaultInfo,
    OperatingMode,
    PeakIndicators,
    RailConfig,
    RailMeasurement,
    RailName,
    RailState,
    SystemSnapshot,
    SystemState,
)
from .rail_config import RailRegistry

__all__ = [
    # Main service
    "FIM24725Service",
    # Models
    "SystemState",
    "OperatingMode",
    "RailName",
    "RailState",
    "RailConfig",
    "RailMeasurement",
    "PeakIndicators",
    "SystemSnapshot",
    "FaultInfo",
    # Rail configuration
    "RailRegistry",
    # MCU
    "MCUInterface",
    "MockMCU",
    # Exceptions
    "FIM24725Error",
    "StateError",
    "RailError",
    "BoundsError",
    "VerificationError",
    "MCUError",
    "SequenceError",
    # Logging
    "setup_service_logger",
    "get_service_logger",
]
