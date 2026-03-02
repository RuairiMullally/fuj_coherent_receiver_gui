# FIM24725 Services API

Python library for high-level control of the FIM24725 coherent optical receiver module.

This library provides:

- **Safe power sequencing** (automatic bring-up/shutdown)
- **Named rail control** (no PSU/channel confusion)
- **State management** (OFF, STARTING, READY, FAULT)
- **Operating mode control** (AGC/MGC)
- **Bounds enforcement** (automatic clamping to safe ranges)

---

## Quick Start

```python
from fuj_backend.services import FIM24725Service, OperatingMode

# Initialize service with PSU addresses
service = FIM24725Service(
    psu1_ip="192.168.1.10", psu1_port=20001,
    psu2_ip="192.168.1.11", psu2_port=20002,
)

try:
    # Execute startup sequence
    service.startup()

    # Control the device
    service.set_voa(2.4)       # Variable optical attenuator
    service.set_oa_x(1.65)     # Output amplitude X
    service.set_oa_y(1.65)     # Output amplitude Y

    # Pre-stage GA values before switching to MGC
    service.set_ga_x(1.0)      # Takes effect immediately on switch to MGC
    service.set_mode(OperatingMode.MGC)

    # Read status
    snapshot = service.get_snapshot()
    print(f"State: {snapshot.state}")
    print(f"VCC voltage: {snapshot.rails[RailName.VCC_3V3].voltage}V")

finally:
    service.shutdown()
```

### Context Manager Usage

```python
with FIM24725Service(
    psu1_ip="192.168.1.10", psu1_port=20001,
    psu2_ip="192.168.1.11", psu2_port=20002,
) as service:
    service.startup()
    # ... operations ...
# Automatic shutdown and cleanup
```

---

## Library Objects

### `FIM24725Service`

Main entry point for controlling the FIM24725 module.

**Constructor**

```python
FIM24725Service(
    psu1_ip: str,           # IP address of PSU1 (VCC, VPD, VOA)
    psu1_port: int,         # UDP port for PSU1
    psu2_ip: str,           # IP address of PSU2 (GA, OA)
    psu2_port: int,         # UDP port for PSU2
    mcu: MCUInterface = None,  # Optional MCU implementation (defaults to MockMCU)
)
```

**Properties**

```python
state: SystemState          # Current system state
mode: OperatingMode         # Current operating mode (AGC/MGC)
is_ready: bool              # True if system is ready for operation
is_fault: bool              # True if system is in fault state
fault_info: FaultInfo | None  # Fault details if in FAULT state
```

---

## Enums

### `SystemState`

```python
class SystemState(str, Enum):
    OFF = "OFF"                 # System powered off
    STARTING = "STARTING"       # Startup sequence in progress
    READY = "READY"             # Ready for operation
    FAULT = "FAULT"             # Fault detected
    SHUTTING_DOWN = "SHUTTING_DOWN"  # Shutdown in progress
```

### `OperatingMode`

```python
class OperatingMode(str, Enum):
    AGC = "AGC"    # Automatic gain control (FIM24725 ignores GA pins)
    MGC = "MGC"    # Manual gain control (GA pins active)
```

### `RailName`

```python
class RailName(str, Enum):
    VCC_3V3 = "VCC_3V3"      # Amplifier supply (3.3V)
    VPD_5V0 = "VPD_5V0"      # Photodiode supply (5.0V)
    VOA_CTRL = "VOA_CTRL"    # Variable optical attenuator (0-4.8V)
    GA_X = "GA_X"            # Gain adjust X (0-3.3V)
    GA_Y = "GA_Y"            # Gain adjust Y (0-3.3V)
    OA_X = "OA_X"            # Output amplitude X (0.5-2V)
    OA_Y = "OA_Y"            # Output amplitude Y (0.5-2V)
```

### `RailState`

```python
class RailState(str, Enum):
    OFF = "OFF"           # Output disabled
    ENABLED = "ENABLED"   # Output enabled
    FAULT = "FAULT"       # Fault detected
```

---

## Data Structures

### `RailMeasurement`

Measured values for a single rail.

```python
RailMeasurement(
    name: RailName,      # Rail identifier
    voltage: float,      # Measured voltage (V)
    current: float,      # Measured current (A)
    state: RailState,    # Current rail state
    mode: str,           # "CV" or "CC"
)
```

### `PeakIndicators`

Peak indicator readings from the MCU ADC.

```python
PeakIndicators(
    pi_xi: float,   # 0-2V, near 0 = power loss, near 2 = clipping
    pi_xq: float,
    pi_yi: float,
    pi_yq: float,
)
```

### `SystemSnapshot`

Complete system state snapshot.

```python
SystemSnapshot(
    state: SystemState,
    mode: OperatingMode,
    rails: dict[RailName, RailMeasurement],
    sd_enabled: bool,
    peak_indicators: PeakIndicators | None,
    mpd_value: float | None,
    fault_message: str | None,
)
```

### `FaultInfo`

Fault information.

```python
FaultInfo(
    rail: RailName | None,   # Faulted rail, if applicable
    message: str,            # Fault description
    timestamp: float,        # Unix timestamp
    recoverable: bool,       # True if recovery possible
)
```

---

## FIM24725Service Methods

### Lifecycle

#### `startup(mode: OperatingMode = OperatingMode.AGC) -> None`

Execute the full startup sequence:

1. Verify safe initial state (SD=DISABLE, all off)
2. Program OVP/OCP protections
3. Enable VPD_5V0, verify 5.0V (photodiode bias FIRST per app notes)
4. Enable VCC_3V3, verify 3.3V / 280-480mA (amplifier supply SECOND per app notes)
5. Set initial controls (GA=0V, OA=0.5V min, VOA=2.5V)
6. Enable control rail outputs; confirm PSU1 (VOA_CTRL) and PSU2 (GA_X) responsive via VOUT? query
7. Settling delay (500ms)
8. Enable module output (SD=ENABLE)
9. Validate peak indicators

**Raises:**
- `StateError`: If not in OFF state
- `SequenceError`: If any step fails
- `MCUError`: If MCU communication fails
- `VerificationError`: If rail verification fails

```python
service.startup()                      # Default AGC mode
service.startup(OperatingMode.MGC)     # Start in MGC mode
```

#### `shutdown() -> None`

Execute orderly shutdown sequence:

1. SD = DISABLE
2. Return controls to safe values
3. Disable VCC_3V3 (amplifier supply FIRST per app notes)
4. Disable VPD_5V0 (photodiode bias SECOND per app notes)
5. Disable control rails

Safe to call from any state. Does not raise on failure.

```python
service.shutdown()
```

#### `close() -> None`

Clean up resources. Calls `shutdown()` if not already off.

```python
service.close()
```

---

### Rail Control

All control methods require `SystemState.READY`. Values are automatically clamped to safe bounds.

#### `set_voa(volts: float) -> None`

Set Variable Optical Attenuator voltage.

- **Range:** 0-4.8V (clamped)
- **Effect:** Higher voltage = more attenuation
- **Safety:** No hardware damage from high setting

```python
service.set_voa(2.4)  # Set VOA to 2.4V
```

#### `set_oa_x(volts: float) -> None`

Set Output Amplitude X voltage.

- **Range:** 0.5–2V (clamped; app notes AGC mode range)
- **Effect:** Controls final output amplitude for X channel
- **Note:** Does not affect noise profile

```python
service.set_oa_x(1.65)
```

#### `set_oa_y(volts: float) -> None`

Set Output Amplitude Y voltage.

- **Range:** 0.5–2V (clamped; app notes AGC mode range)

```python
service.set_oa_y(1.65)
```

#### `set_ga_x(volts: float) -> None`

Set Gain Adjust X voltage.

- **Range:** 0-3.3V (clamped)
- **Effect:** Controls internal gain, affects noise and output swing
- **AGC mode:** FIM24725 hardware ignores the GA pin, so calling this in AGC
  pre-stages the value — it becomes active the moment the system switches to MGC

```python
# Pre-stage before switching mode
service.set_ga_x(1.0)
service.set_mode(OperatingMode.MGC)

# Or set directly in MGC
service.set_mode(OperatingMode.MGC)
service.set_ga_x(1.0)
```

#### `set_ga_y(volts: float) -> None`

Set Gain Adjust Y voltage.

- **Range:** 0-3.3V (clamped)
- **AGC mode:** Pre-stages value; active on switch to MGC

```python
service.set_ga_y(1.0)
```

---

### Mode Control

#### `set_mode(mode: OperatingMode) -> None`

Switch operating mode between AGC and MGC.

- **AGC:** FIM24725 hardware ignores GA pins (automatic internal control); GA PSU outputs remain at their current voltage, preserving any pre-staged value
- **MGC:** GA pins active for manual gain control; any value pre-staged during AGC takes effect immediately

GA values are **not reset** on mode transitions. This allows pre-staging a GA value in AGC and having it become active the instant the system switches to MGC, with no intervening write required.

```python
service.set_mode(OperatingMode.MGC)
service.set_mode(OperatingMode.AGC)
```

---

### Monitoring

#### `get_snapshot() -> SystemSnapshot`

Get complete system state snapshot including all rail measurements.

```python
snapshot = service.get_snapshot()
print(f"State: {snapshot.state}")
print(f"Mode: {snapshot.mode}")
print(f"VCC: {snapshot.rails[RailName.VCC_3V3].voltage}V")
if snapshot.peak_indicators:
    print(f"PI_XI: {snapshot.peak_indicators.pi_xi}V")
```

#### `read_peak_indicators() -> PeakIndicators`

Read peak indicator values from MCU.

- Values near 0V indicate power loss
- Values near 2V indicate clipping

```python
pi = service.read_peak_indicators()
print(f"PI_XI: {pi.pi_xi}V")
```

#### `read_mpd() -> float`

Read monitor photodiode value.

MPD measures optical input power independent of gain settings.

```python
mpd = service.read_mpd()
print(f"MPD: {mpd}")
```

---

### Advanced Operations

#### `sweep_ga(channel, start, end, step, dwell_ms=100) -> list[tuple[float, PeakIndicators]]`

Sweep GA voltage and record PI at each step (MGC mode only).

**Parameters:**
- `channel`: "X" or "Y"
- `start`: Starting voltage
- `end`: Ending voltage
- `step`: Voltage step size
- `dwell_ms`: Time to wait at each step (ms)

**Returns:** List of (voltage, peak_indicators) tuples

```python
service.set_mode(OperatingMode.MGC)
results = service.sweep_ga("X", start=0.0, end=3.0, step=0.1, dwell_ms=50)
for voltage, pi in results:
    print(f"GA_X={voltage:.2f}V -> PI_XI={pi.pi_xi:.3f}V")
```

---

## Rail Configuration

The `RailRegistry` class provides access to rail configuration.

```python
from fuj_backend.services import RailRegistry, RailName

# Get configuration for a specific rail
config = RailRegistry.get(RailName.VCC_3V3)
print(f"OVP: {config.ovp}V, OCP: {config.ocp}A")

# Access rail categories
print(RailRegistry.POWER_RAILS)    # [VCC_3V3, VPD_5V0]
print(RailRegistry.CONTROL_RAILS)  # [VOA_CTRL, GA_X, GA_Y, OA_X, OA_Y]
print(RailRegistry.GA_RAILS)       # [GA_X, GA_Y]
print(RailRegistry.OA_RAILS)       # [OA_X, OA_Y]
```

### Rail Configuration Table

| Rail | PSU | Ch | Nominal | Max | OVP | OCP |
|------|-----|----|---------| ----|-----|-----|
| VCC_3V3 | PSU1 | 1 | 3.300V | 3.300V | 3.600V | 0.700A |
| VPD_5V0 | PSU1 | 2 | 5.000V | 5.000V | 5.500V | 0.150A |
| VOA_CTRL | PSU1 | 3 | 2.500V | 4.800V | 5.000V | 0.100A |
| GA_X | PSU2 | 1 | 0.000V | 3.300V | 3.600V | 0.020A |
| GA_Y | PSU2 | 2 | 0.000V | 3.300V | 3.600V | 0.020A |
| OA_X | PSU2 | 3 | 0.500V | 2.000V | 3.600V | 0.020A |
| OA_Y | PSU2 | 4 | 0.500V | 2.000V | 3.600V | 0.020A |

---

## MCU Interface

The MCU interface is abstracted via a Protocol for flexibility.

### Using MockMCU (Default)

```python
# MockMCU is used automatically if no MCU is provided
service = FIM24725Service(
    psu1_ip="192.168.1.10", psu1_port=20001,
    psu2_ip="192.168.1.11", psu2_port=20002,
)
```

### Custom MCU Implementation

```python
from fuj_backend.services import MCUInterface, OperatingMode, PeakIndicators

class MySerialMCU:
    """Custom serial MCU implementation."""

    def set_shutdown(self, disable: bool) -> bool:
        # Send command to set SD pin, return confirmed state
        ...

    def set_mode(self, mode: OperatingMode) -> OperatingMode:
        # Send command to set MC/AGC pin, return confirmed mode
        ...

    @property
    def sd_disabled(self) -> bool:
        # Query current SD pin state
        ...

    @property
    def mode(self) -> OperatingMode:
        # Query current MC/AGC mode
        ...

    def read_peak_indicators(self) -> PeakIndicators:
        # Read ADC values
        ...

    def read_mpd(self) -> float:
        # Read MPD value
        ...

    def is_connected(self) -> bool:
        # Check connection
        ...

# Use custom MCU
mcu = MySerialMCU(port="/dev/ttyUSB0")
service = FIM24725Service(
    psu1_ip="192.168.1.10", psu1_port=20001,
    psu2_ip="192.168.1.11", psu2_port=20002,
    mcu=mcu,
)
```

**Set-Confirm Pattern:** The `set_shutdown()` and `set_mode()` methods return
the actual MCU state after applying the command. The service verifies these
return values match the expected state and raises `MCUError` on mismatch.
This ensures the MCU actually applied the requested change before the service
updates its own state machine.

---

## Exceptions

All exceptions inherit from `FIM24725Error`.

### `StateError`

Invalid state transition or operation in current state.

```python
from fuj_backend.services import StateError

try:
    service.set_voa(2.4)  # Fails if not READY
except StateError as e:
    print(f"Invalid state: {e.current_state}")
```

### `RailError`

Rail-related error (base class).

### `BoundsError`

Value out of bounds for rail.

```python
from fuj_backend.services import BoundsError

# Note: By default, values are clamped, not rejected
# BoundsError is raised only when using RailController directly with clamp=False
```

### `VerificationError`

Rail verification failed during startup.

```python
from fuj_backend.services import VerificationError

try:
    service.startup()
except VerificationError as e:
    print(f"Rail {e.rail} failed: expected {e.expected}, got {e.actual}")
```

### `MCUError`

MCU communication error.

```python
from fuj_backend.services import MCUError

try:
    service.startup()
except MCUError as e:
    print(f"MCU error: {e}")
```

### `SequenceError`

Power sequencing error.

---

## State Machine

### Valid State Transitions

```
OFF -> STARTING -> READY -> SHUTTING_DOWN -> OFF
         |           |           |
         v           v           v
       FAULT <------+---------->FAULT
```

### State Descriptions

| State | Description | Allowed Operations |
|-------|-------------|-------------------|
| OFF | System powered off | `startup()` |
| STARTING | Startup in progress | None (wait for completion) |
| READY | Ready for operation | `set_*()`, `get_snapshot()`, `shutdown()` |
| FAULT | Fault detected | `shutdown()` |
| SHUTTING_DOWN | Shutdown in progress | None (wait for completion) |

---

## Logging

The service layer provides automatic file logging with daily rotation.

**Log file:** `logs/fim24725_service.log`

**Rotation:** Daily at midnight, 30-day retention

**Log format:**

```
2026-02-12 10:30:45.123 | fim24725.service | INFO | === Starting FIM24725 Startup Sequence ===
2026-02-12 10:30:45.156 | fim24725.rails | INFO | VCC_3V3: Enabling at 3.300V
2026-02-12 10:30:45.189 | fim24725.state | INFO | State: OFF -> STARTING
```

**Logger hierarchy:**

```
fim24725              # Root service logger
fim24725.service      # FIM24725Service
fim24725.state        # StateMachine
fim24725.rails        # RailController
fim24725.mcu.mock     # MockMCU
```

**Explicit logger setup (optional):**

```python
from fuj_backend.services import setup_service_logger

# Logger is automatically initialized on first use, but can be
# explicitly set up to customize log directory creation timing
logger = setup_service_logger()
```

**Custom configuration:**

```python
import logging

# Adjust log levels
logging.getLogger("fim24725").setLevel(logging.DEBUG)
logging.getLogger("fim24725.rails").setLevel(logging.WARNING)

# Add custom handler
handler = logging.StreamHandler()
logging.getLogger("fim24725").addHandler(handler)
```

**Related logs:**

- PSU HAL logs: `logs/psu_hal.log` (command TX/RX)

---

## Thread Safety

All public methods on `FIM24725Service` are **thread-safe**.

The service uses a reentrant lock (`threading.RLock`) to serialize access:

- All state-modifying operations are protected
- Properties are also protected to ensure consistent reads
- Reentrant locking allows methods to call other methods internally

**Example concurrent usage:**

```python
import threading

service = FIM24725Service(...)
service.startup()

def monitor():
    while True:
        snapshot = service.get_snapshot()  # Thread-safe
        print(f"VCC: {snapshot.rails[RailName.VCC_3V3].voltage}V")
        time.sleep(1)

def control():
    service.set_voa(2.4)  # Thread-safe, will wait for monitor
    service.set_oa_x(1.65)

t1 = threading.Thread(target=monitor)
t2 = threading.Thread(target=control)
t1.start()
t2.start()
```

**Notes:**
- The underlying HAL also serializes PSU commands per device
- Long operations (e.g., `sweep_ga`) hold the lock for the entire duration

---

## Design Rationale

See [ADR-002: FIM24725 Services Layer](adr/ADR-002-services-layer.md) for architectural decisions.

---

## Glossary

- **AGC**: Automatic Gain Control - internal automatic gain adjustment
- **MGC**: Manual Gain Control - user-controlled gain via GA pins
- **GA**: Gain Adjust - controls internal TIA gain
- **OA**: Output Amplitude - controls final output swing
- **VOA**: Variable Optical Attenuator - controls optical input level
- **PI**: Peak Indicator - signals clipping (2V) or power loss (0V)
- **MPD**: Monitor Photodiode - measures optical power independent of gain
- **SD**: Shutdown pin - enables/disables module output
- **TIA**: Transimpedance Amplifier - converts photodiode current to voltage
