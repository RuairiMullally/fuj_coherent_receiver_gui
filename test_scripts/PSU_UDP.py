## PSU_IP = "192.168.1.198" #10.10.10.137
"""
Comprehensive MP71050x test script (UDP) for one PSU.

Run from Windows host (not WSL) so network routing is correct.
Keep a hand on the output button the first time you run any automation.

Assumes:
- PSU_A is reachable at 10.10.10.137
- PSU_A device UDP port is 20001
- Client binds local 10.10.10.50:20001 (matches PSU port; empirically required)

This script exercises many functions across the command surface.
"""

import time
from src.fuj_backend.hardware.psu_hal import PsuTransportUDP, MP71050x

# ---------- configure ----------
PSU_IP = "10.10.10.138"
PSU_PORT = 20002
LOCAL_IP = "10.10.10.51"
LOCAL_PORT = 20002

CH = 1  # we primarily test Channel 1

# Safe test levels
V_LOW = 0.500
V_MID = 2.500
V_HIGH = 5.000
I_LOW = 0.050
I_MID = 0.250
I_HIGH = 0.500

# How long to pause so you can see changes on the front panel
PANEL_DELAY = 0.6


def banner(msg: str):
    print("\n" + "=" * 70)
    print(msg)
    print("=" * 70)


def show_status(psu: MP71050x, label: str = ""):
    st = psu.status()
    prefix = f"[{label}] " if label else ""
    print(f"{prefix}STATUS raw=0x{st.raw:02x} mode={st.mode} out={st.output}")
    return st


def assert_close(a: float, b: float, tol: float, what: str):
    if abs(a - b) > tol:
        raise AssertionError(f"{what}: expected {b}, got {a} (tol {tol})")


def main():
    psu_a = MP71050x(
        "PSU_A",
        PsuTransportUDP(psu_ip=PSU_IP, psu_port=PSU_PORT, local_ip=LOCAL_IP, local_port=LOCAL_PORT),
    )

    ch1 = psu_a.channel(CH)

    banner("1) Identify + initial status")
    dev = psu_a.identify(refresh=True)
    print("Identify:", dev)
    show_status(psu_a, "initial")

    banner("2) Basic UI toggles: lock/unlock + beep")
    print("Locking front panel...")
    psu_a.lock_front_panel(True)   # LOCK:1 :contentReference[oaicite:1]{index=1}
    time.sleep(PANEL_DELAY)

    print("Enabling beep...")
    psu_a.beep(True)               # BEEP:1 :contentReference[oaicite:2]{index=2}
    time.sleep(PANEL_DELAY)

    print("Disabling beep...")
    psu_a.beep(False)
    time.sleep(PANEL_DELAY)

    print("Unlocking front panel...")
    psu_a.lock_front_panel(False)
    time.sleep(PANEL_DELAY)

    banner("3) Ensure outputs OFF (safety)")
    psu_a.set_output(None, False)  # OUT1234:0 :contentReference[oaicite:3]{index=3}
    time.sleep(PANEL_DELAY)
    show_status(psu_a, "all off")

    banner("4) Setpoint test: VSET/ISET + query back")
    for v, i in [(V_LOW, I_LOW), (V_MID, I_MID), (V_HIGH, I_HIGH), (V_MID, I_LOW)]:
        print(f"Setting CH{CH} V={v:.3f} I={i:.3f}")
        ch1.set_voltage(v)         # VSET<X>:... :contentReference[oaicite:4]{index=4}
        ch1.set_current_limit(i)   # ISET<X>:... :contentReference[oaicite:5]{index=5}
        time.sleep(PANEL_DELAY)

        vq = ch1.get_voltage_setpoint()  # VSET<X>? :contentReference[oaicite:6]{index=6}
        iq = ch1.get_current_setpoint()  # ISET<X>? :contentReference[oaicite:7]{index=7}
        print(f"Queried setpoints: VSET={vq:.3f} ISET={iq:.3f}")

        # Use loose tolerances in case firmware rounds differently
        assert_close(vq, v, tol=0.010, what="VSET")
        assert_close(iq, i, tol=0.010, what="ISET")

    banner("5) Protection test: OVP/OCP set+enable+query")
    # Set slightly above the set voltage/current
    ovp_level = V_HIGH + 0.500
    ocp_level = I_HIGH + 0.100

    print(f"Setting OVP={ovp_level:.3f}V and enabling OVP...")
    ch1.set_ovp(ovp_level, enabled=True)   # OVPSET + OVP :contentReference[oaicite:8]{index=8}
    time.sleep(PANEL_DELAY)
    ovp_v, ovp_en = ch1.get_ovp()
    print("OVP readback:", ovp_v, "enabled:", ovp_en)

    print(f"Setting OCP={ocp_level:.3f}A and enabling OCP...")
    ch1.set_ocp(ocp_level, enabled=True)   # OCPSET + OCP :contentReference[oaicite:9]{index=9}
    time.sleep(PANEL_DELAY)
    ocp_a, ocp_en = ch1.get_ocp()
    print("OCP readback:", ocp_a, "enabled:", ocp_en)

    banner("6) Output ON/OFF + readback measurements (no load expected)")
    print("Turning CH1 output ON...")
    ch1.output(True)  # OUT1:1 :contentReference[oaicite:10]{index=10}
    time.sleep(PANEL_DELAY)

    show_status(psu_a, "ch1 on")

    vout = ch1.measure_voltage()  # VOUT<X>? :contentReference[oaicite:11]{index=11}
    iout = ch1.measure_current()  # IOUT<X>? :contentReference[oaicite:12]{index=12}
    print(f"Measured: VOUT={vout:.3f} IOUT={iout:.3f} (with no load, IOUT ~ 0)")

    print("Turning CH1 output OFF...")
    ch1.output(False)
    time.sleep(PANEL_DELAY)
    show_status(psu_a, "ch1 off")

    banner("7) Manual stepping test (VSTEP/VUP/VDOWN and ISTEP/IUP/IDOWN)")
    # Voltage manual stepping changes the setpoint in increments
    base_v = 1.000
    ch1.set_voltage(base_v)
    ch1.set_manual_voltage_step(0.250)  # VSTEP :contentReference[oaicite:13]{index=13}
    time.sleep(PANEL_DELAY)

    print("Voltage step up x3")
    for _ in range(3):
        ch1.voltage_step_up()  # VUP :contentReference[oaicite:14]{index=14}
        time.sleep(PANEL_DELAY)
        print("VSET now:", ch1.get_voltage_setpoint())

    print("Voltage step down x2")
    for _ in range(2):
        ch1.voltage_step_down()  # VDOWN :contentReference[oaicite:15]{index=15}
        time.sleep(PANEL_DELAY)
        print("VSET now:", ch1.get_voltage_setpoint())

    # Current manual stepping
    base_i = 0.100
    ch1.set_current_limit(base_i)
    ch1.set_manual_current_step(0.050)  # ISTEP :contentReference[oaicite:16]{index=16}
    time.sleep(PANEL_DELAY)

    print("Current step up x2")
    for _ in range(2):
        ch1.current_step_up()  # IUP :contentReference[oaicite:17]{index=17}
        time.sleep(PANEL_DELAY)
        print("ISET now:", ch1.get_current_setpoint())

    print("Current step down x1")
    ch1.current_step_down()  # IDOWN :contentReference[oaicite:18]{index=18}
    time.sleep(PANEL_DELAY)
    print("ISET now:", ch1.get_current_setpoint())

    banner("8) LIST programming test (edit + length + cycles + save)")
    # This only programs list tables; it doesn't necessarily run them.
    list_id = 1
    print(f"Programming LIST{list_id} on CH{CH} with a couple of steps...")
    # Example in doc: LISTCH1:2,3,12.5,2.2,1.5 :contentReference[oaicite:19]{index=19}
    ch1.list_set_step(list_id=list_id, step=1, volts=1.000, amps=0.100, dwell_s=0.500)
    ch1.list_set_step(list_id=list_id, step=2, volts=2.000, amps=0.150, dwell_s=0.500)
    ch1.list_set_length(list_id=list_id, length=2)         # LISTLCH :contentReference[oaicite:20]{index=20}
    ch1.list_set_cycles(list_id=list_id, cycles=3)          # LISTCCH :contentReference[oaicite:21]{index=21}
    ch1.list_save(list_id=list_id)                          # LISTSCH :contentReference[oaicite:22]{index=22}
    print("LIST programmed and saved.")
    time.sleep(PANEL_DELAY)

    banner("9) External trigger/switch/comp toggles")
    print("External trigger ON then OFF")
    ch1.external_trigger(True)  # EXIT :contentReference[oaicite:23]{index=23}
    time.sleep(PANEL_DELAY)
    ch1.external_trigger(False)
    time.sleep(PANEL_DELAY)

    print("External switch ON then OFF")
    ch1.external_switch(True)   # EXON :contentReference[oaicite:24]{index=24}
    time.sleep(PANEL_DELAY)
    ch1.external_switch(False)
    time.sleep(PANEL_DELAY)

    print("External compensation ON then OFF")
    ch1.external_comp(True)     # COMP :contentReference[oaicite:25]{index=25}
    time.sleep(PANEL_DELAY)
    ch1.external_comp(False)
    time.sleep(PANEL_DELAY)

    banner("10) Optional: save/recall panel profiles (0-9)")
    # WARNING: This changes stored presets on the PSU.
    # Uncomment if you want to verify functionality.
    # psu_a.save_profile(9)   # SAV9 :contentReference[oaicite:26]{index=26}
    # time.sleep(PANEL_DELAY)
    # psu_a.recall_profile(9) # RCL9 :contentReference[oaicite:27]{index=27}
    # time.sleep(PANEL_DELAY)
    print("Skipped by default (uncomment to test).")

    banner("11) Cleanup: outputs OFF, restore benign setpoints")
    psu_a.set_output(None, False)
    ch1.set_voltage(0.0)
    ch1.set_current_limit(0.0)
    time.sleep(PANEL_DELAY)
    show_status(psu_a, "final")

    print("\nAll tests complete.")


if __name__ == "__main__":
    main()


