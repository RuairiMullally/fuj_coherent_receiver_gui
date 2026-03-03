"""Telemetry routes: /telemetry/peak_indicators, /telemetry/mpd.

These endpoints query the MCU directly (rather than using a cached snapshot)
for the freshest available reading.

Thread safety: All handlers are sync `def`. FastAPI runs them in its thread pool.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from fuj_backend.api.deps import get_service
from fuj_backend.api.limiter import limiter
from fuj_backend.api.models import PeakIndicatorsOut
from fuj_backend.services.fim24725_service import FIM24725Service

router = APIRouter()


@router.get("/peak_indicators", response_model=PeakIndicatorsOut)
@limiter.limit("120/minute")
def get_peak_indicators(
    request: Request,
    service: FIM24725Service = Depends(get_service),
) -> PeakIndicatorsOut:
    """Read all four peak indicator channels from the MCU ADC."""
    pi = service.read_peak_indicators()
    return PeakIndicatorsOut(
        pi_xi=pi.pi_xi, pi_xq=pi.pi_xq, pi_yi=pi.pi_yi, pi_yq=pi.pi_yq
    )


@router.get("/mpd")
@limiter.limit("120/minute")
def get_mpd(
    request: Request,
    service: FIM24725Service = Depends(get_service),
) -> dict[str, float]:
    """Read monitor photodiode values from the MCU ADC.

    Returns mpd (differential: MPD+ - MPD-) and mpd_n (MPD- raw).
    """
    return {"mpd": service.read_mpd(), "mpd_n": service.read_mpd_n()}
