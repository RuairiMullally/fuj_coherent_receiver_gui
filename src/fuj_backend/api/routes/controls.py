"""Control rail routes: /controls/voa, /oa_x, /oa_y, /ga_x, /ga_y, /sweep_ga.

Thread safety: All handlers are sync `def`. FastAPI runs them in its thread pool.
The service RLock serialises concurrent requests automatically — no additional
locking is required here.

Sweep note: sweep_ga is long-running (seconds to minutes depending on range and
dwell time). The service RLock is held for the full sweep duration, blocking all
other control commands until it completes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from fuj_backend.api.deps import get_service
from fuj_backend.api.limiter import limiter
from fuj_backend.api.models import (
    ActionResponse,
    GaRequest,
    OaRequest,
    PeakIndicatorsOut,
    SweepPoint,
    SweepRequest,
    SweepResponse,
    VoaRequest,
)
from fuj_backend.services.fim24725_service import FIM24725Service

router = APIRouter()


@router.post("/voa", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_voa(
    request: Request,
    body: VoaRequest,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Set VOA control voltage (0–4.8 V)."""
    service.set_voa(body.voltage)
    return ActionResponse(ok=True, state=service.state)


@router.post("/oa_x", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_oa_x(
    request: Request,
    body: OaRequest,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Set OA_X output amplitude (0.5–2 V per app notes AGC mode range)."""
    service.set_oa_x(body.voltage)
    return ActionResponse(ok=True, state=service.state)


@router.post("/oa_y", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_oa_y(
    request: Request,
    body: OaRequest,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Set OA_Y output amplitude (0.5–2 V per app notes AGC mode range)."""
    service.set_oa_y(body.voltage)
    return ActionResponse(ok=True, state=service.state)


@router.post("/ga_x", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_ga_x(
    request: Request,
    body: GaRequest,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Set GA_X gain adjust voltage (0–3.3 V).

    Safe to call in AGC mode — the FIM24725 ignores GA pins in AGC, but the
    PSU accepts the value, pre-staging it for immediate use when MGC is selected.
    """
    service.set_ga_x(body.voltage)
    return ActionResponse(ok=True, state=service.state)


@router.post("/ga_y", response_model=ActionResponse)
@limiter.limit("10/minute")
def post_ga_y(
    request: Request,
    body: GaRequest,
    service: FIM24725Service = Depends(get_service),
) -> ActionResponse:
    """Set GA_Y gain adjust voltage (0–3.3 V). See ga_x note on pre-staging."""
    service.set_ga_y(body.voltage)
    return ActionResponse(ok=True, state=service.state)


@router.post("/sweep_ga", response_model=SweepResponse)
@limiter.limit("10/minute")
def post_sweep_ga(
    request: Request,
    body: SweepRequest,
    service: FIM24725Service = Depends(get_service),
) -> SweepResponse:
    """Sweep a GA channel across a voltage range and return PI at each step.

    Requires MGC mode. Long-running — the service lock is held for the duration.
    """
    results = service.sweep_ga(
        channel=body.channel,
        start=body.start,
        end=body.end,
        step=body.step,
        dwell_ms=body.dwell_ms,
    )
    points = [
        SweepPoint(
            voltage=v,
            pi=PeakIndicatorsOut(
                pi_xi=pi.pi_xi,
                pi_xq=pi.pi_xq,
                pi_yi=pi.pi_yi,
                pi_yq=pi.pi_yq,
            ),
        )
        for v, pi in results
    ]
    return SweepResponse(channel=body.channel, points=points)
