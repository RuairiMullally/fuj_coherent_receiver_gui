"""
FIM24725 Service - Full Command Exercise Script

Exercises every public service command with 2-second pauses between steps
so that PSU outputs, FIM24725 behaviour, and MCU responses can be
physically inspected at each stage.

Network config:
    NIC 1 (10.10.10.50) -> PSU1 (10.10.10.137)  -- VCC / VPD / VOA
    NIC 2 (10.10.10.51) -> PSU2 (10.10.10.138)  -- GA_X / GA_Y / OA_X / OA_Y
"""

import time

from fuj_backend.hardware import ArduinoMCU
from fuj_backend.services import FIM24725Service, OperatingMode


PAUSE = 2.0  # seconds between steps


def step(label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    time.sleep(2)


def show(label: str, value: object) -> None:
    print(f"  {label}: {value}")


# ---------------------------------------------------------------------------

with ArduinoMCU("/dev/arduino") as mcu:
    with FIM24725Service(
        psu1_ip="10.10.10.137",
        psu1_port=20001,
        psu1_local_ip="10.10.10.50",
        psu2_ip="10.10.20.137",
        psu2_port=20002,
        psu2_local_ip="10.10.20.50",
        mcu=mcu,
    ) as service:

        # ------------------------------------------------------------------
        # STARTUP
        # ------------------------------------------------------------------
        step("startup() — full sequenced bring-up in AGC mode")
        service.startup(OperatingMode.AGC)
        show("state", service.state)
        show("mode", service.mode)

        # ------------------------------------------------------------------
        # MONITORING — initial readings
        # ------------------------------------------------------------------
        step("get_snapshot() — full system snapshot after startup")
        snap = service.get_snapshot()
        show("state", snap.state)
        show("mode", snap.mode)
        show("sd_enabled", snap.sd_enabled)
        for name, meas in snap.rails.items():
            show(f"  {name.value}", f"{meas.voltage:.3f}V / {meas.current:.3f}A [{meas.state.value}]")
        if snap.peak_indicators:
            pi = snap.peak_indicators
            show("PI", f"XI={pi.pi_xi:.3f}V  XQ={pi.pi_xq:.3f}V  YI={pi.pi_yi:.3f}V  YQ={pi.pi_yq:.3f}V")
        show("MPD", snap.mpd_value)

        step("read_peak_indicators() — standalone PI read")
        pi = service.read_peak_indicators()
        show("PI_XI", f"{pi.pi_xi:.3f}V")
        show("PI_XQ", f"{pi.pi_xq:.3f}V")
        show("PI_YI", f"{pi.pi_yi:.3f}V")
        show("PI_YQ", f"{pi.pi_yq:.3f}V")

        step("read_mpd() — monitor photodiode read")
        mpd = service.read_mpd()
        show("MPD", f"{mpd:.3f}V")

        # ------------------------------------------------------------------
        # VOA CONTROL
        # ------------------------------------------------------------------
        step("set_voa(0.0) — minimum attenuation")
        service.set_voa(0.0)

        step("set_voa(1.2) — mid-low attenuation")
        service.set_voa(1.2)

        step("set_voa(2.5) — mid attenuation (nominal)")
        service.set_voa(2.5)

        step("set_voa(3.6) — high attenuation")
        service.set_voa(3.6)

        step("set_voa(4.8) — maximum attenuation")
        service.set_voa(4.8)

        step("set_voa(2.4) — return to operating point")
        service.set_voa(2.4)

        # ------------------------------------------------------------------
        # OA CONTROL (X and Y)
        # ------------------------------------------------------------------
        step("set_oa_x(0.0) — OA_X minimum")
        service.set_oa_x(0.0)

        step("set_oa_x(1.65) — OA_X mid (VCC/2)")
        service.set_oa_x(1.65)

        step("set_oa_x(3.3) — OA_X maximum")
        service.set_oa_x(3.3)

        step("set_oa_x(1.65) — OA_X return to mid")
        service.set_oa_x(1.65)

        step("set_oa_y(0.0) — OA_Y minimum")
        service.set_oa_y(0.0)

        step("set_oa_y(1.65) — OA_Y mid (VCC/2)")
        service.set_oa_y(1.65)

        step("set_oa_y(3.3) — OA_Y maximum")
        service.set_oa_y(3.3)

        step("set_oa_y(1.65) — OA_Y return to mid")
        service.set_oa_y(1.65)

        # ------------------------------------------------------------------
        # GA PRE-STAGING (still in AGC — FIM24725 ignores GA pins in AGC)
        # ------------------------------------------------------------------
        step("set_ga_x(1.0) — pre-stage GA_X in AGC mode (FIM24725 ignores, PSU accepts)")
        service.set_ga_x(1.0)

        step("set_ga_y(1.0) — pre-stage GA_Y in AGC mode")
        service.set_ga_y(1.0)

        # ------------------------------------------------------------------
        # MODE SWITCH TO MGC — pre-staged GA values become active
        # ------------------------------------------------------------------
        step("set_mode(MGC) — switch to manual gain control; pre-staged GA_X/Y now active")
        service.set_mode(OperatingMode.MGC)
        show("mode", service.mode)

        # ------------------------------------------------------------------
        # GA CONTROL (in MGC — now active)
        # ------------------------------------------------------------------
        step("set_ga_x(0.0) — GA_X minimum in MGC")
        service.set_ga_x(0.0)

        step("set_ga_x(1.65) — GA_X mid")
        service.set_ga_x(1.65)

        step("set_ga_x(3.3) — GA_X maximum")
        service.set_ga_x(3.3)

        step("set_ga_x(1.0) — GA_X return to operating point")
        service.set_ga_x(1.0)

        step("set_ga_y(0.0) — GA_Y minimum in MGC")
        service.set_ga_y(0.0)

        step("set_ga_y(1.65) — GA_Y mid")
        service.set_ga_y(1.65)

        step("set_ga_y(3.3) — GA_Y maximum")
        service.set_ga_y(3.3)

        step("set_ga_y(1.0) — GA_Y return to operating point")
        service.set_ga_y(1.0)

        # ------------------------------------------------------------------
        # GA SWEEP (MGC required)
        # ------------------------------------------------------------------
        step("sweep_ga('X', 0.0, 3.3, 0.3, dwell_ms=200) — GA_X sweep up")
        results_x = service.sweep_ga("X", start=0.0, end=3.3, step=0.3, dwell_ms=200)
        print(f"  Swept {len(results_x)} points:")
        for v, pi in results_x:
            print(f"    GA_X={v:.2f}V  PI: XI={pi.pi_xi:.3f} XQ={pi.pi_xq:.3f} YI={pi.pi_yi:.3f} YQ={pi.pi_yq:.3f}")

        step("sweep_ga('Y', 0.0, 3.3, 0.3, dwell_ms=200) — GA_Y sweep up")
        results_y = service.sweep_ga("Y", start=0.0, end=3.3, step=0.3, dwell_ms=200)
        print(f"  Swept {len(results_y)} points:")
        for v, pi in results_y:
            print(f"    GA_Y={v:.2f}V  PI: XI={pi.pi_xi:.3f} XQ={pi.pi_xq:.3f} YI={pi.pi_yi:.3f} YQ={pi.pi_yq:.3f}")

        # ------------------------------------------------------------------
        # MODE SWITCH BACK TO AGC
        # ------------------------------------------------------------------
        # GA retains its last value (end of sweep); FIM24725 ignores GA in AGC.
        # Pre-staged for next MGC session — no zeroing needed.
        step("set_mode(AGC) — return to automatic gain control; GA value retained")
        service.set_mode(OperatingMode.AGC)
        show("mode", service.mode)

        # ------------------------------------------------------------------
        # FINAL SNAPSHOT
        # ------------------------------------------------------------------
        step("get_snapshot() — full system snapshot before shutdown")
        snap = service.get_snapshot()
        show("state", snap.state)
        show("mode", snap.mode)
        for name, meas in snap.rails.items():
            show(f"  {name.value}", f"{meas.voltage:.3f}V / {meas.current:.3f}A [{meas.state.value}]")
        if snap.peak_indicators:
            pi = snap.peak_indicators
            show("PI", f"XI={pi.pi_xi:.3f}V  XQ={pi.pi_xq:.3f}V  YI={pi.pi_yi:.3f}V  YQ={pi.pi_yq:.3f}V")

        # ------------------------------------------------------------------
        # SHUTDOWN
        # ------------------------------------------------------------------
        step("shutdown() — orderly sequenced shutdown")
        service.shutdown()
        show("state", service.state)

        print("\n[done]")
