# ADR-004: REST API Layer

**Status:** Accepted
**Date:** 2026-02-25
**Authors:** Project Team

---

## Context

The `FIM24725Service` (ADR-002) is a thread-safe Python object providing all device
control operations. A frontend UI (Dash) and any future clients need a well-defined,
network-accessible interface to this service.

### Key requirements

1. **Expose the full service API** — every public method must be reachable over HTTP
2. **Safety** — the service is the source of truth; the API must not bypass service-layer
   safeguards (sequencing, bounds, state machine)
3. **Single service instance** — one `FIM24725Service` is shared across all requests;
   state lives in the service, not the API layer
4. **Startup is explicit** — the device starts in `OFF` state; startup is triggered by
   the user, not automatically on server start
5. **Rate limiting** — protect control endpoints from accidental burst commands
6. **Observability** — API and service logs must be accessible to the UI for debugging
7. **Local deployment** — single-user, trusted LAN only (Raspberry Pi); no auth required

---

## Decision

We implement a **FastAPI REST API** with the following design:

### 1. Application factory pattern

The app is created via a `create_app()` factory, making the entry point:

```bash
uvicorn fuj_backend.api.app:create_app --factory
```

This cleanly separates construction from import, enables testing, and is the standard
pattern for FastAPI lifespan management.

### 2. Lifespan for resource management

All hardware resources (`FIM24725Service`, MCU) are constructed and torn down in a
FastAPI `@asynccontextmanager` lifespan function attached to the app. This guarantees:

- Resources are set up before the first request arrives
- Resources are cleanly released on server shutdown (even on SIGTERM)
- No global state or module-level singletons outside the app factory

The service is stored on `app.state` and injected into routes via `Depends(get_service)`.

### 3. Synchronous route handlers

All route handlers are defined as `def` (not `async def`). FastAPI automatically runs
`def` handlers in its thread pool (anyio). This is the correct approach because:

- `FIM24725Service` uses `threading.RLock` — blocking the async event loop would deadlock
- The thread pool isolates blocking hardware I/O from the event loop
- Concurrent requests serialise naturally at the service lock — no additional locking
  is needed in the API layer

```python
# Thread safety: FIM24725Service uses threading.RLock (@synchronized on all public
# methods). All route handlers are sync `def` — FastAPI runs them in its thread pool.
# Concurrent requests will block at the service lock, serialising hardware access
# automatically. No additional locking is required here.
```

### 4. No service locking in the API layer

The API layer does **not** introduce its own locks, queues, or serialisation. The service
layer is the single authority on thread safety. Adding redundant locking would create
deadlock risk and obscure the true concurrency model.

### 5. pydantic-settings for configuration

A `Settings` class (inheriting `BaseSettings`) loads all configuration from environment
variables with prefix `FUJ_` and optionally from a `.env` file. This enables:

- Zero-code deployment changes (IPs, ports, MCU mode) via environment variables
- Docker-friendly configuration (ENV in Dockerfile or compose file)
- Type validation at startup (wrong types fail immediately, not mid-operation)
- Self-documenting defaults

### 6. Rate limiting via slowapi

[slowapi](https://github.com/laurentS/slowapi) provides decorator-based rate limiting
on top of the `limits` library. Applied at the route level:

```python
@router.post("/startup")
@limiter.limit("10/minute")
def post_startup(request: Request, ...):
    ...
```

A module-level `Limiter` singleton (`api/limiter.py`) is shared across all route
files and registered on `app.state`. This ensures a single consistent limit store.

Rate limits chosen:
- **Control endpoints** (startup/shutdown/mode/set*): 10/minute — prevents accidental
  command bursts while accommodating normal manual operation
- **Status/telemetry**: 120/minute — 2/second, suits a 500 ms UI poll interval
- **Logs**: 30/minute — less frequent; UI updates log panel on user scroll or timer

### 7. Exception → HTTP status mapping

Service exceptions are mapped globally via FastAPI exception handlers registered in
`register_exception_handlers()`. The mapping:

| Exception | HTTP status | Rationale |
|---|---|---|
| `StateError` | 409 Conflict | System is not in the required state — a precondition failed |
| `SequenceError` | 409 Conflict | Same category: sequence precondition not met |
| `BoundsError` | 422 Unprocessable Entity | Input is syntactically valid but semantically out of range |
| `VerificationError` | 502 Bad Gateway | The upstream hardware (PSU) did not apply the setpoint |
| `MCUError` | 502 Bad Gateway | The upstream hardware (MCU) failed to respond |
| `FIM24725Error` | 500 Internal Server Error | Catch-all for unhandled service errors |

All errors return a consistent body `{"detail": "...", "error_type": "ClassName"}`.
Using `error_type` allows the UI to display friendly messages and act differently on
recoverable vs. non-recoverable conditions.

FastAPI's built-in `RequestValidationError` → 422 handler is kept unchanged for Pydantic
input validation errors.

### 8. Separate API and service-layer models

Request/response Pydantic models (`api/models.py`) are defined independently of the
service-layer models (`services/models.py`). This decoupling:

- Allows the API contract to evolve without touching service internals
- Avoids exposing internal fields (e.g. `RailConfig`) that are not relevant to clients
- Permits field renaming or restructuring at the API boundary (e.g. `rails` keyed by
  string rather than `RailName` enum for clean JSON serialisation)

### 9. In-memory log buffer

A custom `logging.Handler` (`LogBufferHandler`) appends structured `LogLine` records
to a bounded `deque(maxlen=500)`. It is attached to the root `fim24725` logger at
startup, capturing output from the service, hardware HAL, and API layers.

The `GET /logs` endpoint exposes this buffer. The UI polls it to populate the debug log
panel. Structured records (`{timestamp, level, logger, message}`) allow the UI to apply
colour coding by log level.

This approach was chosen over:
- **Tailing log files**: Requires filesystem access, polling, and log file path coupling
- **SSE/WebSocket streaming**: Adds persistent connection management complexity; the UI
  is polling everything else anyway (500 ms interval), so consistency favours polling

### 10. Separate API logger

A dedicated `fim24725.api` logger writes to `logs/api.log` (same daily-rotation setup
as the service logger). This provides a separate audit trail for API activity
(request lifecycle, startup/shutdown events) without polluting the service log.

### 11. CORS and host restrictions

CORS is restricted to `localhost`/`127.0.0.1` origins. `TrustedHostMiddleware` limits
accepted `Host` headers to local addresses. These are appropriate for a single-user
local deployment where no external access is intended.

---

## Consequences

### Positive

- **No additional concurrency logic needed**: Service RLock provides full thread safety;
  the API layer is purely a routing/serialisation concern
- **Consistent error contract**: All errors use the same JSON shape, simplifying UI error handling
- **Observable**: Logs are immediately accessible via API without log file access
- **Configuration flexibility**: All deployment parameters are environment variables,
  ready for Docker/compose without code changes
- **Standard patterns**: factory + lifespan + Depends is well-documented FastAPI idiom
- **Interactive docs**: FastAPI auto-generates Swagger UI and ReDoc at `/docs` and `/redoc`

### Trade-offs

- **Synchronous sweep**: `sweep_ga` holds the service lock for its full duration
  (potentially minutes). Other control requests will block, not fail. This is acceptable
  for single-user lab equipment but would need a job queue design for multi-user use.
- **Rate limits are hard-coded in decorators**: The `Settings.rate_*` fields document
  intent but the decorator strings are duplicated. Changing limits requires a code edit.
- **In-memory log buffer is not persistent**: Log lines are lost on server restart.
  The rotating file logs remain; the buffer is for live UI display only.

### Risks mitigated

- **Accidental burst commands**: Rate limiting prevents rapid repeated startup/shutdown
- **Service state bypass**: All control flows through `FIM24725Service` methods;
  no direct PSU or MCU access at the API layer
- **Resource leaks**: Lifespan pattern ensures `service.close()` and MCU teardown
  always execute, even on abnormal shutdown

---

## Alternatives considered

### 1. Async service layer

Rewrite `FIM24725Service` to use `asyncio` locks instead of `threading.RLock`,
enabling fully async route handlers.

**Rejected** because:
- The service, HAL, and MCU layers are all synchronous (socket I/O, serial I/O)
- Wrapping each in `asyncio.to_thread()` internally would add significant complexity
- The `def` handler + thread pool approach achieves the same non-blocking behaviour
  with no changes to existing code
- `threading.RLock` is battle-tested; asyncio locks introduce new failure modes

### 2. WebSocket or SSE for live telemetry

Push PI/MPD telemetry to the UI over a persistent connection instead of polling.

**Rejected** because:
- The Dash UI uses `dcc.Interval` for all other polling (state, rails) — consistency
  favours polling for telemetry too
- A 500 ms polling interval is sufficient for the lab use case
- Persistent connections complicate lifespan management and reconnect logic
- SSE/WebSocket would be a separate endpoint type alongside polling — added complexity
  for no measurable benefit at this scale

### 3. GraphQL

A single `/graphql` endpoint with typed queries.

**Rejected** because:
- Overkill for a fixed, small set of operations on a single device
- No existing GraphQL knowledge on the team
- OpenAPI/Swagger (automatic from FastAPI) provides sufficient documentation

### 4. A single router file

All routes in one file rather than four.

**Rejected** because:
- 13 endpoints across 4 concerns (service control, controls, telemetry, logs) would
  make a single file harder to navigate
- The router-per-concern structure mirrors the service API organisation

---

## References

- [ADR-001: PSU Hardware Abstraction Layer](ADR-001-psu-hal.md)
- [ADR-002: FIM24725 Services Layer](ADR-002-services-layer.md)
- [ADR-003: Arduino MCU](ADR-003-arduino-mcu.md)
- [REST API Documentation](../rest_api.md)
- [FastAPI Lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [slowapi rate limiting](https://github.com/laurentS/slowapi)
