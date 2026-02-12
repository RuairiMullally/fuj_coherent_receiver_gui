
# FIM24725 Control Schema

# Implementation Notes — HAL Wrapper

## Design Goals

* Provide a **single device-level API** (bring-up, shutdown, setpoints)

* Hide PSU channel details from higher-level logic

* Enforce:

  * Electrical safety (OVP/OCP)
  * Correct power sequencing
  * Voltage/current bounds

* Maintain a **single source of truth mapping**:

  ```
  (PSU, Channel) → Named Rail/Control → FIM24725 Pin Group
  ```

* Use explicit rail naming:

  * `VCC_3V3`
  * `VPD_5V0`
  * `VOA_CTRL`

---

## Safety Requirements

* Always program **OVP and OCP before enabling output**
* Validate input bounds before applying:

  * OA
  * GA
  * VOA
* Unified fault path:

  * Any fault → Immediate action → `SD = DISABLE`
* Define a **PSU Ready condition** before allowing `SD = ENABLE`
* If MCU unresponsive:

  * Default to safe state (`SD = DISABLE`)
  * Fail bring-up
* Implement logging:

  * State transitions
  * MCU commands

---

## Operating Modes

### AGC Mode

* MCU sets `MC/AGC = AGC`
* GA channels become *don't-care* (held in safe range)
* OA and VOA remain valid controls
* Provide recommended OA defaults

---

### MGC Mode

* MCU sets `MC/AGC = MGC`
* GA becomes active control
* Provide:

  * Safe stepping
  * Sweep features
  * Guardrails on range

---

## High-Level Control Functions

```c
set_voa(volts)      // clamp 0–4.8 V
set_oa_x(volts)     // clamp 0–VCC
set_oa_y(volts)
set_ga_x(volts)     // clamp 0–VCC (MGC only)
set_ga_y(volts)
```

* Treat MCU commands as asynchronous relative to PSU
* Require PSU ready confirmation before enabling SD

---



# PSU 1 — Amplifier Supply, Diode Bias, VOA

| PSU  | Ch | Rail Name | Description                 | FIM24725 Pins                 | VSET    | OVP     | OCP             | Notes                                                          |
| ---- | -- | --------- | --------------------------- | ----------------------------- | ------- | ------- | --------------- | -------------------------------------------------------------- |
| PSU1 | 1  | VCC_3V3   | Amplifier supply (X & Y)    | VCC_Y (13) + VCC_X (22)       | 3.300 V | 3.600 V | 0.800 A         | VCC op: 3.135–3.465 V. Icc 360–400 mA. OVP below abs max 4.5 V |
| PSU1 | 2  | VPD_5V0   | Photodiode supply           | VPD_Y* (6–9) + VPD_X* (26–29) | 5.000 V | 5.500 V | 0.200 A (start) | VPD op: 4.75–5.25 V. Abs max PD reverse 7 V                    |
| PSU1 | 3  | VOA_CTRL  | Variable optical attenuator | VOA1 (31), VOA2 (30 = GND)    | 0–4.8 V | 5.000 V | 0.100 A         | Max current 80 mA. Abs max 5.2 V                               |

---

## PSU1 Notes

* VOA2 hard tied to GND
* All grounds common
* VOA prevents photodiode saturation
* Cannot be driven by Arduino (>40 mA possible)
* No hardware risk from high VOA setting — only degraded signal quality

---

# PSU 2 — Analogue Controls (GA / OA)

| PSU  | Ch | Rail Name | Description        | FIM24725 Pins           | Range   | OVP   | OCP     | Notes       |
| ---- | -- | --------- | ------------------ | ----------------------- | ------- | ----- | ------- | ----------- |
| PSU2 | 1  | GA_X      | Gain adjust X      | GA-XI (19) + GA-XQ (24) | 0–3.3 V | 3.6 V | 0.020 A | Range 0–VCC |
| PSU2 | 2  | GA_Y      | Gain adjust Y      | GA-YI (11) + GA-YQ (16) | 0–3.3 V | 3.6 V | 0.020 A | Same        |
| PSU2 | 3  | OA_X      | Output amplitude X | OA-XI (20) + OA-XQ (23) | 0–3.3 V | 3.6 V | 0.020 A | Range 0–VCC |
| PSU2 | 4  | OA_Y      | Output amplitude Y | OA-YI (12) + OA-YQ (15) | 0–3.3 V | 3.6 V | 0.020 A | Same        |

---

## PSU2 Notes

* GA and OA must never exceed VCC

---

# External MCU — Digital Control

| Signal | Description        | Pins                                           | Direction        | Threshold                              |
| ------ | ------------------ | ---------------------------------------------- | ---------------- | -------------------------------------- |
| SD     | Shutdown           | SD (32)                                        | MCU → Module     | Enable: 0–0.8 V; Disable: 2 V–VCC      |
| MC/AGC | Mode select        | MC/AGC (3)                                     | MCU → Module     | MGC: 0–0.8 V; AGC: 2 V–VCC             |
| PI     | Peak indicators    | PI-XI (18), PI-XQ (25), PI-YI (10), PI-YQ (17) | Module → MCU ADC | 0–2 V                                  |
| MPD    | Monitor photodiode | MPD+ (4), MPD− (5)                             | Module → AFE/ADC | Treat as photodiode node; do not drive |

---

# Bring-Up Algorithm

## 1. Initial State

* All PSU outputs OFF
* `SD = DISABLE (HIGH)`
* `MC/AGC = AGC (HIGH)`

---

## 2. Program Protections

### PSU1

* VCC_3V3: 3.300 V / 3.600 V / 0.800 A
* VPD_5V0: 5.000 V / 5.500 V / 0.200 A
* VOA_CTRL: 0.0–1.0 V start / 5.000 V / 0.100 A

### PSU2

* GA_X/Y, OA_X/Y = 0 V
* OVP = 3.600 V
* OCP = 0.020 A

---

## 3. Enable VCC

* Turn ON PSU1 CH1
* Verify:

  * VOUT ≈ 3.3 V
  * IOUT ≈ 360–400 mA
* Fault if abnormal

---

## 4. Enable VPD

* Turn ON PSU1 CH2
* Verify 5.0 V
* Increase OCP only if required

---

## 5. Set Initial Controls (SD disabled)

* GA_X, GA_Y = 0 V
* OA_X, OA_Y = 0 V
* VOA initial low (verify polarity)

---

## 6. Settling

* Wait 50–200 ms

---

## 7. Enable Output

* `SD = ENABLE (LOW)`

---

## 8. Validate

* Read PI (0–2 V)
* Ensure not pinned high/low

---

# Shutdown Sequence

1. `SD = DISABLE`
2. Return controls to safe values
3. Power down in reverse risk order:

   * VPD off
   * VCC off
   * Remaining controls off

---

# Functional Notes

## VOA

* Optical attenuation control
* No hardware damage from high setting
* Only affects signal quality

---

## MC / AGC

* AGC: automatic internal gain
* MGC: user-controlled GA

---

## TIA

Transimpedance amplifier: photodiode current → voltage

---

## GA

* Internal gain control
* Affects:

  * Noise profile
  * Output swing
* Mostly useful for lab characterization

---

## OA

* Final output amplitude adjustment
* Does not affect noise
* Used for downstream interface compatibility

---

## PI

Indicates:

* Clipping (~2 V)
* Power loss (~0 V)

Useful for:

* Rail detection
* Gain effectiveness
* Signal validation

---

## MPD

* Measures optical input independent of gain
* MPD = optical reality
* PI = electrical state
