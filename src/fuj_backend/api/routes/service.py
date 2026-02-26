"""Service control routes: /status, /startup, /shutdown, /mode.

Thread safety: All handlers are sync `def`. FastAPI runs them in its thread pool.
The service RLock serialises concurrent requests automatically — no additional
locking is required here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from fuj_backend.api.deps import get_service
from fuj_backend.api.limiter import limiter
from fuj_backend.api.models import (
    ActionResponse,
    FaultOut,
    ModeRequest,
    PeakIndicatorsOut,
    RailMeasurementOut,
    ServiceStatusResponse,
    StartupRequest,
)
from fuj_backend.services.fim24725_service import FIM24725Service

router = APIRouter()


def _build_status(service: FIM24725Service) -> ServiceStatusResponse:
    snap = service.get_snapshot()
    rails_out = {
        name.value: RailMeasurementOut(
            voltage=meas.voltage,
            current=meas.current,
            state=meas.state,
            mode=meas.mode,
        )
        for name, meas in snap.rails.items()
    }
    pi_out = None
    if snap.peak_indicators is not None:
        pi = snap.peak_indicators
        pi_out = PeakIndicatorsOut(
            pi_xi=pi.pi_xi, pi_xq=pi.pi_xq, pi_yi=pi.pi_yi, pi_yq=pi.pi_yq
        )
    fault_out = None
    if snap.fault_message:
        fi = service.fault_info
        fault_out = FaultOut(
            message=snap.fault_message,
            timestamp=fi.timestamp if fi else 0.0,
            recoverable=fi.recoverable if fi else True,
        )
    return ServiceStatusResponse(
        state=snap.state,
        mode=snap.mode,
        sd_enabled=snap.sd_enabled,
        rails=rails_out,
        peak_indicators=pi_out,
        mpd_value=snap.mpd_value,
        fault=fault_out,
    )


@router.get("/status", response_model=ServiceStatusResponse)
@limiter.limit("300/minute")
def get_status(
    request: Request,
    service: FIM24725Service = Depends(get_service),
) -> ServiceStatusResponse:
    """Return a full system snapshot (state, mode, rails, PI, MPD, fault)."""
    return _build_status(service)


@router.post("/startup", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_startup(
    request: Request,
    body: StartupRequest,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Trigger the full power-on sequence in the requested mode."""
    service.startup(body.mode)
    return ActionResponse(ok=True, state=service.state)


@router.post("/shutdown", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_shutdown(
    request: Request,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Trigger the orderly power-down sequence."""
    service.shutdown()
    return ActionResponse(ok=True, state=service.state)


@router.post("/mode", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_mode(
    request: Request,
    body: ModeRequest,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Switch between AGC and MGC modes. System must be READY."""
    service.set_mode(body.mode)
    return ActionResponse(ok=True, state=service.state)
