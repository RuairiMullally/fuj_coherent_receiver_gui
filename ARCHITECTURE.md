# FUJ Coherent Receiver GUI - Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Lab Technician (Browser)                        │
│                         Connected via Tailscale                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓ HTTP
┌─────────────────────────────────────────────────────────────────────────┐
│                          DASH FRONTEND (fuj_gui)                        │
│  ┌──────────────────────┐         ┌──────────────────────┐            │
│  │   components/        │         │   callbacks/         │            │
│  │   - controls.py      │         │   - hardware.py      │            │
│  │   - status.py        │    ←──→ │   - startup.py       │            │
│  │   (UI Structure)     │         │   (Event Handlers)   │            │
│  └──────────────────────┘         └──────────────────────┘            │
│                                           ↓                             │
│                              API calls to backend (httpx)              │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓ HTTP REST
┌─────────────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (fuj_backend)                        │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                      API LAYER (api/)                             │ │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────┐              │ │
│  │  │ hardware.py │  │  startup.py  │  │ status.py  │              │ │
│  │  │ PUT /ch/{id}│  │ POST /startup│  │ GET /status│              │ │
│  │  └─────────────┘  └──────────────┘  └────────────┘              │ │
│  │         ↓                 ↓                ↓                      │ │
│  │         └─────────────────┴────────────────┘                      │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              ↓                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                   SERVICES LAYER (services/)                      │ │
│  │                                                                   │ │
│  │  ┌──────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │ │
│  │  │ FIM24725Service  │  │ RailController  │  │  StateMachine   │ │ │
│  │  │                  │  │                 │  │                 │ │ │
│  │  │ • startup()      │  │ • set_voa()     │  │ • state         │ │ │
│  │  │ • shutdown()     │  │ • set_oa_x/y()  │  │ • transitions   │ │ │
│  │  │ • set_mode()     │  │ • set_ga_x/y()  │  │ • fault()       │ │ │
│  │  │ • get_snapshot() │  │ • bounds check  │  │ • callbacks     │ │ │
│  │  └──────────────────┘  └─────────────────┘  └─────────────────┘ │ │
│  │                                                                   │ │
│  │  ┌──────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │ │
│  │  │  RailRegistry    │  │  MCUInterface   │  │     models      │ │ │
│  │  │                  │  │                 │  │                 │ │ │
│  │  │ • VCC_3V3        │  │ • set_shutdown()│  │ • SystemState   │ │ │
│  │  │ • VPD_5V0        │  │ • set_mode()    │  │ • RailName      │ │ │
│  │  │ • VOA_CTRL       │  │ • read_pi()     │  │ • PeakIndicators│ │ │
│  │  │ • GA_X/Y, OA_X/Y │  │ • MockMCU       │  │ • SystemSnapshot│ │ │
│  │  └──────────────────┘  └─────────────────┘  └─────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              ↓                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │              MODELS LAYER (models/)                               │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │  Pydantic Models: ChannelValue, HardwareState, etc.         │ │ │
│  │  │  • Type validation                                           │ │ │
│  │  │  • Schema definitions                                        │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              ↓                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │         HARDWARE ABSTRACTION LAYER (hardware/)                    │ │
│  │                                                                   │ │
│  │  psu_hal.py                                                       │ │
│  │  ┌───────────────────────────────────────────────────────────┐   │ │
│  │  │                                                           │   │ │
│  │  │  ┌─────────────────┐     ┌──────────────────────────┐    │   │ │
│  │  │  │ PsuTransportUDP │     │ MP71050x                 │    │   │ │
│  │  │  │                 │◄────│ (one per physical PSU)   │    │   │ │
│  │  │  │ • write()       │     │                          │    │   │ │
│  │  │  │ • query_raw()   │     │ • identify() → DeviceId  │    │   │ │
│  │  │  │ • query_str()   │     │ • status() → Status      │    │   │ │
│  │  │  │                 │     │ • set_output()            │    │   │ │
│  │  │  │ UDP socket      │     │ • channel(n) → Channel   │    │   │ │
│  │  │  │ per command     │     │ • lock_front_panel()      │    │   │ │
│  │  │  └─────────────────┘     │ • save/recall_profile()  │    │   │ │
│  │  │                          │                          │    │   │ │
│  │  │                          │ threading.Lock per PSU   │    │   │ │
│  │  │                          └────────────┬─────────────┘    │   │ │
│  │  │                                       │ .channel(n)      │   │ │
│  │  │                          ┌────────────▼─────────────┐    │   │ │
│  │  │                          │ Channel                  │    │   │ │
│  │  │                          │ (bound to PSU + ch 1-4)  │    │   │ │
│  │  │                          │                          │    │   │ │
│  │  │                          │ • set_voltage/current    │    │   │ │
│  │  │                          │ • measure_voltage/current│    │   │ │
│  │  │                          │ • output(on/off)         │    │   │ │
│  │  │                          │ • OVP/OCP protections    │    │   │ │
│  │  │                          │ • LIST programming       │    │   │ │
│  │  │                          │ • auto/manual stepping   │    │   │ │
│  │  │                          └──────────────────────────┘    │   │ │
│  │  │                                                           │   │ │
│  │  │  Dataclasses: DeviceId, Status                            │   │ │
│  │  │  Type alias:  Channels = int | Iterable[int] | None       │   │ │
│  │  └───────────────────────────────────────────────────────────┘   │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
                              ↓
                     ┌─────────────────┐
                     │   UDP Socket    │
                     │  port 18190+    │
                     └─────────────────┘
                              ↓
                   ┌──────────────────────┐
                   │ Lab Hardware          │
                   │ Multicomp Pro        │
                   │ MP710508/509 PSU     │
                   └──────────────────────┘
```

## HAL Design Notes

The Hardware Abstraction Layer follows a **synchronous, serialized-per-device** model:

- **One `MP71050x` instance per physical PSU** -- ensures command serialization via `threading.Lock`
- **One `Channel` view per output channel (1-4)** -- bound to its parent PSU, preventing channel/PSU confusion
- **`PsuTransportUDP`** encapsulates all socket operations -- the PSU logic never touches sockets directly
- **UDP transport** with per-command socket creation -- reliable when local port matches PSU device port

The HAL exposes the full command surface but does **not** enforce safety policies. Validation, rate limiting, and operating envelopes are responsibilities of the Services layer above.

For the complete design rationale, see [ADR-001: PSU Hardware Abstraction Layer](docs/adr/ADR-001-psu-hal.md).
For the full API reference, see [PSU HAL API Documentation](docs/psu_hal_api.md).

## Services Layer Design Notes

The Services Layer provides high-level control of the FIM24725 coherent optical receiver:

- **`FIM24725Service`** -- Main facade providing startup/shutdown sequences, named rail control, and state management
- **`RailController`** -- Maps named rails (VCC_3V3, VOA_CTRL, GA_X, etc.) to PSU/channel pairs with bounds enforcement
- **`StateMachine`** -- Enforces valid state transitions (OFF → STARTING → READY → SHUTTING_DOWN)
- **`RailRegistry`** -- Single source of truth for rail configuration (OVP, OCP, bounds)
- **`MCUInterface`** -- Protocol for external MCU communication (MockMCU for development)

The services layer composes HAL objects internally and enforces safety policies that the HAL intentionally omits.

For the complete design rationale, see [ADR-002: FIM24725 Services Layer](docs/adr/ADR-002-services-layer.md).
For the full API reference, see [Services API Documentation](docs/services_api.md).
