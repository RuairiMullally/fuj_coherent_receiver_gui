# Arduino MCU API (`ArduinoMCU`)

Python class for controlling the FIM24725 coherent receiver MCU signals via an OSEPP Arduino
Uno R3 connected over USB serial.

The class implements the `MCUInterface` Protocol defined in the services layer, providing:
- **Digital output:** SD (shutdown) and MC/AGC (gain mode) control signals
- **Analog input:** Peak Indicator and Monitor Photodiode readings via Arduino ADC

---

## Quick start

```python
from fuj_backend.hardware import ArduinoMCU
from fuj_backend.services import FIM24725Service

with ArduinoMCU("/dev/arduino") as mcu:
    with FIM24725Service(
        psu1_ip="10.10.10.137", psu1_port=20001, psu1_local_ip="10.10.10.50",
        psu2_ip="10.10.10.138", psu2_port=20002, psu2_local_ip="10.10.10.51",
        mcu=mcu,
    ) as service:
        service.startup()
        service.set_voa(2.4)
        service.set_oa_x(1.65)
        service.shutdown()
```

---

## Hardware

### Pin assignments

| Signal  | Arduino Pin | Direction     | Logic                             | Voltage Range |
|---------|-------------|---------------|-----------------------------------|---------------|
| SD      | D2          | Digital out   | HIGH = module disabled (safe)     | 0 / 5V        |
| MC/AGC  | D3          | Digital out   | HIGH = AGC, LOW = MGC             | 0 / 5V        |
| PI_XI   | A0          | ADC input     | Peak Indicator X-I                | 0–2V          |
| PI_XQ   | A1          | ADC input     | Peak Indicator X-Q                | 0–2V          |
| PI_YI   | A2          | ADC input     | Peak Indicator Y-I                | 0–2V          |
| PI_YQ   | A3          | ADC input     | Peak Indicator Y-Q                | 0–2V          |
| MPD     | A4          | ADC input     | Monitor Photodiode                | 0–2V          |

**Safe state:** D2 and D3 are set HIGH during `setup()` before enabling outputs. This
ensures SD=disabled and MODE=AGC at all times during Arduino boot, with no glitch.

**ADC conversion:** `voltage = (analogRead(pin) / 1024.0) × 5.0`
Default AREF = VCC = 5V. Gives ~4.9 mV/count; signals use ~40% of ADC range (0–2V).

---

## `ArduinoMCU` class

### Constructor

```python
ArduinoMCU(
    port: str = "/dev/arduino",
    baud: int = 115200,
    timeout: float = 2.0,
)
```

Opens the serial connection, waits for the Arduino to boot, and blocks until the Arduino
sends its `INIT:` startup message.

**Parameters**

| Parameter | Default           | Description |
|-----------|-------------------|-------------|
| `port`    | `"/dev/arduino"`  | Serial device path. `/dev/arduino` is created by udev on the Pi for FTDI FT232R (VID `0403`, PID `6001`). |
| `baud`    | `115200`          | Baud rate — must match firmware (`115200` hardcoded). |
| `timeout` | `2.0`             | Seconds to wait for command responses and the `INIT:` startup message. |

**Raises**

- `MCUError` — If `INIT:` is not received within `timeout` seconds. Indicates wrong firmware, missing sketch, or hardware fault.
- `serial.SerialException` — If the serial port cannot be opened (device not present, permission denied, etc.).

**Startup sequence**

1. Opens `serial.Serial(port, 115200, timeout=0.1)`
2. Sleeps 2s for Arduino reset-on-DTR to complete
3. Clears the input buffer
4. Starts background reader thread (`arduino-reader`, daemon)
5. Waits for `INIT:SD=1,MODE=AGC` from Arduino (up to `timeout` seconds)
6. On timeout: calls `close()`, raises `MCUError`

**Class constants**

| Constant          | Value | Description |
|-------------------|-------|-------------|
| `BAUD`            | `115200` | Default baud rate |
| `BOOT_DELAY_S`    | `2.0` | Seconds to wait after DTR reset |
| `READ_TIMEOUT_S`  | `0.1` | `serial.readline()` timeout inside reader thread |

---

### Methods

#### `set_shutdown(disable: bool) -> bool`

Sets the SD (Shutdown) pin on the FIM24725.

```python
mcu.set_shutdown(True)   # SD HIGH — module disabled (safe state)
mcu.set_shutdown(False)  # SD LOW  — module enabled
```

Sends `SD:1` or `SD:0` to the Arduino. The Arduino applies the pin and verifies with
`digitalRead()` before echoing the applied state. Updates the `sd_disabled` cache.

**Returns:** `True` if SD is now HIGH (module disabled), `False` if LOW (enabled).

**Raises:** `MCUError` on communication failure, timeout, or `ERR:PIN_FAULT:SD` from Arduino.

---

#### `set_mode(mode: OperatingMode) -> OperatingMode`

Sets the MC/AGC gain control mode.

```python
from fuj_backend.services import OperatingMode

mcu.set_mode(OperatingMode.AGC)   # MC/AGC HIGH
mcu.set_mode(OperatingMode.MGC)   # MC/AGC LOW
```

Sends `MODE:AGC` or `MODE:MGC`. The Arduino echoes the applied mode. Updates the `mode` cache.

**Returns:** The `OperatingMode` confirmed by the Arduino.

**Raises:** `MCUError` on communication failure, timeout, or `ERR:PIN_FAULT:MODE` from Arduino.

---

#### `read_peak_indicators() -> PeakIndicators`

Returns the latest Peak Indicator readings from the telemetry cache.

```python
pi = mcu.read_peak_indicators()
print(pi.pi_xi, pi.pi_xq, pi.pi_yi, pi.pi_yq)  # voltages 0–2V
```

Readings are updated autonomously every 500ms by the background reader thread.

**Returns:** `PeakIndicators` with `pi_xi`, `pi_xq`, `pi_yi`, `pi_yq` fields (each 0–2V float).

**Raises:** `MCUError` if no telemetry has been received yet (immediately after construction,
before the first 500ms telemetry arrives).

---

#### `read_mpd() -> float`

Returns the latest Monitor Photodiode reading from the telemetry cache.

```python
mpd = mcu.read_mpd()   # 0–2V float
```

Updated every 500ms alongside the Peak Indicators.

**Returns:** MPD voltage as a float, 0–2V.

**Raises:** `MCUError` if no telemetry has been received yet.

---

#### `is_connected() -> bool`

Sends `PING` and checks for `PONG` response.

```python
if mcu.is_connected():
    print("Arduino is responsive")
```

**Returns:** `True` if `PONG` is received within `timeout` seconds. `False` on timeout,
serial error, or if `_connected` is already `False` (set by reader thread on fault).

Does not raise; all errors are swallowed and return `False`.

---

#### `close() -> None`

Stops the reader thread and closes the serial port.

```python
mcu.close()
```

Safe to call multiple times. Called automatically by `__exit__` when used as a context manager.

---

### Properties

#### `sd_disabled: bool` (read-only)

Cached SD pin state. `True` = SD HIGH (module disabled), `False` = SD LOW (module enabled).

Initialised to `True` at construction (matches Arduino `setup()` initial state). Updated by `set_shutdown()`.

```python
if mcu.sd_disabled:
    print("Module is disabled")
```

---

#### `mode: OperatingMode` (read-only)

Cached MC/AGC pin state. `OperatingMode.AGC` or `OperatingMode.MGC`.

Initialised to `OperatingMode.AGC` at construction. Updated by `set_mode()`.

```python
print(mcu.mode)  # OperatingMode.AGC
```

---

### Context manager support

`ArduinoMCU` supports the `with` statement for automatic cleanup:

```python
with ArduinoMCU("/dev/arduino") as mcu:
    # mcu is connected and initialised
    print(mcu.is_connected())
# mcu.close() called automatically here
```

---

## Data structures

### `PeakIndicators`

Return type of `read_peak_indicators()`.

```python
PeakIndicators(
    pi_xi: float,   # Peak Indicator X-I, 0–2V
    pi_xq: float,   # Peak Indicator X-Q, 0–2V
    pi_yi: float,   # Peak Indicator Y-I, 0–2V
    pi_yq: float,   # Peak Indicator Y-Q, 0–2V
)
```

### `OperatingMode`

```python
class OperatingMode(str, Enum):
    AGC = "AGC"   # Automatic Gain Control — MC/AGC pin HIGH
    MGC = "MGC"   # Manual Gain Control   — MC/AGC pin LOW
```

---

## Serial protocol

All messages are ASCII, `\n`-terminated, 115200 baud, 8N1.

### Commands (Host → Arduino)

| Command    | Effect                                    | Response (success)      | Response (fault)        |
|------------|-------------------------------------------|-------------------------|-------------------------|
| `PING`     | Connectivity check                        | `PONG`                  | —                       |
| `SD:1`     | Set SD HIGH (module disabled)             | `SD:1`                  | `ERR:PIN_FAULT:SD`      |
| `SD:0`     | Set SD LOW (module enabled)               | `SD:0`                  | `ERR:PIN_FAULT:SD`      |
| `MODE:AGC` | Set MC/AGC HIGH (AGC mode)                | `MODE:AGC`              | `ERR:PIN_FAULT:MODE`    |
| `MODE:MGC` | Set MC/AGC LOW (MGC mode)                 | `MODE:MGC`              | `ERR:PIN_FAULT:MODE`    |
| *(unknown)*| —                                         | —                       | `ERR:UNKNOWN:<cmd>`     |

### Unsolicited messages (Arduino → Host)

| Message | When | Format |
|---------|------|--------|
| `INIT:SD=1,MODE=AGC` | Once, at Arduino startup | Fixed string |
| `TELE:...` | Every 500ms | See Telemetry format below |

### Telemetry format

```
TELE:PI_XI=x.xxx,PI_XQ=x.xxx,PI_YI=x.xxx,PI_YQ=x.xxx,MPD=x.xxx
```

All voltages are 3 decimal places. Example:

```
TELE:PI_XI=1.234,PI_XQ=0.876,PI_YI=1.543,PI_YQ=0.234,MPD=0.567
```

### Error messages (Arduino → Host)

| Message               | Cause |
|-----------------------|-------|
| `ERR:PIN_FAULT:SD`    | `digitalRead(D2)` did not match after `digitalWrite(D2, ...)` |
| `ERR:PIN_FAULT:MODE`  | `digitalRead(D3)` did not match after `digitalWrite(D3, ...)` |
| `ERR:UNKNOWN:<cmd>`   | Command not recognised by firmware |

`ERR:` responses cause `_send_command()` to raise `MCUError("Arduino error: ERR:...")`.

---

## Execution model

- All public methods are **synchronous and blocking** (wait for command echo or raise on timeout).
- The **background reader thread** runs continuously, routing telemetry to the internal cache and command responses to an internal queue. It is transparent to callers.
- `read_peak_indicators()` and `read_mpd()` are **non-blocking** — they return the cached value from the last telemetry frame without sending a command.
- **Thread safety:** Telemetry cache reads/writes are protected by `_tele_lock`. The response queue is `queue.Queue` (thread-safe). Concurrent callers to command methods will interleave — external locking is recommended if calling from multiple threads (the `FIM24725Service` `RLock` provides this in normal use).

---

## Logging

All serial traffic and internal events are logged via the `fim24725` logger hierarchy.

**Logger name:** `fim24725.mcu.arduino`

**Log location:** `logs/fim24725_service.log` (set up by `FIM24725Service` on construction)

**Typical entries:**

```
INFO  fim24725.mcu.arduino  Connecting to Arduino on /dev/arduino at 115200 baud
DEBUG fim24725.mcu.arduino  Waiting 2.0s for Arduino reset
INFO  fim24725.mcu.arduino  Arduino startup: INIT:SD=1,MODE=AGC
INFO  fim24725.mcu.arduino  Arduino connected and initialised
DEBUG fim24725.mcu.arduino  TX: SD:0
DEBUG fim24725.mcu.arduino  RX: SD:0
DEBUG fim24725.mcu.arduino  RX: TELE:PI_XI=1.234,PI_XQ=0.876,...
INFO  fim24725.mcu.arduino  Arduino disconnected
```

To use the logger before attaching a `FIM24725Service`, call `setup_service_logger()` first:

```python
from fuj_backend.services import setup_service_logger
setup_service_logger()
```

---

## Examples

### Example: Standalone connectivity check

```python
from fuj_backend.services import setup_service_logger
from fuj_backend.hardware import ArduinoMCU

setup_service_logger()

with ArduinoMCU("/dev/arduino") as mcu:
    print("Connected:", mcu.is_connected())
    print("SD disabled:", mcu.sd_disabled)
    print("Mode:", mcu.mode)
```

### Example: Read telemetry

```python
import time
from fuj_backend.hardware import ArduinoMCU

with ArduinoMCU("/dev/arduino") as mcu:
    time.sleep(0.6)  # Wait for at least one telemetry frame
    pi = mcu.read_peak_indicators()
    mpd = mcu.read_mpd()
    print(f"PI_XI={pi.pi_xi:.3f} PI_XQ={pi.pi_xq:.3f}")
    print(f"PI_YI={pi.pi_yi:.3f} PI_YQ={pi.pi_yq:.3f}")
    print(f"MPD={mpd:.3f}")
```

### Example: Use with FIM24725Service

```python
from fuj_backend.hardware import ArduinoMCU
from fuj_backend.services import FIM24725Service, OperatingMode

with ArduinoMCU("/dev/arduino") as mcu:
    with FIM24725Service(
        psu1_ip="10.10.10.137", psu1_port=20001, psu1_local_ip="10.10.10.50",
        psu2_ip="10.10.10.138", psu2_port=20002, psu2_local_ip="10.10.10.51",
        mcu=mcu,
    ) as service:
        service.startup()           # MCU initialised as part of startup
        service.set_voa(2.4)
        service.set_oa_x(1.65)
        snapshot = service.get_snapshot()
        print(snapshot)
        service.shutdown()
```

### Example: MockMCU for development (no Arduino required)

```python
from fuj_backend.services import FIM24725Service, MockMCU

# MockMCU is the default — no mcu= argument needed
with FIM24725Service(
    psu1_ip="10.10.10.137", psu1_port=20001,
    psu2_ip="10.10.10.138", psu2_port=20002,
) as service:
    service.startup()
    service.set_voa(2.4)
    service.shutdown()
```

---

## Troubleshooting

### `MCUError: Arduino on /dev/arduino did not send INIT within 2.0s`

Checklist:
1. Check Arduino is plugged in and `/dev/arduino` exists (`ls -l /dev/arduino`)
2. Verify the correct firmware is flashed (`arduino/fim24725_mcu/fim24725_mcu.ino`)
3. Open a serial terminal to verify `INIT:SD=1,MODE=AGC` arrives: `minicom -b 115200 -D /dev/arduino`
4. Ensure no other process holds the port (another `minicom` session, previous Python process)
5. If the Arduino has the blink sketch or no sketch, it will not send `INIT:`

### `serial.SerialException: [Errno 2] No such file or directory: '/dev/arduino'`

- The udev rule creating `/dev/arduino` is not active, or the Arduino is not connected
- Check raw device: `ls /dev/ttyUSB* /dev/ttyACM*`
- Check udev rules: `udevadm info -n /dev/ttyUSB0 | grep -i ftdi`

### `AttributeError: module 'serial' has no attribute 'Serial'`

The conflicting `serial` PyPI package is installed alongside `pyserial`. Fix:

```bash
pip uninstall serial
pip install pyserial
python -c "import serial; print(serial.__version__)"  # should print e.g. 3.5
```

### No telemetry / `MCUError: No telemetry received from Arduino yet`

- Wait at least 600ms after construction before calling `read_peak_indicators()` or `read_mpd()`
- Check the reader thread is alive: if a `SerialException` occurred, `is_connected()` returns `False`
- Telemetry parse errors are logged as `WARNING` and drop the frame silently; check `logs/fim24725_service.log`

### Commands time out (`MCUError: No response to command '...' within 2.0s`)

- Arduino may be emitting `TELE:` lines that are being routed correctly, but the command response was lost
- Check Arduino serial output directly with a terminal to verify responses
- Ensure `timeout` is not set too low (default 2.0s is usually sufficient)

---

## Glossary

- **SD:** Shutdown pin — `HIGH` disables the FIM24725 module; `LOW` enables it; active-low
- **MC/AGC:** Mode Control / Automatic Gain Control pin — `HIGH` = AGC mode; `LOW` = MGC mode
- **PI_XI/XQ/YI/YQ:** Peak Indicator voltages for X-polarisation I/Q and Y-polarisation I/Q channels (0–2V)
- **MPD:** Monitor Photodiode voltage (0–2V)
- **TELE:** Unsolicited telemetry frame emitted by the Arduino every 500ms
- **INIT:** Startup confirmation message emitted once by the Arduino in `setup()`
- **DTR reset:** Arduino Uno resets when the USB serial connection is opened (DTR line toggles); requires 2s boot delay
- **MCUInterface:** Python `typing.Protocol` in `fuj_backend.services` that defines the 7 methods/properties any MCU backend must implement
- **MockMCU:** In-memory MCU stub implementing `MCUInterface`; used when no Arduino is present
- **Reader thread:** Daemon background thread that drains the serial port; separates unsolicited telemetry from synchronous command responses
