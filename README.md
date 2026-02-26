# FUJ Coherent Receiver GUI

Web-based control panel for the FIM24725 coherent optical receiver module.
Controls two programmable PSUs (7 power rails), an Arduino MCU, and displays
live PI / MPD telemetry.

---

## Architecture

Two processes, one port each:

```
Browser → http://127.0.0.1:8050
              ↓
         Dash UI (fuj_gui)
         polling REST API via httpx
              ↓ HTTP
         FastAPI backend (fuj_backend)  → http://127.0.0.1:8000
              ↓
         FIM24725Service  (threading.RLock, state machine)
              ↓
         PSU HAL (UDP)  +  Arduino MCU (serial)
              ↓
         Lab hardware
```

| Component | Description |
|---|---|
| `fuj_gui` | Dash frontend — DARKLY dark theme, 500ms polling |
| `fuj_backend` | FastAPI REST API — rate-limited, exception-mapped |
| `services/` | `FIM24725Service` — sequencing, state machine, thread safety |
| `hardware/` | PSU HAL (UDP) + Arduino MCU (serial / mock) |

---

## Quick start

### Mock hardware (no physical devices)

```bash
pip install -e .

# Terminal 1 — API
FUJ_MCU_MODE=mock FUJ_PSU1_LOCAL_IP="" FUJ_PSU2_LOCAL_IP="" \
  uvicorn fuj_backend.api.app:create_app --factory --port 8000

# Terminal 2 — UI
fuj-gui
```

Open `http://127.0.0.1:8050`.

### Real hardware (Raspberry Pi)

```bash
# Terminal 1 — API
FUJ_MCU_MODE=real \
FUJ_PSU1_IP=10.10.10.137 \
FUJ_PSU2_IP=10.10.20.137 \
  uvicorn fuj_backend.api.app:create_app --factory --host 0.0.0.0 --port 8000

# Terminal 2 — UI
FUJ_GUI_API_BASE_URL=http://localhost:8000 fuj-gui
```

---

## Configuration

### API (`FUJ_` prefix)

| Variable | Default | Description |
|---|---|---|
| `FUJ_PSU1_IP` | `10.10.10.137` | PSU1 IP (VCC, VPD, VOA) |
| `FUJ_PSU2_IP` | `10.10.20.137` | PSU2 IP (GA, OA) |
| `FUJ_PSU1_LOCAL_IP` | `10.10.10.50` | Local NIC for PSU1 (empty = default route) |
| `FUJ_PSU2_LOCAL_IP` | `10.10.20.50` | Local NIC for PSU2 |
| `FUJ_MCU_MODE` | `mock` | `mock` or `real` |
| `FUJ_MCU_PORT` | `/dev/arduino` | Serial port (real mode only) |
| `FUJ_LOG_LEVEL` | `INFO` | Root log level |

### UI (`FUJ_GUI_` prefix)

| Variable | Default | Description |
|---|---|---|
| `FUJ_GUI_API_BASE_URL` | `http://localhost:8000` | Backend URL |
| `FUJ_GUI_GUI_PORT` | `8050` | UI port |
| `FUJ_GUI_POLL_INTERVAL_MS` | `500` | Status / graph refresh (ms) |
| `FUJ_GUI_GRAPH_HISTORY_S` | `60` | Rolling graph window (seconds) |

Both accept a `.env` file in the working directory.

---

## Project structure

```
src/
├── fuj_backend/
│   ├── api/              FastAPI routes, models, exception handlers, rate limiting
│   ├── services/         FIM24725Service, state machine, rail controller, MCU interface
│   ├── hardware/         PSU HAL (UDP), Arduino MCU (serial)
│   └── config.py         pydantic-settings (FUJ_ prefix)
└── fuj_gui/
    ├── app.py            Dash factory + layout + main() entry point
    ├── config.py         GUISettings (FUJ_GUI_ prefix)
    ├── api_client.py     Synchronous httpx wrapper
    ├── callbacks/        status, graph, logs callbacks
    └── components/       header, controls, graph panel, log panel
```

---

## Documentation

| Document | Description |
|---|---|
| [docs/gui.md](docs/gui.md) | Dash UI reference — layout, controls, polling, configuration |
| [docs/rest_api.md](docs/rest_api.md) | REST API reference — all 13 endpoints |
| [docs/services_api.md](docs/services_api.md) | Service layer API reference |
| [docs/arduino_mcu_api.md](docs/arduino_mcu_api.md) | Arduino MCU protocol |
| [docs/psu_hal_api.md](docs/psu_hal_api.md) | PSU HAL API reference |
| [docs/pi_setup.md](docs/pi_setup.md) | Raspberry Pi deployment guide |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detailed system architecture diagram |

### Architecture Decision Records

| ADR | Decision |
|---|---|
| [ADR-001](docs/adr/ADR-001-psu-hal.md) | PSU Hardware Abstraction Layer |
| [ADR-002](docs/adr/ADR-002-services-layer.md) | FIM24725 Services Layer |
| [ADR-003](docs/adr/ADR-003-arduino-mcu.md) | Arduino MCU |
| [ADR-004](docs/adr/ADR-004-rest-api.md) | REST API Layer |

---

## Technology stack

| Layer | Technology |
|---|---|
| UI | Dash 2.18+, dash-bootstrap-components (DARKLY), Plotly |
| API client | httpx |
| Backend | FastAPI, Uvicorn |
| Rate limiting | slowapi |
| Configuration | pydantic-settings |
| Hardware | pyserial (MCU), UDP sockets (PSU) |
| Python | 3.12+ |
