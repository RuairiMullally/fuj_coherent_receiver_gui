# PSU_HAL API (MP710508 / MP710509)

Python library for controlling Multicomp Pro MP710508/MP710509 4-channel PSUs over UDP.

The library models:
- **One `MP71050x` object per physical PSU**
- **One `Channel` object per PSU output channel (1–4)**

It’s designed so you never confuse “channel 2” across different PSUs: a `Channel` is always bound to one `MP71050x`.

---

## Quick start

```python
from PSU_HAL import PsuTransportUDP, MP71050x

psu_a = MP71050x(
    "PSU_A",
    PsuTransportUDP(
        psu_ip="10.10.10.137", psu_port=20001,
        local_ip="10.10.10.50", local_port=20001
    )
)

ch1 = psu_a.channel(1)

ch1.set_voltage(5.0)
ch1.set_current_limit(0.5)
ch1.output(True)

print(ch1.measure_voltage(), ch1.measure_current())

ch1.output(False)
```

---

## Library objects

### `PsuTransportUDP`

Represents the *network connection settings* used to talk to a PSU.

**What it represents**

* The PSU’s destination IP/UDP port
* The local bind IP/port (often set to match PSU port)

**Constructor**

```python
PsuTransportUDP(
    psu_ip: str,
    psu_port: int = 18190,
    local_ip: str | None = None,
    local_port: int | None = 18190,
    term: bytes = b"\n",
    timeout_s: float = 2.0,
)
```

**When using multiple PSUs**

* Give each PSU a unique UDP port (e.g., 20001, 20002, …)
* Bind the local port to the matching port for that PSU instance

---

### `MP71050x`

Represents **one physical PSU** (one box on the bench).

**What it represents**

* A single instrument with its own identity, 4 channels, and device-wide settings.
* A command boundary: operations to the same PSU are executed sequentially.

**Constructor**

```python
MP71050x(name: str, transport: PsuTransportUDP)
```

**Attributes**

* `name: str` — your label for the PSU (e.g. `"PSU_A"`)
* `t: PsuTransportUDP` — transport settings used for communication

**Device-wide methods**

```python
identify(refresh: bool = False) -> DeviceId
lock_front_panel(locked: bool) -> None
beep(enabled: bool) -> None
status() -> Status
set_output(channels: Channels, enabled: bool) -> None
save_profile(slot: int) -> None        # slot 0..9
recall_profile(slot: int) -> None      # slot 0..9
channel(ch: int) -> Channel            # ch 1..4
```

**Channel selection (`Channels`)**

* `int` → one channel (1..4)
* `Iterable[int]` → multiple channels (e.g. `[1,3,4]`)
* `None` → all channels

---

### `Channel`

Represents **one PSU channel** (CH1–CH4) bound to a specific PSU.

**What it represents**

* A view of a single output channel that always knows which PSU it belongs to.

**Created by**

```python
ch = psu.channel(1)
```

---

## Data structures

### `DeviceId`

Return type of `MP71050x.identify()`.

```python
DeviceId(
  raw: str,                 # full response
  model: str,               # "MP710508" etc.
  version: str | None,      # "V1.1" etc.
  serial: str | None        # parsed from SN:...
)
```

### `Status`

Return type of `MP71050x.status()`.

```python
Status(
  raw: int,                          # bitfield byte
  mode: ("CV"|"CC", "CV"|"CC", ...), # per-channel modes
  output: (bool, bool, bool, bool)   # per-channel output ON/OFF
)
```

---

## `MP71050x` methods (device-wide)

### `identify(refresh=False) -> DeviceId`

Reads and parses the PSU identity string.

### `lock_front_panel(locked: bool) -> None`

Locks/unlocks front panel buttons.

### `beep(enabled: bool) -> None`

Enables/disables keypad beep.

### `status() -> Status`

Reads PSU status (CV/CC + output on/off states).

### `set_output(channels: Channels, enabled: bool) -> None`

Turns outputs on/off for one, many, or all channels.

Examples:

```python
psu.set_output(1, True)          # CH1 on
psu.set_output([2,4], False)     # CH2 & CH4 off
psu.set_output(None, False)      # all off
```

### `save_profile(slot: int) -> None` / `recall_profile(slot: int) -> None`

Saves/recalls a front-panel memory slot (0–9).

### `channel(ch: int) -> Channel`

Returns a channel object bound to this PSU.

---

## `Channel` methods (per-channel)

### Setpoints

```python
set_voltage(volts: float) -> None
get_voltage_setpoint() -> float

set_current_limit(amps: float) -> None
get_current_setpoint() -> float
```

### Measurements (readback)

```python
measure_voltage() -> float
measure_current() -> float
```

### Output control

```python
output(enabled: bool) -> None
```

### Protection (OVP/OCP)

```python
set_ovp(volts: float, enabled: bool | None = None) -> None
get_ovp() -> tuple[float, bool]          # (level, enabled)

set_ocp(amps: float, enabled: bool | None = None) -> None
get_ocp() -> tuple[float, bool]          # (level, enabled)
```

### LIST programming

Programs sequence list parameters for this channel.

```python
list_set_step(list_id: int, step: int, volts: float, amps: float, dwell_s: float) -> None
list_set_length(list_id: int, length: int) -> None
list_set_cycles(list_id: int, cycles: int) -> None
list_save(list_id: int) -> None
```

### External controls

```python
external_trigger(enabled: bool) -> None     # external trigger enable
external_switch(enabled: bool) -> None      # external switch enable
external_comp(enabled: bool) -> None        # external compensation enable
```

### Automatic stepping

```python
auto_step_voltage(v_start: float, v_end: float, v_step: float, step_time_s: float) -> None
auto_step_voltage_stop() -> None

auto_step_current(i_start: float, i_end: float, i_step: float, step_time_s: float) -> None
auto_step_current_stop() -> None
```

### Manual stepping

```python
set_manual_voltage_step(step_v: float) -> None
voltage_step_up() -> None
voltage_step_down() -> None

set_manual_current_step(step_a: float) -> None
current_step_up() -> None
current_step_down() -> None
```

---

## Execution model (synchrony & ordering)

* All calls are **synchronous** (blocking).
* Within a single PSU instance, commands are executed **sequentially** (no interleaving).
* Different PSU instances can be used independently (and can run in parallel in different threads/processes if desired).

---

## Recommended multi-PSU setup

Assign each PSU a unique UDP port and match local binds:

```python
psu_a = MP71050x("A", PsuTransportUDP("10.10.10.137", psu_port=20001, local_ip="10.10.10.50", local_port=20001))
psu_b = MP71050x("B", PsuTransportUDP("10.10.10.138", psu_port=20002, local_ip="10.10.10.50", local_port=20002))
```

This keeps replies isolated per PSU.



## Examples

### Example: Bring up a channel safely (no load)
```python
ch = psu_a.channel(1)

# setpoints
ch.set_voltage(2.5)
ch.set_current_limit(0.2)

# protections (optional but recommended)
ch.set_ovp(3.0, enabled=True)
ch.set_ocp(0.25, enabled=True)

# enable output
ch.output(True)

# readback
print("V=", ch.measure_voltage(), "I=", ch.measure_current())

# shutdown
ch.output(False)
```

### Example: Control multiple channels on one PSU

```python
psu_a.set_output(None, False)      # all off
psu_a.set_output([1,2], True)      # CH1 and CH2 on
psu_a.set_output(3, True)          # CH3 on
psu_a.set_output([2,3], False)     # CH2 and CH3 off
```

### Example: Quick health check

```python
dev = psu_a.identify()
st = psu_a.status()

print(dev.model, dev.version, dev.serial)
print("Modes:", st.mode)
print("Outputs:", st.output)
```

### Example: Program a simple LIST on CH1

```python
ch1 = psu_a.channel(1)

list_id = 1
ch1.list_set_step(list_id, step=1, volts=1.0, amps=0.1, dwell_s=0.5)
ch1.list_set_step(list_id, step=2, volts=2.0, amps=0.2, dwell_s=0.5)
ch1.list_set_length(list_id, length=2)
ch1.list_set_cycles(list_id, cycles=5)
ch1.list_save(list_id)
```

### Example: Manual stepping (easy front-panel-visible changes)

```python
ch1 = psu_a.channel(1)

ch1.set_voltage(1.0)
ch1.set_manual_voltage_step(0.25)

ch1.voltage_step_up()
ch1.voltage_step_up()
ch1.voltage_step_down()

print("VSET =", ch1.get_voltage_setpoint())
```

---

## Common patterns

### Pattern: Keep channels as long-lived references

Recommended:

```python
psu_a = MP71050x("A", transport_a)
laser_bias = psu_a.channel(1)
tec_supply = psu_a.channel(2)

laser_bias.set_voltage(3.3)
tec_supply.set_voltage(1.8)
```

This makes it obvious which PSU/channel a command applies to.

### Pattern: Bundle operations in helper functions

```python
def configure_laser_supply(ch, v, i):
    ch.set_voltage(v)
    ch.set_current_limit(i)
    ch.set_ovp(v + 0.5, enabled=True)
    ch.set_ocp(i + 0.1, enabled=True)

configure_laser_supply(psu_a.channel(1), 5.0, 0.5)
```

---

## Troubleshooting notes (usage-focused)

### No replies / timeouts

Checklist:

1. Verify PSU IP reachable (ping)
2. Confirm you’re sending to the correct `psu_port`
3. Ensure `local_ip` is the correct NIC address for the lab network
4. Bind `local_port` to match the PSU port (recommended for this PSU family)

### Multiple PSUs in one program

Recommendation:

* Assign each PSU a unique UDP port (e.g., 20001, 20002…)
* Match local binds to those ports per PSU instance
* Create one `MP71050x` per physical PSU

---

## Compatibility notes

* The API is intended to remain stable even if the underlying transport changes (UDP today, possibly USB/serial later).
* Methods use **engineering units**:

  * volts (V), amps (A), seconds (s)

---

## Glossary

* **PSU**: Physical power supply unit (one MP710508/MP710509 instrument)
* **Channel**: One output of the PSU (CH1–CH4)
* **Setpoint**: The configured voltage/current limit (`VSET`, `ISET`)
* **Readback**: Measured output voltage/current (`VOUT`, `IOUT`)
* **OVP/OCP**: Over-voltage / Over-current protection
* **LIST**: Programmable sequence table (steps of V/I/dwell)
* **Stepping**: Incrementing setpoints either manually or automatically

---

