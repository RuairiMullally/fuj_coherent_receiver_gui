"""
FIM24725 Coherent Receiver Service.

Main facade providing high-level device control with safety enforcement.
This is the primary entry point for application code interacting with the
FIM24725 coherent optical receiver module.

Features:
- Safe power sequencing (bring-up/shutdown)
- Named rail control with bounds checking
- State management and fault handling
- Operating mode control (AGC/MGC)
- Thread-safe operations
"""

from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Callable, Optional, TypeVar

from ..hardware.psu_hal import MP71050x, PsuTransportUDP

from .exceptions import MCUError, VerificationError
from .logging import get_service_logger
from .mcu_interface import MCUInterface, MockMCU
from .models import (
    FaultInfo,
    OperatingMode,
    PeakIndicators,
    RailName,
    SystemSnapshot,
    SystemState,
)
from .rail_config import RailRegistry
from .rail_controller import RailController
from .state_machine import StateMachine

T = TypeVar("T")


def synchronized(method: Callable[..., T]) -> Callable[..., T]:
    """Decorator to synchronize method access with the service lock.

    Uses RLock to allow reentrant calls from the same thread.
    """

    @wraps(method)
    def wrapper(self: FIM24725Service, *args: object, **kwargs: object) -> T:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class FIM24725Service:
    """
    High-level service for FIM24725 coherent receiver control.

    This is the primary entry point for application code. It provides:
    - Safe power sequencing (bring-up/shutdown)
    - Named rail control with bounds checking
    - State management and fault handling
    - Operating mode control (AGC/MGC)

    Thread Safety:
        All public methods are thread-safe. The service uses an RLock to
        serialize access, preventing race conditions between concurrent
        callers. Read-only properties are also protected.

    Usage:
        service = FIM24725Service(
            psu1_ip="192.168.1.10", psu1_port=20001,
            psu2_ip="192.168.1.11", psu2_port=20002,
        )
        try:
            service.startup()
            service.set_voa(2.4)
            service.set_oa_x(1.65)
        finally:
            service.shutdown()

    Context manager usage:
        with FIM24725Service(...) as service:
            service.startup()
            # ... operations ...
        # Automatic shutdown and cleanup
    """

    SETTLING_TIME_MS: int = 500  # Default settling time in milliseconds

    def __init__(
        self,
        psu1_ip: str,
        psu1_port: int,
        psu2_ip: str,
        psu2_port: int,
        psu1_local_ip: Optional[str] = None,
        psu2_local_ip: Optional[str] = None,
        mcu: Optional[MCUInterface] = None,
    ) -> None:
        """
        Initialize the FIM24725 service.

        Args:
            psu1_ip: IP address of PSU1 (VCC, VPD, VOA)
            psu1_port: UDP port for PSU1
            psu2_ip: IP address of PSU2 (GA, OA controls)
            psu2_port: UDP port for PSU2
            psu1_local_ip: Local NIC IP to bind for PSU1 (required when
                           each PSU is on a separate ethernet adapter)
            psu2_local_ip: Local NIC IP to bind for PSU2
            mcu: MCU interface implementation (defaults to MockMCU)
        """
        # Initialize logger first (ensures file handler is set up)
        self._logger = get_service_logger().getChild("service")

        # Thread safety: RLock allows reentrant calls (e.g., shutdown -> _assert_sd_disable)
        self._lock = threading.RLock()

        # Initialize HAL connections
        self._transport1 = PsuTransportUDP(
            psu1_ip, psu_port=psu1_port, local_ip=psu1_local_ip, local_port=psu1_port
        )
        self._transport2 = PsuTransportUDP(
            psu2_ip, psu_port=psu2_port, local_ip=psu2_local_ip, local_port=psu2_port
        )
        self._psu1 = MP71050x("PSU1", self._transport1)
        self._psu2 = MP71050x("PSU2", self._transport2)

        # Initialize components
        self._rails = RailController(self._psu1, self._psu2)
        self._state = StateMachine()
        self._mcu = mcu or MockMCU()

        # Register fault callback to assert SD disable on fault
        self._state.add_state_callback(self._on_state_change)

        self._logger.info(
            f"FIM24725Service initialized: PSU1={psu1_ip}:{psu1_port}, "
            f"PSU2={psu2_ip}:{psu2_port}"
        )

    def _on_state_change(
        self, old_state: SystemState, new_state: SystemState
    ) -> None:
        """Handle state changes, particularly faults.

        Note: Called while _lock is held (from state machine operations).
        """
        if new_state == SystemState.FAULT:
            self._assert_sd_disable_unlocked()

    def _assert_sd_disable_unlocked(self) -> None:
        """Assert SD disable on fault (internal, no lock).

        Only disables module output via SD pin — does NOT attempt
        to power down rails.  Full rail shutdown requires an explicit
        call to shutdown().

        Rationale: during a fault, issuing PSU commands over UDP may
        make things worse or mask the real issue.  The SD pin disable
        is the most critical safety action and is a single serial
        command to the MCU.

        Note: Caller must hold _lock or ensure exclusive access.
        """
        self._logger.warning("Fault response: asserting SD disable (module output off)")
        try:
            self._mcu.set_shutdown(disable=True)
        except Exception as e:
            self._logger.error(f"MCU SD disable failed during fault response: {e}")

    # --- MCU error → fault helper ---

    def _fault_on_mcu_error(self, context: str, e: MCUError) -> None:
        """Transition to FAULT state on an MCU communication error.

        Args:
            context: Brief description of the operation that failed.
            e: The MCUError that was caught.
        """
        self._logger.error(f"MCU error during {context}: {e}")
        self._state.fault(
            FaultInfo(
                message=f"MCU error during {context}: {e}",
                timestamp=time.time(),
                recoverable=False,
            )
        )

    def _fault_on_rail_error(self, context: str, e: VerificationError) -> None:
        """Transition to FAULT state on a rail voltage verification failure.

        Args:
            context: Brief description of the operation that failed.
            e: The VerificationError that was caught.
        """
        self._logger.error(f"Rail verification error during {context}: {e}")
        self._state.fault(
            FaultInfo(
                message=f"Rail verification error during {context}: {e}",
                timestamp=time.time(),
                recoverable=False,
            )
        )

    # --- MCU verification helpers ---

    def _set_sd_verified(self, disable: bool) -> None:
        """Set SD state and verify MCU confirmation.

        Raises:
            MCUError: If MCU returns a state that doesn't match expected.
        """
        actual = self._mcu.set_shutdown(disable)
        if actual != disable:
            expected_str = "DISABLED" if disable else "ENABLED"
            actual_str = "DISABLED" if actual else "ENABLED"
            raise MCUError(
                f"SD state mismatch: expected {expected_str}, got {actual_str}"
            )

    def _set_mode_verified(self, mode: OperatingMode) -> None:
        """Set mode and verify MCU confirmation.

        Raises:
            MCUError: If MCU returns a mode that doesn't match expected.
        """
        actual = self._mcu.set_mode(mode)
        if actual != mode:
            raise MCUError(
                f"Mode mismatch: expected {mode.value}, got {actual.value}"
            )

    # --- Properties (thread-safe) ---

    @property
    def state(self) -> SystemState:
        """Current system state."""
        with self._lock:
            return self._state.state

    @property
    def mode(self) -> OperatingMode:
        """Current operating mode (AGC/MGC)."""
        with self._lock:
            return self._state.mode

    @property
    def is_ready(self) -> bool:
        """True if system is ready for operation."""
        with self._lock:
            return self._state.is_ready()

    @property
    def is_fault(self) -> bool:
        """True if system is in fault state."""
        with self._lock:
            return self._state.is_fault()

    @property
    def fault_info(self) -> Optional[FaultInfo]:
        """Fault information if in FAULT state."""
        with self._lock:
            return self._state.fault_info

    # --- Startup Sequence ---

    @synchronized
    def startup(self, mode: OperatingMode = OperatingMode.AGC) -> None:
        """
        Execute full startup sequence.

        Follows the bring-up algorithm:
        0. Lock PSU front panel buttons
        1. Verify safe initial state
        2. Program protections and setpoints (OVP/OCP/Vset/Iset per config)
        3. Enable VPD, verify  ← photodiode bias MUST come before amplifier supply
        4. Enable VCC, verify
        5. Set initial control values
        6. Enable control rails
        7. Settling delay
        8. Enable module output (SD = ENABLE)
        9. Validate PI readings

        Args:
            mode: Initial operating mode (default AGC)

        Raises:
            StateError: If not in OFF state
            SequenceError: If any startup step fails
            MCUError: If MCU communication fails
            VerificationError: If rail verification fails
        """
        self._state.require_state(SystemState.OFF)
        self._logger.info("=== Starting FIM24725 Startup Sequence ===")

        try:
            self._state.transition_to(SystemState.STARTING)

            # Step 0: Lock PSU front panels (prevents accidental physical button presses)
            self._logger.info("Step 0: Locking PSU front panels")
            self._rails.lock_panels()

            # Step 1: Verify initial safe state
            self._ensure_safe_initial_state()

            # Step 2: Program all protections (sets OVP/OCP/Vset/Iset per config)
            self._program_protections()

            # Step 3: Enable VPD, verify (photodiode bias FIRST per app notes)
            self._enable_vpd()

            # Step 4: Enable VCC, verify (amplifier supply SECOND per app notes)
            self._enable_vcc()

            # Step 5: Set initial control values
            self._set_initial_controls()

            # Step 6: Enable PSU2 control outputs
            self._enable_control_rails()

            # Step 7: Settling time
            self._logger.info(f"Settling for {self.SETTLING_TIME_MS}ms")
            time.sleep(self.SETTLING_TIME_MS / 1000.0)

            # Step 8: Enable module output (SD = ENABLE)
            self._enable_module_output(mode)

            # Step 9: Validate PI readings
            self._validate_peak_indicators()

            self._state.transition_to(SystemState.READY)
            self._logger.info("=== Startup Complete ===")

        except Exception as e:
            self._logger.error(f"Startup failed: {e}")
            self._state.fault(
                FaultInfo(
                    message=f"Startup failed: {e}",
                    timestamp=time.time(),
                    recoverable=True,
                )
            )
            raise

    def _ensure_safe_initial_state(self) -> None:
        """Verify/set safe initial state before startup."""
        self._logger.info("Step 1: Ensuring safe initial state")

        # Check MCU connection
        if not self._mcu.is_connected():
            raise MCUError("MCU not responding")

        # Ensure SD disabled, AGC mode (safe defaults)
        self._set_sd_verified(True)
        self._set_mode_verified(OperatingMode.AGC)

        # Ensure all outputs off
        self._rails.disable_all_rails()

    def _program_protections(self) -> None:
        """Program OVP/OCP and setpoints for all rails."""
        self._logger.info("Step 2: Programming protections and setpoints")
        self._rails.program_all_protections()

    def _enable_vcc(self) -> None:
        """Enable VCC rail and verify."""
        self._logger.info("Step 4: Enabling VCC_3V3")
        self._rails.enable_rail(RailName.VCC_3V3)
        time.sleep(0.500)  # Brief settling

        if not self._rails.verify_rail(RailName.VCC_3V3):
            measurement = self._rails.measure_rail(RailName.VCC_3V3)
            raise VerificationError(
                RailName.VCC_3V3,
                "3.3V / 280-480mA",
                f"{measurement.voltage:.3f}V / {measurement.current:.3f}A",
            )

    def _enable_vpd(self) -> None:
        """Enable VPD rail and verify."""
        self._logger.info("Step 3: Enabling VPD_5V0")
        self._rails.enable_rail(RailName.VPD_5V0)
        time.sleep(0.500)  # 500ms settling for VPD_5V0

        if not self._rails.verify_rail(RailName.VPD_5V0):
            measurement = self._rails.measure_rail(RailName.VPD_5V0)
            raise VerificationError(
                RailName.VPD_5V0,
                "5.0V",
                f"{measurement.voltage:.3f}V",
            )

    def _set_initial_controls(self) -> None:
        """Set initial control values from rail config (nominal_voltage)."""
        self._logger.info("Step 5: Setting initial control values")

        for rail in RailRegistry.CONTROL_RAILS:
            config = RailRegistry.get(rail)
            ch = self._rails._get_channel(rail)
            ch.set_voltage(config.nominal_voltage)
            ch.set_current_limit(config.nominal_current)

    def _enable_control_rails(self) -> None:
        """Enable control rail outputs; implicitly verify PSU2 is reachable."""
        self._logger.info("Step 6: Enabling control rails")

        for rail in RailRegistry.CONTROL_RAILS:
            self._rails.enable_rail(rail)

        time.sleep(0.300)  # settling

        # Confirm PSU1 control is responsive and VOA_CTRL is at nominal.
        # socket.timeout propagates to startup's except block if PSU1 is unreachable.
        self._logger.info("Step 6a: Confirming PSU1 control reachable")
        voa_meas = self._rails.measure_rail(RailName.VOA_CTRL)
        voa_nominal = RailRegistry.get(RailName.VOA_CTRL).nominal_voltage
        if abs(voa_meas.voltage - voa_nominal) > 0.1:
            raise VerificationError(
                RailName.VOA_CTRL,
                f"{voa_nominal:.3f}V ±0.100V",
                f"{voa_meas.voltage:.3f}V",
            )
        self._logger.info(f"PSU1 control confirmed reachable — VOA_CTRL={voa_meas.voltage:.3f}V")

        # Confirm PSU2 is responsive and GA_X is at nominal (0V).
        # socket.timeout propagates to startup's except block if PSU2 is unreachable.
        self._logger.info("Step 6b: Confirming PSU2 reachable")
        ga_meas = self._rails.measure_rail(RailName.GA_X)
        ga_nominal = RailRegistry.get(RailName.GA_X).nominal_voltage
        if abs(ga_meas.voltage - ga_nominal) > 0.1:
            raise VerificationError(
                RailName.GA_X,
                f"{ga_nominal:.3f}V ±0.100V",
                f"{ga_meas.voltage:.3f}V",
            )
        self._logger.info(f"PSU2 confirmed reachable — GA_X={ga_meas.voltage:.3f}V")

    def _enable_module_output(self, mode: OperatingMode) -> None:
        """Enable module output (SD = ENABLE)."""
        self._logger.info(f"Step 8: Enabling output (mode={mode.value})")
        self._set_mode_verified(mode)
        self._state.set_mode(mode)
        self._set_sd_verified(False)  # SD = ENABLE → D2 HIGH → SD HIGH = shutdown disabled (module running)

    def _validate_peak_indicators(self) -> None:
        """Validate PI readings are not railed."""
        self._logger.info("Step 9: Validating peak indicators")
        pi = self._mcu.read_peak_indicators()

        # Check for railed values (0V or 2V)
        for name, value in [
            ("PI_XI", pi.pi_xi),
            ("PI_XQ", pi.pi_xq),
            ("PI_YI", pi.pi_yi),
            ("PI_YQ", pi.pi_yq),
        ]:
            if value < 0.1 or value > 1.9:
                self._logger.warning(f"{name} appears railed: {value:.3f}V")

    # --- Shutdown Sequence ---

    @synchronized
    def shutdown(self) -> None:
        """
        Execute orderly shutdown sequence.

        Follows the datasheet power-down sequence:
        1. SD = DISABLE (turn off optical/module output)
        2. Disable control rails (GA, OA, VOA → 0V at FIM24725 pins)
        3. Disable VCC_3V3 (amplifier supply off)
        4. Disable VPD_5V0 (photodiode supply off — LAST)

        Safe to call from any state. Does not raise on failure.
        """
        self._logger.info("=== Starting FIM24725 Shutdown Sequence ===")

        try:
            if self._state.state not in (SystemState.OFF, SystemState.FAULT):
                self._state.transition_to(SystemState.SHUTTING_DOWN)

            # Step 1: SD = DISABLE (D2 LOW → FIM24725 SD LOW = shutdown active)
            self._logger.info("Step 1: Disabling module output (D2 LOW → SD LOW = shutdown active)")
            try:
                self._set_sd_verified(True)
            except Exception as e:
                self._logger.error(f"SD disable failed: {e}")

            # Step 2: Disable control rails → 0V at FIM24725 pins (datasheet step 2)
            # Must happen before VCC to avoid driving control pins above VCC (0V).
            self._logger.info("Step 2: Disabling control rails (VOA, GA, OA → 0V)")
            for rail in RailRegistry.CONTROL_RAILS:
                try:
                    self._rails.disable_rail(rail)
                except Exception as e:
                    self._logger.error(f"{rail.value} disable failed: {e}")

            # Step 3: Disable VCC_3V3 (amplifier supply — datasheet step 3)
            self._logger.info("Step 3: Disabling VCC_3V3 (amplifier supply)")
            try:
                self._rails.disable_rail(RailName.VCC_3V3)
            except Exception as e:
                self._logger.error(f"VCC disable failed: {e}")

            # Step 4: Disable VPD_5V0 (photodiode supply — datasheet step 4, LAST)
            self._logger.info("Step 4: Disabling VPD_5V0 (photodiode supply, last)")
            try:
                self._rails.disable_rail(RailName.VPD_5V0)
            except Exception as e:
                self._logger.error(f"VPD disable failed: {e}")

            self._state.transition_to(SystemState.OFF)

            # Step 6: Unlock PSU front panels
            self._logger.info("Step 6: Unlocking PSU front panels")
            try:
                self._rails.unlock_panels()
            except Exception as e:
                self._logger.error(f"Panel unlock failed: {e}")

            self._logger.info("=== Shutdown Complete ===")

        except Exception as e:
            self._logger.error(f"Shutdown error: {e}")
            self._assert_sd_disable_unlocked()

    # --- Named Rail API ---

    @synchronized
    def set_voa(self, volts: float) -> None:
        """
        Set VOA (Variable Optical Attenuator) voltage.

        Higher voltage = more attenuation. No hardware damage from
        high setting, only affects signal quality.

        Args:
            volts: Target voltage, clamped to 0-4.8V

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        try:
            self._rails.set_voa(volts)
        except VerificationError as e:
            self._fault_on_rail_error("set_voa", e)
            raise

    @synchronized
    def set_oa_x(self, volts: float) -> None:
        """
        Set Output Amplitude X voltage.

        Controls final output amplitude for X channel.
        Does not affect noise profile.

        Args:
            volts: Target voltage, clamped to 0.5–2V (app notes AGC mode range)

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        try:
            self._rails.set_oa_x(volts)
        except VerificationError as e:
            self._fault_on_rail_error("set_oa_x", e)
            raise

    @synchronized
    def set_oa_y(self, volts: float) -> None:
        """
        Set Output Amplitude Y voltage.

        Controls final output amplitude for Y channel.
        Does not affect noise profile.

        Args:
            volts: Target voltage, clamped to 0.5–2V (app notes AGC mode range)

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        try:
            self._rails.set_oa_y(volts)
        except VerificationError as e:
            self._fault_on_rail_error("set_oa_y", e)
            raise

    @synchronized
    def set_ga_x(self, volts: float) -> None:
        """
        Set Gain Adjust X voltage.

        Controls internal gain for X channel. Affects noise profile
        and output swing. Mainly useful for lab characterization.

        Can be called in either AGC or MGC mode. In AGC mode the FIM24725
        hardware ignores the GA pin, so setting a value pre-stages it — the
        voltage takes effect immediately when the system switches to MGC.

        Args:
            volts: Target voltage, clamped to 0-3.3V

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        try:
            self._rails.set_ga_x(volts)
        except VerificationError as e:
            self._fault_on_rail_error("set_ga_x", e)
            raise

    @synchronized
    def set_ga_y(self, volts: float) -> None:
        """
        Set Gain Adjust Y voltage.

        Controls internal gain for Y channel. Affects noise profile
        and output swing. Mainly useful for lab characterization.

        Can be called in either AGC or MGC mode. In AGC mode the FIM24725
        hardware ignores the GA pin, so setting a value pre-stages it — the
        voltage takes effect immediately when the system switches to MGC.

        Args:
            volts: Target voltage, clamped to 0-3.3V

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        try:
            self._rails.set_ga_y(volts)
        except VerificationError as e:
            self._fault_on_rail_error("set_ga_y", e)
            raise

    # --- Mode Control ---

    @synchronized
    def set_mode(self, mode: OperatingMode) -> None:
        """
        Switch operating mode between AGC and MGC.

        In AGC mode, GA channels are ignored by the FIM24725 hardware
        (internal automatic gain control active). GA PSU outputs remain
        at their current voltage, enabling pre-staging: a GA value set
        while in AGC takes effect immediately when the system switches to MGC.

        In MGC mode, GA channels are active for manual gain control.

        Args:
            mode: Target operating mode

        Raises:
            StateError: If system not ready or during startup
            MCUError: If MCU communication fails (also triggers fault + shutdown)
        """
        self._state.require_state(SystemState.READY)
        try:
            self._set_mode_verified(mode)
        except MCUError as e:
            self._fault_on_mcu_error("set_mode", e)
            raise
        self._state.set_mode(mode)

    # --- Monitoring ---

    @synchronized
    def get_snapshot(self) -> SystemSnapshot:
        """
        Get complete system state snapshot.

        Returns all current state, measurements, and readings.

        Returns:
            SystemSnapshot with full system state
        """
        pi = None
        mpd = None
        rails: dict = {}

        mpd_n = None
        if self._state.state == SystemState.READY:
            try:
                pi = self._mcu.read_peak_indicators()
                mpd = self._mcu.read_mpd()
                mpd_n = self._mcu.read_mpd_n()
            except Exception as e:
                self._logger.warning(f"MCU read failed: {e}")
            try:
                rails = self._rails.measure_all_rails()
            except Exception as e:
                self._logger.warning(f"Rail measurement failed: {e}")

        return SystemSnapshot(
            state=self._state.state,
            mode=self._state.mode,
            rails=rails,
            sd_enabled=(self._state.state == SystemState.READY),
            peak_indicators=pi,
            mpd_value=mpd,
            mpd_n_value=mpd_n,
            fault_message=(
                self._state.fault_info.message if self._state.fault_info else None
            ),
        )

    @synchronized
    def read_peak_indicators(self) -> PeakIndicators:
        """
        Read peak indicator values from MCU.

        Values near 0V indicate power loss.
        Values near 2V indicate clipping.

        Returns:
            PeakIndicators with all 4 channel readings

        Raises:
            MCUError: If MCU communication fails (also triggers fault + shutdown)
        """
        try:
            return self._mcu.read_peak_indicators()
        except MCUError as e:
            self._fault_on_mcu_error("read_peak_indicators", e)
            raise

    @synchronized
    def read_mpd(self) -> float:
        """
        Read differential monitor photodiode value (MPD+ - MPD-).

        MPD measures optical input power independent of gain settings.
        MPD = optical reality, PI = electrical state.

        Returns:
            Differential MPD value (MPD+ - MPD-)

        Raises:
            MCUError: If MCU communication fails (also triggers fault + shutdown)
        """
        try:
            return self._mcu.read_mpd()
        except MCUError as e:
            self._fault_on_mcu_error("read_mpd", e)
            raise

    @synchronized
    def read_mpd_n(self) -> float:
        """
        Read MPD- (negative terminal) raw value.

        Returns:
            MPD- voltage (0–2V)

        Raises:
            MCUError: If MCU communication fails (also triggers fault + shutdown)
        """
        try:
            return self._mcu.read_mpd_n()
        except MCUError as e:
            self._fault_on_mcu_error("read_mpd_n", e)
            raise

    # --- Advanced Operations ---

    @synchronized
    def sweep_ga(
        self,
        channel: str,
        start: float,
        end: float,
        step: float,
        dwell_ms: float = 100,
    ) -> list[tuple[float, PeakIndicators]]:
        """
        Sweep GA voltage and record PI at each step (MGC mode only).

        Useful for characterizing gain response.

        Args:
            channel: "X" or "Y"
            start: Starting voltage
            end: Ending voltage
            step: Voltage step size
            dwell_ms: Time to wait at each step (milliseconds)

        Returns:
            List of (voltage, peak_indicators) tuples

        Raises:
            StateError: If not ready or not in MGC mode
        """
        from .exceptions import StateError

        self._state.require_state(SystemState.READY)

        if self._state.mode != OperatingMode.MGC:
            raise StateError("GA sweep requires MGC mode", self._state.state)

        results: list[tuple[float, PeakIndicators]] = []
        current = start
        step_signed = step if end > start else -step

        # Use internal methods to avoid re-acquiring lock
        set_ga = (
            lambda v: self._rails.set_ga_x(v)
            if channel.upper() == "X"
            else self._rails.set_ga_y(v)
        )

        try:
            while (step_signed > 0 and current <= end) or (
                step_signed < 0 and current >= end
            ):
                set_ga(current)
                time.sleep(dwell_ms / 1000.0)
                pi = self._mcu.read_peak_indicators()
                results.append((current, pi))
                current += step_signed
        except VerificationError as e:
            self._fault_on_rail_error("sweep_ga", e)
            raise

        return results

    # --- Cleanup ---

    @synchronized
    def close(self) -> None:
        """Clean up resources.

        Performs shutdown if not already off, then closes transports.
        """
        if self._state.state != SystemState.OFF:
            # Call internal shutdown since we already hold the lock
            self._shutdown_internal()
        self._transport1.close()
        self._transport2.close()
        self._logger.info("FIM24725Service closed")

    def _shutdown_internal(self) -> None:
        """Internal shutdown without acquiring lock (for use by close())."""
        self._logger.info("=== Starting FIM24725 Shutdown Sequence ===")

        try:
            if self._state.state not in (SystemState.OFF, SystemState.FAULT):
                self._state.transition_to(SystemState.SHUTTING_DOWN)

            # Step 1: SD = DISABLE (D2 LOW → FIM24725 SD LOW = shutdown active)
            try:
                self._set_sd_verified(True)
            except Exception as e:
                self._logger.error(f"SD disable failed: {e}")

            # Step 2: Disable control rails → 0V at FIM24725 pins (datasheet step 2)
            # Must happen before VCC to avoid driving control pins above VCC (0V).
            for rail in RailRegistry.CONTROL_RAILS:
                try:
                    self._rails.disable_rail(rail)
                except Exception as e:
                    self._logger.error(f"{rail.value} disable failed: {e}")

            # Step 3: Disable VCC_3V3 (amplifier supply — datasheet step 3)
            try:
                self._rails.disable_rail(RailName.VCC_3V3)
            except Exception as e:
                self._logger.error(f"VCC disable failed: {e}")

            # Step 4: Disable VPD_5V0 (photodiode supply — datasheet step 4, LAST)
            try:
                self._rails.disable_rail(RailName.VPD_5V0)
            except Exception as e:
                self._logger.error(f"VPD disable failed: {e}")

            self._state.transition_to(SystemState.OFF)

            try:
                self._rails.unlock_panels()
            except Exception as e:
                self._logger.error(f"Panel unlock failed: {e}")

            self._logger.info("=== Shutdown Complete ===")

        except Exception as e:
            self._logger.error(f"Shutdown error: {e}")
            self._assert_sd_disable_unlocked()

    def __enter__(self) -> FIM24725Service:
        return self

    def __exit__(self, _exc_type: object, _exc_val: object, _exc_tb: object) -> None:
        self.close()
