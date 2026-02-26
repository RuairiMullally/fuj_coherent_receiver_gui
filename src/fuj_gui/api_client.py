"""Thin synchronous httpx wrapper for the FIM24725 REST API.

Usage:
    init_client("http://localhost:8000")
    client = get_client()
    status = client.get_status()

All methods return a parsed dict on success, or {"error": "<message>"} on
HTTP error or timeout so that callbacks can display an error toast rather
than raising an unhandled exception.
"""

from __future__ import annotations

import httpx

_client: "APIClient | None" = None


class APIClient:
    def __init__(self, base_url: str, timeout: float = 3.0) -> None:
        self._base = base_url.rstrip("/") + "/api/v1"
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, **params) -> dict:
        try:
            r = httpx.get(f"{self._base}{path}", params=params, timeout=self._timeout)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            return {"error": str(exc)}

    def _post(self, path: str, body: dict | None = None) -> dict:
        try:
            r = httpx.post(
                f"{self._base}{path}",
                json=body,
                timeout=self._timeout,
            )
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Service control
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        return self._get("/status")

    def startup(self, mode: str = "AGC") -> dict:
        return self._post("/startup", {"mode": mode})

    def shutdown(self) -> dict:
        return self._post("/shutdown")

    def set_mode(self, mode: str) -> dict:
        return self._post("/mode", {"mode": mode})

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def set_voa(self, v: float) -> dict:
        return self._post("/controls/voa", {"voltage": v})

    def set_oa_x(self, v: float) -> dict:
        return self._post("/controls/oa_x", {"voltage": v})

    def set_oa_y(self, v: float) -> dict:
        return self._post("/controls/oa_y", {"voltage": v})

    def set_ga_x(self, v: float) -> dict:
        return self._post("/controls/ga_x", {"voltage": v})

    def set_ga_y(self, v: float) -> dict:
        return self._post("/controls/ga_y", {"voltage": v})

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def get_logs(self, n: int = 100) -> dict:
        return self._get("/logs", n=n)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

def init_client(base_url: str, timeout: float = 3.0) -> None:
    global _client
    _client = APIClient(base_url, timeout)


def get_client() -> APIClient:
    if _client is None:
        raise RuntimeError("API client not initialised — call init_client() first")
    return _client
