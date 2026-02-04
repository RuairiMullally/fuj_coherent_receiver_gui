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
│  │         ┌─────────────────────────────────────┐                  │ │
│  │         │   HardwareInterface (ABC)           │                  │ │
│  │         │   • initialize()                    │                  │ │
│  │         │   • write_channel()                 │                  │ │
│  │         │   • read_channel()                  │                  │ │
│  │         │   • get_status()                    │                  │ │
│  │         │   • shutdown()                      │                  │ │
│  │         └─────────────────────────────────────┘                  │ │
│  │                         ↑                                         │ │
│  │         ┌───────────────┼───────────────┐                        │ │
│  │         │               │               │                        │ │
│  │    ┌────────┐    ┌─────────────┐  ┌──────────┐                 │ │
│  │    │Simulator│   │EthernetDriver│  │DaemonDriver│               │ │
│  │    │Driver   │   │              │  │ (optional)│                │ │
│  │    └────────┘    └─────────────┘  └──────────┘                 │ │
│  │         ↓               ↓               ↓                        │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
              ↓                ↓               ↓
     ┌────────────┐   ┌─────────────┐   ┌──────────────┐
     │In-Memory   │   │Raw Ethernet │   │HTTP to Daemon│
     │Simulation  │   │TCP Socket   │   │Process       │
     └────────────┘   └─────────────┘   └──────────────┘
                             ↓
                    ┌──────────────────┐
                    │ Lab Hardware     │
                    │ (Coherent RX)    │
                    └──────────────────┘
```

---

## Hardware Abstraction Layer (HAL) Pattern

### The Problem We're Solving

We need to control hardware, but the communication method might change:
- **Development**: Use simulator (no hardware needed)
- **Production Option A**: Direct Ethernet communication
- **Production Option B**: Separate daemon process
- **Future**: USB, Serial, or other protocols

### The Solution: Abstract Interface

```
                    ┌─────────────────────────────┐
                    │    Backend Code             │
                    │    (API, Services)          │
                    │                             │
                    │    hw.write_channel(1, 0.5) │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   HardwareInterface (ABC)   │
                    │   ┌─────────────────────┐   │
                    │   │ Abstract Methods:   │   │
                    │   │ • initialize()      │   │
                    │   │ • write_channel()   │   │
                    │   │ • read_channel()    │   │
                    │   │ • get_status()      │   │
                    │   │ • shutdown()        │   │
                    │   └─────────────────────┘   │
                    └──────────────┬──────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│SimulatorDriver  │    │ EthernetDriver      │    │ DaemonDriver     │
│                 │    │                     │    │                  │
│ • Fake channels │    │ • TCP socket        │    │ • HTTP client    │
│ • Instant reply │    │ • Protocol encoding │    │ • REST API calls │
│ • No hardware   │    │ • Async I/O         │    │ • IPC            │
└─────────────────┘    └─────────────────────┘    └──────────────────┘
         │                         │                         │
         ▼                         ▼                         ▼
   ┌─────────┐          ┌──────────────────┐      ┌──────────────────┐
   │In-Memory│          │  192.168.1.100   │      │  localhost:9000  │
   │ Dict    │          │  Port 5000       │      │  Daemon Process  │
   └─────────┘          │  (Lab Hardware)  │      └──────────────────┘
                        └──────────────────┘
```

---

## Configuration-Based Driver Selection

### At Startup

```
┌──────────────────────────────────────────────────────────┐
│  1. Load Configuration                                   │
│     (environment vars, .env file, config.py)            │
│                                                          │
│     HARDWARE_MODE=simulator     ← Development           │
│     HARDWARE_MODE=ethernet      ← Production            │
│     HARDWARE_MODE=daemon        ← Alternative           │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│  2. Hardware Factory                                     │
│     (hardware/factory.py)                               │
│                                                          │
│     def create_hardware_driver(config):                 │
│         if config.mode == "simulator":                  │
│             return SimulatorDriver()                    │
│         elif config.mode == "ethernet":                 │
│             return EthernetDriver(host, port)           │
│         elif config.mode == "daemon":                   │
│             return DaemonDriver(url)                    │
└────────────────────┬─────────────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────────────┐
│  3. Inject Into Application                              │
│                                                          │
│     app.state.hw_driver = create_hardware_driver(config) │
│                                                          │
│     ← Backend code only sees HardwareInterface          │
│     ← Actual implementation is hidden                   │
└──────────────────────────────────────────────────────────┘
```

---

## Request Flow: User Updates Channel Value

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. USER ACTION                                                      │
│    Lab technician moves slider in browser                           │
│    Channel 3: 0.750                                                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. DASH CALLBACK (frontend)                                         │
│    callbacks/hardware.py                                            │
│    • Callback triggered by slider Input                             │
│    • Makes HTTP PUT request to backend                              │
│    • PUT /api/channels/3 {"value": 0.750}                          │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. API ENDPOINT (backend)                                           │
│    api/hardware.py: update_channel()                                │
│    ✓ Receive request                                                │
│    ✓ Parse with Pydantic model                                      │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. STATE CHECK (services)                                           │
│    services/state.py                                                │
│    • Check: Is hardware status == "READY"?                          │
│    • If not: Return HTTP 400 "Hardware not ready"                   │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼ (status is READY)
┌─────────────────────────────────────────────────────────────────────┐
│ 5. VALIDATION (services)                                            │
│    services/validation.py                                           │
│    • Check: Is 0.750 within bounds for channel 3?                   │
│    • Check: Safety limits, rate limits, etc.                        │
│    • If invalid: Return HTTP 400 "Out of bounds"                    │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼ (validation passed)
┌─────────────────────────────────────────────────────────────────────┐
│ 6. ACQUIRE LOCK (services)                                          │
│    services/state.py                                                │
│    • Acquire async lock for channel 3                               │
│    • Prevents concurrent writes to same channel                     │
│    • Block if another request is updating channel 3                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼ (lock acquired)
┌─────────────────────────────────────────────────────────────────────┐
│ 7. HARDWARE WRITE (HAL)                                             │
│    hardware/interface.py → [Concrete Driver]                        │
│                                                                     │
│    success = await hw_driver.write_channel(3, 0.750)                │
│                                                                     │
│    ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │
│    │ SimulatorDriver │  │ EthernetDriver   │  │ DaemonDriver    │ │
│    │                 │  │                  │  │                 │ │
│    │ • Update dict   │  │ • Send TCP cmd   │  │ • HTTP POST     │ │
│    │ • Return True   │  │ • Wait for ACK   │  │ • Wait response │ │
│    │ (instant)       │  │ • Return result  │  │ • Return result │ │
│    └─────────────────┘  └──────────────────┘  └─────────────────┘ │
│                                                                     │
│    ← SYNCHRONOUS: Wait for hardware confirmation                    │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼ (write confirmed)
┌─────────────────────────────────────────────────────────────────────┐
│ 8. UPDATE STATE (services)                                          │
│    services/state.py                                                │
│    • Update in-memory state: channels[3] = 0.750                    │
│    • Release lock for channel 3                                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 9. RETURN SUCCESS (backend → frontend)                              │
│    Return HTTP 200 {"channel_id": 3, "value": 0.750}               │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 10. UPDATE UI (frontend)                                            │
│     Callback updates value display: "0.750"                         │
│     User sees confirmation                                          │
└─────────────────────────────────────────────────────────────────────┘

Total time: ~50ms (simulator) or ~200ms (real hardware)
```

---

## Startup Sequence Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. USER CLICKS "START HARDWARE" BUTTON                              │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. DASH CALLBACK                                                    │
│    POST /api/startup                                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. CHECK CURRENT STATE                                              │
│    if state.status != "OFFLINE":                                    │
│        return error "Already started"                               │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. SET STATUS = "STARTING"                                          │
│    state.status = "STARTING"                                        │
│    (UI shows "Hardware: STARTING", disables controls)               │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. RUN STARTUP ALGORITHM                                            │
│    services/startup.py                                              │
│                                                                     │
│    async def run_startup_sequence():                                │
│        # Step 1: Connect to hardware                                │
│        await hw_driver.initialize()                                 │
│                                                                     │
│        # Step 2: Run calibration                                    │
│        await hw_driver.calibrate()                                  │
│                                                                     │
│        # Step 3: Set safe defaults                                  │
│        for ch in range(8):                                          │
│            await hw_driver.write_channel(ch, 0.0)                   │
│                                                                     │
│        # Step 4: Verify readiness                                   │
│        status = await hw_driver.get_status()                        │
│        return status == "READY"                                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
                        ┌───────┴────────┐
                        │                │
                   ┌────▼─────┐    ┌─────▼─────┐
                   │ SUCCESS  │    │  FAILURE  │
                   └────┬─────┘    └─────┬─────┘
                        │                │
         ┌──────────────▼────┐    ┌──────▼──────────────┐
         │ 6a. SET READY     │    │ 6b. SET ERROR       │
         │ status = "READY"  │    │ status = "ERROR"    │
         │ Enable controls   │    │ Show error message  │
         └───────────────────┘    └─────────────────────┘
```

---

## File Organization

```
src/
├── fuj_backend/
│   ├── api/                    # FastAPI endpoints (thin orchestration)
│   │   ├── __init__.py
│   │   ├── hardware.py         # PUT /channels/{id}, GET /channels
│   │   ├── startup.py          # POST /startup, POST /shutdown
│   │   └── status.py           # GET /status, GET /health
│   │
│   ├── models/                 # Pydantic models (data schemas)
│   │   ├── __init__.py
│   │   ├── hardware.py         # ChannelValue, HardwareState
│   │   └── validation.py       # ValidationBounds, SafetyLimits
│   │
│   ├── services/               # Business logic
│   │   ├── __init__.py
│   │   ├── state.py            # StateManager (in-memory state + locks)
│   │   ├── validation.py       # ValidationService (bounds checking)
│   │   └── startup.py          # StartupService (initialization algorithm)
│   │
│   ├── hardware/               # Hardware Abstraction Layer
│   │   ├── __init__.py
│   │   ├── interface.py        # HardwareInterface (ABC)
│   │   ├── factory.py          # create_hardware_driver()
│   │   ├── simulator.py        # SimulatorDriver
│   │   ├── ethernet_driver.py  # EthernetDriver (real hardware)
│   │   └── daemon_driver.py    # DaemonDriver (optional)
│   │
│   ├── config.py               # Settings (Pydantic BaseSettings)
│   └── main.py                 # FastAPI app + startup
│
└── fuj_gui/
    ├── components/             # UI components (layout)
    │   ├── __init__.py
    │   ├── controls.py         # Channel sliders, inputs
    │   └── status.py           # Status display, startup button
    │
    ├── callbacks/              # Dash callbacks (interactivity)
    │   ├── __init__.py
    │   ├── hardware.py         # Channel update callbacks
    │   └── startup.py          # Startup/shutdown callbacks
    │
    ├── app.py                  # Dash app factory
    └── layout.py               # Main page layout
```

---

## Key Design Principles

### 1. Single Process Architecture
- FastAPI and Dash run in one process
- HAL drivers run in-process (no separate daemon by default)
- Simpler deployment, easier debugging

### 2. Hardware Abstraction
- Backend code never imports concrete drivers directly
- Only depends on `HardwareInterface`
- Swap implementations via configuration

### 3. Separation of Concerns
- **Models**: Data structure only
- **Services**: Business logic (state, validation, algorithms)
- **Hardware**: External communication only
- **API**: Thin orchestration layer

### 4. Synchronous Hardware Operations
- Wait for confirmation before responding
- Prevents optimistic updates on expensive hardware
- User gets definitive success/failure

### 5. Per-Parameter Locking
- Async locks prevent race conditions
- One write at a time per channel
- Different channels can be updated concurrently

---

## Environment Configuration Examples

### Development (Simulator)
```bash
HARDWARE_MODE=simulator
DEBUG=true
```

### Production (Ethernet)
```bash
HARDWARE_MODE=ethernet
HARDWARE_HOST=192.168.1.100
HARDWARE_PORT=5000
DEBUG=false
```

### Alternative (Daemon)
```bash
HARDWARE_MODE=daemon
DAEMON_URL=http://localhost:9000
DEBUG=false
```

---

## Benefits of This Architecture

✅ **Flexibility**: Change hardware communication without touching backend code
✅ **Testability**: Use simulator for development and testing
✅ **Type Safety**: Abstract interface guarantees all drivers have same methods
✅ **Simplicity**: Single process, no daemon management (unless you want it)
✅ **Safety**: Synchronous writes + per-parameter locks prevent issues
✅ **Maintainability**: Clear separation of concerns
