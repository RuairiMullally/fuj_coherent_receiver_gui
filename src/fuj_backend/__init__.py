"""FUJ Backend - Hardware control and services for FIM24725.

This package provides:
- hardware: Low-level HAL for PSU control
- services: High-level service layer for FIM24725 control
"""

from __future__ import annotations

from .services import (
    FIM24725Service,
    FaultInfo,
    MCUInterface,
    MockMCU,
    OperatingMode,
    PeakIndicators,
    RailMeasurement,
    RailName,
    RailRegistry,
    RailState,
    SystemSnapshot,
    SystemState,
)

__all__ = [
    # Main service
    "FIM24725Service",
    # Models
    "SystemState",
    "OperatingMode",
    "RailName",
    "RailState",
    "RailMeasurement",
    "PeakIndicators",
    "SystemSnapshot",
    "FaultInfo",
    # Rail configuration
    "RailRegistry",
    # MCU
    "MCUInterface",
    "MockMCU",
]
