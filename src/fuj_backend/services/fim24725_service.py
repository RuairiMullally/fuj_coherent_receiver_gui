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

        # Thread safety: RLock allows reentrant calls (e.g., shutdown -> _emergency_shutdown)
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

        # Register fault callback to trigger emergency shutdown
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
            self._emergency_shutdown_unlocked()

    def _emergency_shutdown_unlocked(self) -> None:
        """Immediate safe shutdown on fault (internal, no lock).

        Best-effort shutdown that continues even if individual
        operations fail. Logs errors but does not raise.

        Note: Caller must hold _lock or ensure exclusive access.
        """
        self._logger.warning("Emergency shutdown triggered")

        # First priority: disable module (SD = DISABLE)
        try:
            self._mcu.set_shutdown(disable=True)
        except Exception as e:
            self._logger.error(f"MCU SD disable failed: {e}")

        # Second priority: disable all rails
        try:
            self._rails.disable_all_rails()
        except Exception as e:
            self._logger.error(f"Rail disable failed: {e}")

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
        1. Verify safe initial state
        2. Program protections and setpoints (OVP/OCP/Vset/Iset per config)
        3. Enable VCC, verify
        4. Enable VPD, verify
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

            # Step 1: Verify initial safe state
            self._ensure_safe_initial_state()

            # Step 2: Program all protections (sets OVP/OCP/Vset/Iset per config)
            self._program_protections()

            # Step 3: Enable VCC, verify
            self._enable_vcc()

            # Step 4: Enable VPD, verify
            self._enable_vpd()

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
        self._logger.info("Step 3: Enabling VCC_3V3")
        self._rails.enable_rail(RailName.VCC_3V3)
        time.sleep(0.500)  # Brief settling

        if not self._rails.verify_rail(RailName.VCC_3V3):
            measurement = self._rails.measure_rail(RailName.VCC_3V3)
            raise VerificationError(
                RailName.VCC_3V3,
                "3.3V / 720-800mA",
                f"{measurement.voltage:.3f}V / {measurement.current:.3f}A",
            )

    def _enable_vpd(self) -> None:
        """Enable VPD rail and verify."""
        self._logger.info("Step 4: Enabling VPD_5V0")
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
        """Enable control rail outputs."""
        self._logger.info("Step 6: Enabling control rails")

        for rail in RailRegistry.CONTROL_RAILS:
            self._rails.enable_rail(rail)

    def _enable_module_output(self, mode: OperatingMode) -> None:
        """Enable module output (SD = ENABLE)."""
        self._logger.info(f"Step 8: Enabling output (mode={mode.value})")
        self._set_mode_verified(mode)
        self._state.set_mode(mode)
        self._set_sd_verified(False)  # SD = ENABLE (LOW)

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

        Follows the shutdown algorithm:
        1. SD = DISABLE
        2. Return controls to safe values
        3. Disable VPD
        4. Disable VCC
        5. Disable control rails

        Safe to call from any state. Does not raise on failure.
        """
        self._logger.info("=== Starting FIM24725 Shutdown Sequence ===")

        try:
            if self._state.state not in (SystemState.OFF, SystemState.FAULT):
                self._state.transition_to(SystemState.SHUTTING_DOWN)

            # Step 1: SD = DISABLE
            self._logger.info("Step 1: Disabling module output (SD=HIGH)")
            try:
                self._mcu.set_shutdown(disable=True)
            except Exception as e:
                self._logger.error(f"SD disable failed: {e}")

            # Step 2: Return controls to safe values
            self._logger.info("Step 2: Returning controls to safe values")
            try:
                self._rails.set_voa(0.0)
                self._rails.set_oa_x(0.0)
                self._rails.set_oa_y(0.0)
                # Force GA to 0 regardless of mode
                self._rails.set_ga_x(0.0, OperatingMode.MGC)
                self._rails.set_ga_y(0.0, OperatingMode.MGC)
            except Exception as e:
                self._logger.error(f"Control reset failed: {e}")

            # Step 3: Disable VPD
            self._logger.info("Step 3: Disabling VPD_5V0")
            try:
                self._rails.disable_rail(RailName.VPD_5V0)
            except Exception as e:
                self._logger.error(f"VPD disable failed: {e}")

            # Step 4: Disable VCC
            self._logger.info("Step 4: Disabling VCC_3V3")
            try:
                self._rails.disable_rail(RailName.VCC_3V3)
            except Exception as e:
                self._logger.error(f"VCC disable failed: {e}")

            # Step 5: Disable control rails
            self._logger.info("Step 5: Disabling control rails")
            for rail in RailRegistry.CONTROL_RAILS:
                try:
                    self._rails.disable_rail(rail)
                except Exception as e:
                    self._logger.error(f"{rail.value} disable failed: {e}")

            self._state.transition_to(SystemState.OFF)
            self._logger.info("=== Shutdown Complete ===")

        except Exception as e:
            self._logger.error(f"Shutdown error: {e}")
            self._emergency_shutdown_unlocked()

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
        self._rails.set_voa(volts)

    @synchronized
    def set_oa_x(self, volts: float) -> None:
        """
        Set Output Amplitude X voltage.

        Controls final output amplitude for X channel.
        Does not affect noise profile.

        Args:
            volts: Target voltage, clamped to 0-3.3V

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        self._rails.set_oa_x(volts)

    @synchronized
    def set_oa_y(self, volts: float) -> None:
        """
        Set Output Amplitude Y voltage.

        Controls final output amplitude for Y channel.
        Does not affect noise profile.

        Args:
            volts: Target voltage, clamped to 0-3.3V

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        self._rails.set_oa_y(volts)

    @synchronized
    def set_ga_x(self, volts: float) -> None:
        """
        Set Gain Adjust X voltage (MGC mode only).

        Controls internal gain for X channel. Affects noise profile
        and output swing. Mainly useful for lab characterization.

        Args:
            volts: Target voltage, clamped to 0-3.3V

        Note:
            Ignored if system is in AGC mode (logs warning).

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        self._rails.set_ga_x(volts, self._state.mode)

    @synchronized
    def set_ga_y(self, volts: float) -> None:
        """
        Set Gain Adjust Y voltage (MGC mode only).

        Controls internal gain for Y channel. Affects noise profile
        and output swing. Mainly useful for lab characterization.

        Args:
            volts: Target voltage, clamped to 0-3.3V

        Note:
            Ignored if system is in AGC mode (logs warning).

        Raises:
            StateError: If system not ready
        """
        self._state.require_state(SystemState.READY)
        self._rails.set_ga_y(volts, self._state.mode)

    # --- Mode Control ---

    @synchronized
    def set_mode(self, mode: OperatingMode) -> None:
        """
        Switch operating mode between AGC and MGC.

        In AGC mode, GA channels are ignored (internal automatic control).
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

        # In AGC mode, hold GA at safe value
        if mode == OperatingMode.AGC:
            self._rails.set_ga_x(0.0, OperatingMode.MGC)
            self._rails.set_ga_y(0.0, OperatingMode.MGC)

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

        if self._state.state == SystemState.READY:
            try:
                pi = self._mcu.read_peak_indicators()
                mpd = self._mcu.read_mpd()
            except Exception as e:
                self._logger.warning(f"MCU read failed: {e}")

        return SystemSnapshot(
            state=self._state.state,
            mode=self._state.mode,
            rails=self._rails.measure_all_rails(),
            sd_enabled=(self._state.state == SystemState.READY),
            peak_indicators=pi,
            mpd_value=mpd,
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
        Read monitor photodiode value.

        MPD measures optical input power independent of gain settings.
        MPD = optical reality, PI = electrical state.

        Returns:
            MPD reading value

        Raises:
            MCUError: If MCU communication fails (also triggers fault + shutdown)
        """
        try:
            return self._mcu.read_mpd()
        except MCUError as e:
            self._fault_on_mcu_error("read_mpd", e)
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
            lambda v: self._rails.set_ga_x(v, self._state.mode)
            if channel.upper() == "X"
            else self._rails.set_ga_y(v, self._state.mode)
        )

        while (step_signed > 0 and current <= end) or (
            step_signed < 0 and current >= end
        ):
            set_ga(current)
            time.sleep(dwell_ms / 1000.0)
            pi = self._mcu.read_peak_indicators()
            results.append((current, pi))
            current += step_signed

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

            try:
                self._mcu.set_shutdown(disable=True)
            except Exception as e:
                self._logger.error(f"SD disable failed: {e}")

            try:
                self._rails.set_voa(0.0)
                self._rails.set_oa_x(0.0)
                self._rails.set_oa_y(0.0)
                self._rails.set_ga_x(0.0, OperatingMode.MGC)
                self._rails.set_ga_y(0.0, OperatingMode.MGC)
            except Exception as e:
                self._logger.error(f"Control reset failed: {e}")

            try:
                self._rails.disable_rail(RailName.VPD_5V0)
            except Exception as e:
                self._logger.error(f"VPD disable failed: {e}")

            try:
                self._rails.disable_rail(RailName.VCC_3V3)
            except Exception as e:
                self._logger.error(f"VCC disable failed: {e}")

            for rail in RailRegistry.CONTROL_RAILS:
                try:
                    self._rails.disable_rail(rail)
                except Exception as e:
                    self._logger.error(f"{rail.value} disable failed: {e}")

            self._state.transition_to(SystemState.OFF)
            self._logger.info("=== Shutdown Complete ===")

        except Exception as e:
            self._logger.error(f"Shutdown error: {e}")
            self._emergency_shutdown_unlocked()

    def __enter__(self) -> FIM24725Service:
        return self

    def __exit__(self, _exc_type: object, _exc_val: object, _exc_tb: object) -> None:
        self.close()
