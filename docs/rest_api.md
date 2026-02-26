# FIM24725 REST API

FastAPI layer that exposes the `FIM24725Service` over HTTP. Intended for
consumption by the Dash UI and any other local client.

---

## Running the server

```bash
# Mock MCU (no hardware required)
FUJ_MCU_MODE=mock uvicorn fuj_backend.api.app:create_app --factory --port 8000

# Real hardware
FUJ_MCU_MODE=real \
FUJ_PSU1_IP=10.10.10.137 \
FUJ_PSU2_IP=10.10.20.137 \
uvicorn fuj_backend.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Interactive documentation (Swagger UI): `http://localhost:8000/docs`

---

## Configuration

All settings are read from environment variables (prefix `FUJ_`) or a `.env` file
in the working directory.

| Variable | Default | Description |
|---|---|---|
| `FUJ_PSU1_IP` | `10.10.10.137` | PSU1 IP address (VCC, VPD, VOA) |
| `FUJ_PSU1_PORT` | `20001` | PSU1 UDP port |
| `FUJ_PSU1_LOCAL_IP` | `10.10.10.50` | Local NIC IP to bind for PSU1 |
| `FUJ_PSU2_IP` | `10.10.20.137` | PSU2 IP address (GA, OA) |
| `FUJ_PSU2_PORT` | `20002` | PSU2 UDP port |
| `FUJ_PSU2_LOCAL_IP` | `10.10.20.50` | Local NIC IP to bind for PSU2 |
| `FUJ_MCU_MODE` | `mock` | `mock` uses `MockMCU`; `real` opens serial port |
| `FUJ_MCU_PORT` | `/dev/arduino` | Serial port (only used when `mcu_mode=real`) |
| `FUJ_API_HOST` | `0.0.0.0` | Uvicorn bind host |
| `FUJ_API_PORT` | `8000` | Uvicorn bind port |
| `FUJ_LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `FUJ_LOG_DIR` | `logs` | Directory for rotating log files |
| `FUJ_RATE_CONTROL` | `10/minute` | Rate limit for control endpoints |
| `FUJ_RATE_STATUS` | `120/minute` | Rate limit for `GET /status` |
| `FUJ_RATE_TELEMETRY` | `120/minute` | Rate limit for telemetry endpoints |
| `FUJ_RATE_LOGS` | `30/minute` | Rate limit for `GET /logs` |

---

## Base URL

All endpoints are under `/api/v1`.

---

## Authentication

None. The API is intended for local network deployment only.
`TrustedHostMiddleware` restricts access to localhost origins.

---

## Rate limiting

Enforced per client IP via [slowapi](https://github.com/laurentS/slowapi).
Exceeded limits return `429 Too Many Requests`.

| Endpoint group | Default limit |
|---|---|
| `POST /startup`, `/shutdown`, `/mode`, all `/controls/*` | 10 per minute |
| `GET /status` | 120 per minute |
| `GET /telemetry/*` | 120 per minute |
| `GET /logs` | 30 per minute |

---

## Concurrency

The service layer serialises all requests via `threading.RLock`. Concurrent API
calls will block (not fail) until the current operation completes. The one exception
is `sweep_ga`, which is long-running — avoid issuing other control commands while a
sweep is in progress.

---

## Common response formats

### Success — control action

```json
{
  "ok": true,
  "state": "READY",
  "message": ""
}
```

### Error

All service-layer errors return a consistent body:

```json
{
  "detail": "Human-readable description of what went wrong",
  "error_type": "ExceptionClassName"
}
```

### HTTP error codes

| Code | Meaning | Typical cause |
|---|---|---|
| `200` | OK | Request succeeded |
| `409` | Conflict | Wrong system state (`StateError`, `SequenceError`) |
| `422` | Unprocessable Entity | Voltage out of bounds (`BoundsError`), bad request body |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected service error |
| `502` | Bad Gateway | PSU or MCU verification failed (`VerificationError`, `MCUError`) |

---

## System states

| State | Meaning |
|---|---|
| `OFF` | Service instantiated; no hardware enabled |
| `STARTING` | Startup sequence in progress |
| `READY` | All hardware enabled and verified; control commands accepted |
| `SHUTTING_DOWN` | Shutdown sequence in progress |
| `FAULT` | An error occurred; hardware has been made safe; call `shutdown()` to return to OFF |

> **Note:** `startup()` is not called automatically on server start. The device starts
> in `OFF` state; the user triggers startup via `POST /startup`.

---

## Endpoints

### Service control

#### `GET /api/v1/status`

Returns a full system snapshot. Safe to call in any state.

**Response** `200`

```json
{
  "state": "READY",
  "mode": "AGC",
  "sd_enabled": true,
  "rails": {
    "VCC_3V3": { "voltage": 3.301, "current": 0.372, "state": "ENABLED", "mode": "CV" },
    "VPD_5V0": { "voltage": 4.999, "current": 0.003, "state": "ENABLED", "mode": "CV" },
    "VOA_CTRL": { "voltage": 2.500, "current": 0.012, "state": "ENABLED", "mode": "CV" },
    "GA_X":    { "voltage": 0.000, "current": 0.000, "state": "ENABLED", "mode": "CV" },
    "GA_Y":    { "voltage": 0.000, "current": 0.000, "state": "ENABLED", "mode": "CV" },
    "OA_X":    { "voltage": 0.000, "current": 0.000, "state": "ENABLED", "mode": "CV" },
    "OA_Y":    { "voltage": 0.000, "current": 0.000, "state": "ENABLED", "mode": "CV" }
  },
  "peak_indicators": {
    "pi_xi": 0.512, "pi_xq": 0.480, "pi_yi": 0.523, "pi_yq": 0.491
  },
  "mpd_value": 0.823,
  "fault": null
}
```

`peak_indicators` and `mpd_value` are `null` when no MCU telemetry has been received yet.
`fault` is non-null only when `state == "FAULT"`:

```json
"fault": {
  "message": "Rail VCC_3V3: Expected 3.135-3.465V, got 3.101V",
  "timestamp": 1740489600.0,
  "recoverable": true
}
```

---

#### `POST /api/v1/startup`

Triggers the full power-on sequence. Requires state `OFF`.

**Request body**

```json
{ "mode": "AGC" }
```

| Field | Type | Default | Description |
|---|---|---|---|
| `mode` | `"AGC"` \| `"MGC"` | `"AGC"` | Initial operating mode |

**Response** `200`

```json
{ "ok": true, "state": "READY", "message": "" }
```

**Errors**

| Code | `error_type` | Condition |
|---|---|---|
| `409` | `StateError` | System is not in `OFF` state |
| `502` | `VerificationError` | PSU voltage verification failed |
| `502` | `MCUError` | MCU handshake failed |

---

#### `POST /api/v1/shutdown`

Triggers the orderly power-down sequence. Safe to call in any state;
always attempts to disable hardware.

**Request body**: none

**Response** `200`

```json
{ "ok": true, "state": "OFF", "message": "" }
```

---

#### `POST /api/v1/mode`

Switches between AGC and MGC modes. Requires state `READY`.

**Request body**

```json
{ "mode": "MGC" }
```

**Response** `200`

```json
{ "ok": true, "state": "READY", "message": "" }
```

**Errors**

| Code | `error_type` | Condition |
|---|---|---|
| `409` | `StateError` | System is not in `READY` state |
| `502` | `MCUError` | MCU mode verification failed |

> **GA pre-staging:** GA values written while in AGC mode are accepted by the PSU and
> applied immediately when the mode switches to MGC. There is no need to set GA values
> after the mode switch.

---

### Controls

All control endpoints require state `READY`. All accept a `VoltageRequest` body
and return an `ActionResponse`.

#### `POST /api/v1/controls/voa`

Set Variable Optical Attenuator control voltage.

| Range | Units |
|---|---|
| 0.0 – 4.8 | V |

```json
{ "voltage": 2.5 }
```

---

#### `POST /api/v1/controls/oa_x`

Set Output Amplitude X.

| Range | Units |
|---|---|
| 0.0 – 3.3 | V |

---

#### `POST /api/v1/controls/oa_y`

Set Output Amplitude Y.

| Range | Units |
|---|---|
| 0.0 – 3.3 | V |

---

#### `POST /api/v1/controls/ga_x`

Set Gain Adjust X.

| Range | Units |
|---|---|
| 0.0 – 3.3 | V |

Safe to call in AGC mode — the FIM24725 ignores GA pins in AGC, but the PSU accepts the
value, pre-staging it for the next MGC session.

---

#### `POST /api/v1/controls/ga_y`

Set Gain Adjust Y.

| Range | Units |
|---|---|
| 0.0 – 3.3 | V |

Same pre-staging behaviour as `ga_x`.

---

#### `POST /api/v1/controls/sweep_ga`

Sweep a GA channel across a voltage range and record PI readings at each step.
Requires MGC mode.

> **Warning:** This is a long-running operation. The service lock is held for the
> entire sweep duration, blocking all other control commands until completion.

**Request body**

```json
{
  "channel": "X",
  "start": 0.0,
  "end": 3.3,
  "step": 0.3,
  "dwell_ms": 200
}
```

| Field | Type | Description |
|---|---|---|
| `channel` | `"X"` \| `"Y"` | Which GA channel to sweep |
| `start` | `float` | Start voltage (V) |
| `end` | `float` | End voltage (V) |
| `step` | `float` | Step size (V) |
| `dwell_ms` | `int` | Time to wait at each step before reading PI (ms). Default: `100` |

**Response** `200`

```json
{
  "channel": "X",
  "points": [
    { "voltage": 0.0,  "pi": { "pi_xi": 0.10, "pi_xq": 0.09, "pi_yi": 0.11, "pi_yq": 0.08 } },
    { "voltage": 0.3,  "pi": { "pi_xi": 0.22, "pi_xq": 0.20, "pi_yi": 0.24, "pi_yq": 0.19 } },
    { "voltage": 3.3,  "pi": { "pi_xi": 1.82, "pi_xq": 1.79, "pi_yi": 1.85, "pi_yq": 1.77 } }
  ]
}
```

**Errors**

| Code | `error_type` | Condition |
|---|---|---|
| `409` | `StateError` | System not in `READY` state |
| `409` | `StateError` | Mode is `AGC` (sweep requires `MGC`) |

---

### Telemetry

Both endpoints query the MCU directly for the freshest reading.
Require state `READY`.

#### `GET /api/v1/telemetry/peak_indicators`

Read all four PI channels (XI, XQ, YI, YQ).

**Response** `200`

```json
{
  "pi_xi": 0.512,
  "pi_xq": 0.480,
  "pi_yi": 0.523,
  "pi_yq": 0.491
}
```

All values are in volts. The FIM24725 outputs 0–2 V; values near 0 V indicate power loss,
values near 2 V indicate clipping.

---

#### `GET /api/v1/telemetry/mpd`

Read the monitor photodiode value.

**Response** `200`

```json
{ "mpd": 0.823 }
```

---

### Logs

#### `GET /api/v1/logs`

Returns recent log lines from the in-memory ring buffer (capacity: 500 lines).
Captures output from all `fim24725.*` loggers (service, hardware, API).

**Query parameters**

| Parameter | Type | Default | Range | Description |
|---|---|---|---|---|
| `n` | `int` | `100` | 1–500 | Number of most-recent lines to return |

**Response** `200`

```json
{
  "lines": [
    {
      "timestamp": "2026-02-25T14:32:01",
      "level": "INFO",
      "logger": "fim24725.service",
      "message": "Step 4: Programming protections for VCC_3V3"
    },
    {
      "timestamp": "2026-02-25T14:32:02",
      "level": "DEBUG",
      "logger": "fim24725.rails",
      "message": "VCC_3V3: Write verified 3.301V ≈ 3.300V"
    }
  ],
  "total_buffered": 47
}
```

`lines` is ordered oldest-first. `total_buffered` is the total number of lines currently
in the buffer (useful for knowing how many lines were dropped).

---

## Data models

### `ServiceStatusResponse`

| Field | Type | Description |
|---|---|---|
| `state` | `SystemState` | `OFF` \| `STARTING` \| `READY` \| `SHUTTING_DOWN` \| `FAULT` |
| `mode` | `OperatingMode` | `AGC` \| `MGC` |
| `sd_enabled` | `bool` | `true` = module enabled (SD LOW) |
| `rails` | `dict[str, RailMeasurementOut]` | Keyed by rail name |
| `peak_indicators` | `PeakIndicatorsOut \| null` | Null if no MCU telemetry received |
| `mpd_value` | `float \| null` | Monitor photodiode, null if unavailable |
| `fault` | `FaultOut \| null` | Non-null only when state is `FAULT` |

### `RailMeasurementOut`

| Field | Type | Description |
|---|---|---|
| `voltage` | `float` | Measured output voltage (V) |
| `current` | `float` | Measured output current (A) |
| `state` | `RailState` | `OFF` \| `ENABLED` \| `FAULT` |
| `mode` | `str` | `"CV"` = constant voltage, `"CC"` = constant current (overloaded) |

### `ActionResponse`

| Field | Type | Description |
|---|---|---|
| `ok` | `bool` | `true` on success |
| `state` | `SystemState` | System state *after* the action |
| `message` | `str` | Optional detail message (usually empty) |

---

## Logging

Two rotating log files are written to the `FUJ_LOG_DIR` directory (default: `logs/`):

| File | Content |
|---|---|
| `fim24725_service.log` | Service layer + hardware (PSU, MCU) |
| `api.log` | API request activity and lifecycle events |

Both rotate daily at midnight with 30-day retention.
Log format: `YYYY-MM-DD HH:MM:SS.mmm | logger | LEVEL | message`

The `GET /logs` endpoint exposes the last 500 lines from `fim24725_service.log` in
structured form for the UI debug panel.
