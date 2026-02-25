# ADR-003: Arduino MCU Interface

**Status:** Accepted
**Date:** 2026-02-24
**Authors:** Project Team

---

## Context

The FIM24725 coherent optical receiver module requires two digital control signals that the PSU HAL cannot provide:

- **SD (Shutdown):** drives the FIM24725 module enable/disable line
- **MC/AGC (Mode):** selects between Manual Gain Control (MGC) and Automatic Gain Control (AGC)

In addition, five 0–2V analog signals must be read back periodically:

- **PI_XI, PI_XQ, PI_YI, PI_YQ:** Peak Indicator signals per polarisation/quadrature
- **MPD:** Monitor Photodiode voltage

These signals require a microcontroller with digital output and ADC capability. The Raspberry Pi used as the system controller does not expose bare GPIO suitable for production use, so an external MCU is needed.

### Key Constraints

1. **ADR-002 MCUInterface Protocol:** The services layer defines an `MCUInterface` Protocol; any MCU backend must implement its seven methods/properties
2. **Pi is the host:** The Raspberry Pi runs `FIM24725Service` and owns all application state; the Arduino is a stateless peripheral — it executes commands and reports sensor readings
3. **No blocking firmware:** Firmware must not block the main loop; 500ms telemetry must be emitted regardless of command traffic
4. **Fault propagation:** Hardware faults detected on the Arduino (pin readback mismatch) must propagate to the Pi and trigger a service-level emergency shutdown
5. **Startup confirmation:** The service must not proceed with startup unless the Arduino has confirmed its initial state, preventing operation with wrong/missing firmware

---

## Decision

We will use an **OSEPP Arduino Uno R3** (FTDI FT232R, USB serial, `/dev/arduino` on Pi) as the MCU peripheral, with a stateless command/response firmware and a Python `ArduinoMCU` host class.

### 1. Hardware Assignment

| Signal  | Arduino Pin | Direction | Logic                          |
|---------|-------------|-----------|--------------------------------|
| SD      | D2          | Output    | HIGH = module disabled (safe state) |
| MC/AGC  | D3          | Output    | HIGH = AGC, LOW = MGC          |
| PI_XI   | A0          | Input ADC | 0–2V signal, 5V AREF           |
| PI_XQ   | A1          | Input ADC | 0–2V signal                    |
| PI_YI   | A2          | Input ADC | 0–2V signal                    |
| PI_YQ   | A3          | Input ADC | 0–2V signal                    |
| MPD     | A4          | Input ADC | 0–2V signal                    |

D2 and D3 are set `HIGH` (safe/disabled state) in `setup()` before enabling outputs, preventing glitches on the FIM24725 control pins at power-on.

ADC conversion: `voltage = (analogRead(pin) / 1024.0) * 5.0`
Default AREF = VCC = 5V, giving ~4.9 mV/count over the 0–2V signal range.

### 2. Serial Protocol

All messages are ASCII, `\n`-terminated, sent over 115200 baud.

| Direction      | Message                                            | Meaning                               |
|----------------|----------------------------------------------------|---------------------------------------|
| Host → Arduino | `PING`                                             | Connectivity check                    |
| Arduino → Host | `PONG`                                             | Reply to PING                         |
| Host → Arduino | `SD:1`                                             | Set SD HIGH (module disabled)         |
| Host → Arduino | `SD:0`                                             | Set SD LOW (module enabled)           |
| Arduino → Host | `SD:1` / `SD:0`                                    | Echo applied SD state                 |
| Host → Arduino | `MODE:AGC`                                         | Set MC/AGC HIGH                       |
| Host → Arduino | `MODE:MGC`                                         | Set MC/AGC LOW                        |
| Arduino → Host | `MODE:AGC` / `MODE:MGC`                            | Echo applied mode                     |
| Arduino → Host | `INIT:SD=1,MODE=AGC`                               | Startup complete, initial state       |
| Arduino → Host | `TELE:PI_XI=x.xxx,PI_XQ=x.xxx,PI_YI=x.xxx,PI_YQ=x.xxx,MPD=x.xxx` | Periodic telemetry (500ms) |
| Arduino → Host | `ERR:UNKNOWN:cmd`                                  | Unrecognised command                  |
| Arduino → Host | `ERR:PIN_FAULT:SD`                                 | SD pin readback mismatch              |
| Arduino → Host | `ERR:PIN_FAULT:MODE`                               | MC/AGC pin readback mismatch          |

Command responses are always exactly one line. Telemetry lines are unsolicited and interleaved independently of command traffic.

### 3. Arduino Firmware Design (`arduino/fim24725_mcu/fim24725_mcu.ino`)

- **Non-blocking serial:** Characters are accumulated in a `String` buffer in `loop()`; dispatch occurs on `\n`. `readStringUntil()` is avoided as it blocks for the full timeout on each call.
- **Periodic telemetry:** `millis()` comparison in `loop()` emits a `TELE:` line every 500ms without interrupts or blocking.
- **Setup:** D2/D3 set to `HIGH` (safe state) before `pinMode(OUTPUT)` to avoid a brief LOW glitch. `INIT:SD=1,MODE=AGC` is emitted at the end of `setup()`.
- **Pin readback verification:** After each `digitalWrite()`, `digitalRead()` verifies the pin state. A mismatch emits `ERR:PIN_FAULT:SD` or `ERR:PIN_FAULT:MODE` instead of the normal echo.
- **Stateless:** No application state is kept between commands; all persistent state lives in `FIM24725Service` on the Pi.

### 4. Python Host Class (`src/fuj_backend/hardware/arduino_mcu.py`)

`ArduinoMCU` implements `MCUInterface` via `pyserial`.

**Construction and startup sequence:**

1. Open `serial.Serial(port, 115200, timeout=0.1)` with short read timeout for non-blocking reader
2. Sleep 2s (`BOOT_DELAY_S`) for Arduino reset-on-DTR to complete
3. Clear the input buffer (discards any partial startup noise)
4. Start daemon background reader thread (`arduino-reader`)
5. Wait for `_init_event` (set when `INIT:` line is received), up to `timeout` seconds
6. Raise `MCUError` if `INIT:` is not received — prevents operation with wrong or missing firmware

**Background reader thread (`_reader_loop`):**

- Calls `readline()` in a loop until `_stop_reader` is set
- `TELE:` lines → `_parse_telemetry()` → updates `_last_pi` / `_last_mpd` under `_tele_lock`
- `INIT:` lines → sets `_init_event` (also handles reconnect scenarios)
- All other lines → `_response_queue.put(line)` for synchronous callers
- `SerialException` → sets `_connected = False`, logs error, exits thread

**Command/response cycle (`_send_command`):**

- Writes `cmd + "\n"` to serial
- Calls `_response_queue.get(timeout=self._timeout)` — blocks until response or timeout
- Raises `MCUError("No response to command: ...")` on timeout
- Raises `MCUError("Arduino error: ERR:...")` if response starts with `ERR:`

**Cached initial state:** `_sd_disabled = True`, `_mode = OperatingMode.AGC` — matches the Arduino's `setup()` initial state so property reads are valid before any command is sent.

### 5. MCU Error → Service Fault Propagation

`FIM24725Service` catches `MCUError` in runtime methods and triggers an emergency shutdown:

```python
def _fault_on_mcu_error(self, context: str, e: MCUError) -> None:
    self._logger.error(f"MCU error during {context}: {e}")
    self._state.fault(FaultInfo(
        message=f"MCU error during {context}: {e}",
        timestamp=time.time(),
        recoverable=False,
    ))
```

Methods wrapped: `set_mode()`, `read_peak_indicators()`, `read_mpd()`.
Startup errors are already covered by the existing `except Exception → self._state.fault()` block in `startup()`.

### 6. udev / Device Path

The Arduino is symlinked to `/dev/arduino` on the Pi via udev matching FTDI FT232R VID:PID `0403:6001`. This provides a stable path independent of USB enumeration order.

### 7. Dependency

`pyserial>=3.5` added to `pyproject.toml`. Note: the package is `pyserial` on PyPI, not `serial`. If both are installed, the shadowing `serial` package must be removed: `pip uninstall serial && pip install pyserial`.

---

## Consequences

### Positive

- **Firmware-confirmed startup:** `INIT:` handshake ensures the correct firmware is running before any sequence proceeds
- **Clean separation:** Pi owns all state; Arduino is a dumb peripheral — simplifies firmware and avoids state synchronisation problems
- **Non-blocking firmware:** `millis()`-based telemetry and character-buffer serial read ensure 500ms cadence is maintained regardless of command load
- **Fault transparency:** Pin readback errors (`ERR:PIN_FAULT:*`) propagate immediately to the service fault state and trigger emergency shutdown
- **Protocol simplicity:** ASCII line-based protocol is human-readable and debuggable with any serial terminal (e.g., `minicom -b 115200 -D /dev/arduino`)
- **Thread-safe telemetry:** Background reader with `threading.Lock` prevents race conditions between telemetry updates and service reads

### Trade-offs

- **DTR reset delay:** 2s boot delay on every `ArduinoMCU()` construction is unavoidable without hardware modification (100nF cap on RST line) — acceptable for a laboratory instrument
- **Telemetry latency:** Readings are up to 500ms stale; not suitable for real-time closed-loop control
- **USB single point of failure:** Serial disconnect is detected but not automatically recovered; the service faults and requires manual restart
- **ADC precision:** 10-bit ADC over 5V gives ~4.9 mV/count; signals are 0–2V so only ~40% of range is used, effective resolution is ~6.4 mV over the signal range

### Risks Mitigated

- **Wrong firmware:** `INIT:` handshake prevents operating with wrong/stale firmware or bare Arduino with no sketch
- **Pin glitch on power-on:** D2/D3 pre-set HIGH before `pinMode(OUTPUT)` prevents a LOW glitch that would momentarily enable the FIM24725 during Arduino boot
- **State drift:** Cached state (`_sd_disabled`, `_mode`) is initialised to match Arduino's startup state; properties always reflect either initial or last-commanded state

---

## Alternatives Considered

### 1. Raspberry Pi GPIO Direct

Rejected because:
- Pi GPIO is 3.3V; FIM24725 control signals require level shifting to be verified
- No ADC on Pi without additional hardware
- GPIO access from Python requires root or group membership; complicates Docker deployment

### 2. W5500 Ethernet Shield on Arduino

Rejected for this version because:
- Adds significant firmware complexity (W5500 SPI driver, UDP stack)
- Ethernet cable run to Arduino added infrastructure cost
- Serial over USB is sufficient and already provided by the OSEPP board's FTDI chip
- Retained as a future upgrade path (see Future Considerations)

### 3. External I2C ADC + GPIO Expander

Rejected because:
- Requires dedicated I2C-to-serial bridge or direct Pi I2C access (GPIO issue above)
- Arduino Uno provides both ADC and GPIO in a single, well-supported package
- Adds parts count and firmware complexity

### 4. Polling Model (No Background Reader Thread)

Rejected because:
- Telemetry lines arrive asynchronously and must not block command/response cycles
- Without a reader thread, a TELE: line arriving between a command write and response read would corrupt the command/response queue

---

## Future Considerations

1. **W5500 Ethernet Shield:** Replace USB serial with UDP over Ethernet to match the PSU HAL transport pattern; enables remote Pi → Arduino communication without USB cable constraints
2. **DTR disable on connection:** If boot delay becomes a problem, the FT232R DTR line can be disabled in software (`serial.Serial(dsrdtr=False)`) or suppressed with a hardware RC filter
3. **Automatic serial reconnect:** Background reader thread could attempt reconnect on `SerialException`, bringing connectivity back without a service restart
4. **Higher ADC resolution:** Replace Arduino Uno ADC (10-bit, 5V ref) with external ADS1115 (16-bit, configurable gain) if signal fidelity requirements increase
5. **Telemetry history buffer:** Replace single-value cache with a ring buffer of timestamped readings to support trend analysis and data logging

---

## References

- [ADR-001: PSU Hardware Abstraction Layer](ADR-001-psu-hal.md)
- [ADR-002: FIM24725 Services Layer](ADR-002-services-layer.md)
- [Arduino MCU API Documentation](../arduino_mcu_api.md)
- Arduino Uno R3 datasheet — ATmega328P, 10-bit ADC, 14 digital I/O
- FTDI FT232R datasheet — USB-to-serial, VID `0403`, PID `6001`
