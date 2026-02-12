"""Data models for FIM24725 service layer."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SystemState(str, Enum):
    """Overall system state."""

    OFF = "OFF"
    STARTING = "STARTING"
    READY = "READY"
    FAULT = "FAULT"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class OperatingMode(str, Enum):
    """Gain control mode."""

    AGC = "AGC"  # Automatic gain control
    MGC = "MGC"  # Manual gain control


class RailName(str, Enum):
    """Named power/control rails."""

    VCC_3V3 = "VCC_3V3"
    VPD_5V0 = "VPD_5V0"
    VOA_CTRL = "VOA_CTRL"
    GA_X = "GA_X"
    GA_Y = "GA_Y"
    OA_X = "OA_X"
    OA_Y = "OA_Y"


class RailState(str, Enum):
    """Individual rail state."""

    OFF = "OFF"
    ENABLED = "ENABLED"
    FAULT = "FAULT"


class RailConfig(BaseModel):
    """Configuration for a single rail."""

    name: RailName
    psu_name: str  # "PSU1" or "PSU2"
    channel: int = Field(ge=1, le=4)
    nominal_voltage: float
    min_voltage: float = 0.0
    max_voltage: float
    ovp: float
    ocp: float
    verify_voltage: Optional[tuple[float, float]] = None  # (min, max) for verification
    verify_current: Optional[tuple[float, float]] = None  # (min, max) for verification


class RailMeasurement(BaseModel):
    """Measured values for a rail."""

    name: RailName
    voltage: float
    current: float
    state: RailState
    mode: str  # "CV" or "CC"


class PeakIndicators(BaseModel):
    """Peak indicator readings from MCU ADC."""

    pi_xi: float = Field(ge=0.0, le=2.0)
    pi_xq: float = Field(ge=0.0, le=2.0)
    pi_yi: float = Field(ge=0.0, le=2.0)
    pi_yq: float = Field(ge=0.0, le=2.0)


class SystemSnapshot(BaseModel):
    """Complete system state snapshot."""

    state: SystemState
    mode: OperatingMode
    rails: dict[RailName, RailMeasurement]
    sd_enabled: bool
    peak_indicators: Optional[PeakIndicators] = None
    mpd_value: Optional[float] = None
    fault_message: Optional[str] = None


class FaultInfo(BaseModel):
    """Fault information."""

    rail: Optional[RailName] = None
    message: str
    timestamp: float
    recoverable: bool = True
