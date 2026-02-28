"""Request and response Pydantic models for the FIM24725 REST API.

These are separate from the service-layer models in fuj_backend.services.models
so that the API contract can evolve independently of internal data structures.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from fuj_backend.api.log_buffer import LogLine
from fuj_backend.services.models import OperatingMode, RailState, SystemState

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class StartupRequest(BaseModel):
    mode: OperatingMode = OperatingMode.AGC


class ModeRequest(BaseModel):
    mode: OperatingMode


class VoaRequest(BaseModel):
    """VOA voltage setpoint — clamped to 0–4.8 V at the service layer too."""
    voltage: Annotated[float, Field(ge=0.0, le=4.8)]


class OaGaRequest(BaseModel):
    """OA_X / OA_Y / GA_X / GA_Y voltage setpoint — clamped to 0–3.3 V."""
    voltage: Annotated[float, Field(ge=0.0, le=3.3)]


class SweepRequest(BaseModel):
    channel: Literal["X", "Y"]
    start: float
    end: float
    step: float
    dwell_ms: int = 100


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ActionResponse(BaseModel):
    """Generic response for control actions (startup, shutdown, set_*)."""

    ok: bool
    state: SystemState  # system state *after* the action
    message: str = ""


class RailMeasurementOut(BaseModel):
    voltage: float
    current: float
    state: RailState
    mode: str  # "CV" or "CC"


class PeakIndicatorsOut(BaseModel):
    pi_xi: float
    pi_xq: float
    pi_yi: float
    pi_yq: float


class FaultOut(BaseModel):
    message: str
    timestamp: float
    recoverable: bool


class ServiceStatusResponse(BaseModel):
    """Full system snapshot — returned by GET /status."""

    state: SystemState
    mode: OperatingMode
    sd_enabled: bool
    rails: dict[str, RailMeasurementOut]  # keyed by RailName.value
    peak_indicators: Optional[PeakIndicatorsOut] = None
    mpd_value: Optional[float] = None
    fault: Optional[FaultOut] = None


class SweepPoint(BaseModel):
    voltage: float
    pi: PeakIndicatorsOut


class SweepResponse(BaseModel):
    """Result of a GA sweep operation."""

    channel: str
    points: list[SweepPoint]


class LogsResponse(BaseModel):
    """Log lines returned by GET /logs."""

    lines: list[LogLine]
    total_buffered: int
    max_seq: int  # highest seq in the buffer; pass back as since_seq on next poll
