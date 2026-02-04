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
│  │  │  state.py        │  │ validation.py   │  │   startup.py    │ │ │
│  │  │                  │  │                 │  │                 │ │ │
│  │  │ • status         │  │ • bounds check  │  │ • initialization│ │ │
│  │  │ • channels {}    │  │ • range limits  │  │ • algorithm     │ │ │
│  │  │ • locks {}       │  │ • safety rules  │  │ • sequencing    │ │ │
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
