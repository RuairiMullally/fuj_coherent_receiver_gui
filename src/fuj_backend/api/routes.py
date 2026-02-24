"""REST API endpoints for FIM24725 coherent receiver control."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.exceptions import FIM24725Error, StateError
from ..services.models import OperatingMode

router = APIRouter(tags=["FIM24725"])


# --- Request / Response schemas ---


class StartupRequest(BaseModel):
    mode: OperatingMode = OperatingMode.AGC


class VoltageRequest(BaseModel):
    volts: float = Field(ge=0.0)


class ModeRequest(BaseModel):
    mode: OperatingMode


# --- Helpers ---


def _get_service(request: Request):
    return request.app.state.service


# --- Endpoints ---


@router.get("/health")
def health(request: Request):
    service = _get_service(request)
    return {
        "status": "ok",
        "state": service.state.value,
        "mode": service.mode.value,
    }


@router.get("/status")
def status(request: Request):
    service = _get_service(request)
    snapshot = service.get_snapshot()
    return snapshot.model_dump()


@router.post("/startup")
def startup(request: Request, body: StartupRequest = StartupRequest()):
    service = _get_service(request)
    try:
        service.startup(mode=body.mode)
        return {"status": "ok"}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
def shutdown(request: Request):
    service = _get_service(request)
    try:
        service.shutdown()
        return {"status": "ok"}
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/voa")
def set_voa(request: Request, body: VoltageRequest):
    service = _get_service(request)
    try:
        service.set_voa(body.volts)
        return {"status": "ok", "volts": body.volts}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/oa/x")
def set_oa_x(request: Request, body: VoltageRequest):
    service = _get_service(request)
    try:
        service.set_oa_x(body.volts)
        return {"status": "ok", "volts": body.volts}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/oa/y")
def set_oa_y(request: Request, body: VoltageRequest):
    service = _get_service(request)
    try:
        service.set_oa_y(body.volts)
        return {"status": "ok", "volts": body.volts}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ga/x")
def set_ga_x(request: Request, body: VoltageRequest):
    service = _get_service(request)
    try:
        service.set_ga_x(body.volts)
        return {"status": "ok", "volts": body.volts}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ga/y")
def set_ga_y(request: Request, body: VoltageRequest):
    service = _get_service(request)
    try:
        service.set_ga_y(body.volts)
        return {"status": "ok", "volts": body.volts}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/mode")
def set_mode(request: Request, body: ModeRequest):
    service = _get_service(request)
    try:
        service.set_mode(body.mode)
        return {"status": "ok", "mode": body.mode.value}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FIM24725Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/peak-indicators")
def peak_indicators(request: Request):
    service = _get_service(request)
    try:
        pi = service.read_peak_indicators()
        return pi.model_dump()
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/mpd")
def mpd(request: Request):
    service = _get_service(request)
    try:
        value = service.read_mpd()
        return {"mpd": value}
    except StateError as e:
        raise HTTPException(status_code=409, detail=str(e))
