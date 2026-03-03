# ADR-002: FIM24725 Services Layer

**Status:** Accepted
**Date:** 2026-02-12
**Authors:** Project Team

---

## Context

The FIM24725 coherent optical receiver module requires coordinated control of:

- **Two programmable PSUs** (7 channels total) providing power rails and analog control signals
- **An external MCU** (Arduino) providing digital control signals (SD, MC/AGC) and ADC readings (PI, MPD)
- **Strict power sequencing** to protect the optical components
- **Operating mode management** (AGC vs MGC)

The existing PSU HAL (ADR-001) provides low-level channel control but does not enforce:

- Safety policies (OVP/OCP sequencing, voltage bounds)
- Power-up/power-down sequences
- State management
- Named rail abstraction (hiding PSU/channel details)

A higher-level abstraction is needed between the HAL and the application/GUI layer.

### Key Constraints

1. **Safety-critical sequencing**: VPD must be enabled before VCC (photodiode bias before amplifier supply — reverse order causes device damage); protections must be programmed before outputs enabled
2. **Mode-dependent behavior**: GA writes always reach the PSU; the FIM24725 hardware ignores GA pins in AGC mode, enabling pre-staging of values before switching to MGC
3. **Fault handling**: Any fault must immediately disable the module (SD = DISABLE)
4. **MCU protocol TBD**: The Arduino communication interface is not yet determined
5. **Library, not API**: This layer is consumed by the FastAPI backend, not exposed directly to clients

---

## Decision

We will implement a **Services Layer** that:

### 1. Provides a Device-Level Facade

A single `FIM24725Service` class encapsulates all device operations:

```python
service = FIM24725Service(
    psu1_ip="192.168.1.10", psu1_port=20001,
    psu2_ip="192.168.1.11", psu2_port=20002,
)
service.startup()
service.set_voa(2.4)
service.shutdown()
```

### 2. Implements Named Rail Abstraction

PSU/channel details are hidden behind meaningful names:

| Rail Name | PSU | Channel | Purpose |
|-----------|-----|---------|---------|
| VCC_3V3 | PSU1 | 1 | Amplifier supply |
| VPD_5V0 | PSU1 | 2 | Photodiode supply |
| VOA_CTRL | PSU1 | 3 | Variable optical attenuator |
| GA_X | PSU2 | 1 | Gain adjust X |
| GA_Y | PSU2 | 2 | Gain adjust Y |
| OA_X | PSU2 | 3 | Output amplitude X |
| OA_Y | PSU2 | 4 | Output amplitude Y |

This mapping is defined once in `RailRegistry` and never duplicated.

### 3. Enforces Safety Policies

- **OVP/OCP before enable**: Protections are always programmed before output is enabled
- **Bounds validation**: All setpoints are clamped to safe ranges
- **Fault triggers shutdown**: State machine automatically calls emergency shutdown on fault
- **Sequence enforcement**: Startup/shutdown follow strict ordering

### 4. Manages System State

A state machine enforces valid transitions:

```
OFF -> STARTING -> READY -> SHUTTING_DOWN -> OFF
         |           |           |
         v           v           v
       FAULT <------+---------->FAULT
```

Operations are gated by state (e.g., `set_voa()` requires READY state).

### 5. Abstracts MCU Communication

The MCU interface is defined as a Protocol, allowing:

- `MockMCU` for development and testing
- Future implementations (Serial, I2C, etc.) without changing the service API

### 6. Composes (Not Inherits) HAL Objects

The service creates and owns HAL objects internally:

```
FIM24725Service
    ├── PsuTransportUDP (x2)
    ├── MP71050x (x2)
    ├── RailController
    ├── StateMachine
    └── MCUInterface
```

This keeps the HAL unchanged and allows independent testing.

### 7. Thread Safety

All public methods are protected by a reentrant lock (`threading.RLock`):

- Prevents race conditions between concurrent callers
- Ensures state consistency during multi-step operations
- Uses `RLock` to allow internal method calls (e.g., shutdown calling emergency_shutdown)
- Properties are also protected for consistent reads

### 8. Logging

Dedicated file logging with daily rotation:

- Log file: `logs/fim24725_service.log`
- Logger hierarchy: `fim24725.*` (service, state, rails, mcu)
- Automatic setup on first service instantiation
- 30-day retention matching HAL logs

### 9. Module Structure

```
src/fuj_backend/services/
    __init__.py           # Public exports
    exceptions.py         # Service-specific exceptions
    logging.py            # File logging setup
    models.py             # Pydantic data models
    rail_config.py        # Rail registry
    mcu_interface.py      # MCU Protocol + MockMCU
    state_machine.py      # State management
    rail_controller.py    # Named rail control
    fim24725_service.py   # Main facade
```

---

## Consequences

### Positive

- **Clear separation of concerns**: HAL handles communication, services handle policy
- **Single source of truth**: Rail configuration defined once in `RailRegistry`
- **Safe by default**: Bounds clamping, sequencing, and fault handling are automatic
- **Thread-safe**: All public methods protected by RLock for concurrent access
- **Auditable**: Dedicated file logging with rotation for debugging and compliance
- **Testable**: MockMCU and composition pattern enable unit testing without hardware
- **Extensible**: MCU Protocol allows adding communication backends without API changes
- **Type-safe**: Pydantic models provide validation and serialization

### Trade-offs

- **Additional layer**: Adds complexity between HAL and API
- **Mock-dependent testing**: Full integration tests require real hardware
- **Synchronous design**: Inherited from HAL; async wrappers may be needed for GUI responsiveness
- **Lock contention**: Thread safety adds overhead; long operations block other threads

### Risks Mitigated

- **Electrical damage**: Sequencing and protection programming enforced
- **Software state drift**: State machine tracks actual system state
- **PSU/channel confusion**: Named rails eliminate manual mapping

---

## Alternatives Considered

### 1. Extend HAL with Safety Logic

Rejected because:
- Violates single responsibility (HAL = communication, not policy)
- Makes HAL harder to test independently
- Couples PSU control to FIM24725-specific requirements

### 2. Stateless Service Functions

Rejected because:
- No enforcement of sequencing between calls
- Caller must track state externally
- Fault handling becomes caller's responsibility

### 3. Direct MCU Protocol Implementation

Rejected because:
- Protocol is TBD; would require rework
- Protocol abstraction allows development to proceed in parallel

---

## Future Considerations

1. **Async wrappers**: `asyncio.to_thread()` wrappers for non-blocking GUI integration
2. **Real MCU implementation**: Serial or I2C backend when protocol is finalized
3. **Telemetry/logging**: Structured logging for debugging and auditing
4. **Configuration file**: External YAML/JSON for rail parameters (currently hardcoded)
5. **Health monitoring**: Background task to periodically verify rail states

---

## References

- [ADR-001: PSU Hardware Abstraction Layer](ADR-001-psu-hal.md)
- [FIM24725 Control Schema](../../service_layer_README.md)
- [Services API Documentation](../services_api.md)
