"""Rail controller - named rail access with bounds enforcement.

Provides a high-level API for controlling FIM24725 rails through the HAL,
hiding PSU/channel details and enforcing voltage/current bounds.
"""

from __future__ import annotations

import time
from typing import Optional

from ..hardware.psu_hal import Channel, MP71050x

from .exceptions import BoundsError, VerificationError
from .logging import get_service_logger
from .models import RailMeasurement, RailName, RailState
from .rail_config import RailRegistry


class RailController:
    """
    Controls individual rails through the HAL.

    Provides named rail access, enforces bounds, and tracks rail states.
    Hides PSU/channel details from higher-level logic.
    """

    def __init__(
        self,
        psu1: MP71050x,
        psu2: MP71050x,
    ) -> None:
        """Initialize rail controller.

        Args:
            psu1: HAL instance for PSU1 (VCC, VPD, VOA)
            psu2: HAL instance for PSU2 (GA, OA controls)
        """
        self._logger = get_service_logger().getChild("rails")
        self._psus = {"PSU1": psu1, "PSU2": psu2}
        self._channel_cache: dict[RailName, Channel] = {}
        self._rail_states: dict[RailName, RailState] = {
            rail: RailState.OFF for rail in RailName
        }

    def _get_channel(self, rail: RailName) -> Channel:
        """Get HAL Channel object for a rail.

        Caches channel objects for efficiency.
        """
        if rail not in self._channel_cache:
            config = RailRegistry.get(rail)
            psu = self._psus[config.psu_name]
            self._channel_cache[rail] = psu.channel(config.channel)
        return self._channel_cache[rail]

    def _clamp_and_validate(
        self,
        rail: RailName,
        volts: float,
        clamp: bool = True,
    ) -> float:
        """Validate voltage against rail bounds, optionally clamping.

        Args:
            rail: Target rail
            volts: Requested voltage
            clamp: If True, clamp to bounds; if False, raise BoundsError

        Returns:
            Validated (and possibly clamped) voltage

        Raises:
            BoundsError: If clamp=False and value is out of bounds
        """
        config = RailRegistry.get(rail)

        if volts < config.min_voltage:
            if clamp:
                self._logger.warning(
                    f"{rail.value}: Clamping {volts:.3f}V to min {config.min_voltage:.3f}V"
                )
                return config.min_voltage
            raise BoundsError(rail, volts, config.min_voltage, config.max_voltage)

        if volts > config.max_voltage:
            if clamp:
                self._logger.warning(
                    f"{rail.value}: Clamping {volts:.3f}V to max {config.max_voltage:.3f}V"
                )
                return config.max_voltage
            raise BoundsError(rail, volts, config.min_voltage, config.max_voltage)

        return volts

    # --- Protection Programming ---

    def program_protections(self, rail: RailName) -> None:
        """Program OVP/OCP for a rail and verify setpoints were accepted.

        Must be called before enabling output per safety requirements.

        Raises:
            VerificationError: If the PSU reports a setpoint that differs from
                what was written, or if a protection is not enabled.
        """
        config = RailRegistry.get(rail)
        ch = self._get_channel(rail)

        self._logger.info(
            f"{rail.value}: Programming OVP={config.ovp:.3f}V, OCP={config.ocp:.3f}A, "
            f"Vset={config.nominal_voltage:.3f}V, Iset={config.nominal_current:.3f}A"
        )
        ch.set_ovp(config.ovp, enabled=True)
        ch.set_ocp(config.ocp, enabled=True)
        ch.set_voltage(config.nominal_voltage)
        ch.set_current_limit(config.nominal_current)

        # Verify all setpoints were accepted by the PSU
        ovp_val, ovp_en = ch.get_ovp()
        if abs(ovp_val - config.ovp) > 0.01 or not ovp_en:
            raise VerificationError(
                rail,
                f"OVP={config.ovp:.3f}V en=True",
                f"OVP={ovp_val:.3f}V en={ovp_en}",
            )

        ocp_val, ocp_en = ch.get_ocp()
        if abs(ocp_val - config.ocp) > 0.01 or not ocp_en:
            raise VerificationError(
                rail,
                f"OCP={config.ocp:.3f}A en=True",
                f"OCP={ocp_val:.3f}A en={ocp_en}",
            )

        vset = ch.get_voltage_setpoint()
        if abs(vset - config.nominal_voltage) > 0.01:
            raise VerificationError(
                rail,
                f"VSET={config.nominal_voltage:.3f}V",
                f"VSET={vset:.3f}V",
            )

        iset = ch.get_current_setpoint()
        if abs(iset - config.nominal_current) > 0.001:
            raise VerificationError(
                rail,
                f"ISET={config.nominal_current:.3f}A",
                f"ISET={iset:.3f}A",
            )

        self._logger.debug(f"{rail.value}: Protection setpoints verified OK")

    def program_all_protections(self) -> None:
        """Program protections for all rails."""
        for rail in RailName:
            self.program_protections(rail)

    # --- Output Control ---

    def enable_rail(
        self, rail: RailName, initial_voltage: Optional[float] = None
    ) -> None:
        """Enable a rail output.

        Args:
            rail: Rail to enable
            initial_voltage: Voltage to set before enabling (defaults to nominal)
        """
        config = RailRegistry.get(rail)
        ch = self._get_channel(rail)

        voltage = (
            initial_voltage if initial_voltage is not None else config.nominal_voltage
        )
        voltage = self._clamp_and_validate(rail, voltage)

        self._logger.info(f"{rail.value}: Enabling at {voltage:.3f}V")
        ch.set_voltage(voltage)
        ch.output(True)
        self._rail_states[rail] = RailState.ENABLED

    def disable_rail(self, rail: RailName) -> None:
        """Disable a rail output."""
        ch = self._get_channel(rail)
        self._logger.info(f"{rail.value}: Disabling")
        ch.output(False)
        self._rail_states[rail] = RailState.OFF

    def disable_all_rails(self) -> None:
        """Disable all rail outputs."""
        for rail in RailName:
            self.disable_rail(rail)

    # --- Voltage Write Helpers ---

    _SETTLE_S: float = 0.400  # Output settling time after a voltage write (seconds)

    def _set_voltage_verified(self, rail: RailName, volts: float, tol: float = 0.1) -> None:
        """Set channel voltage and verify via VOUT? readback.

        Waits _SETTLE_S after the write before querying, allowing the PSU
        output to slew to the new setpoint before the readback.

        socket.timeout propagates if the PSU is unreachable.
        Raises VerificationError if measured voltage deviates beyond tolerance.
        """
        ch = self._get_channel(rail)
        ch.set_voltage(volts)
        time.sleep(self._SETTLE_S)  # allow PSU output to settle
        measured = ch.measure_voltage()
        if abs(measured - volts) > tol:
            self._logger.error(
                f"{rail.value}: Voltage write verify failed — "
                f"set {volts:.3f}V, measured {measured:.3f}V (tol ±{tol:.3f}V)"
            )
            raise VerificationError(
                rail,
                f"{volts:.3f}V ±{tol:.3f}V",
                f"{measured:.3f}V",
            )
        self._logger.debug(
            f"{rail.value}: Write verified {measured:.3f}V ≈ {volts:.3f}V"
        )

    # --- Voltage Control (Named Rail API) ---

    def set_voa(self, volts: float) -> None:
        """Set VOA control voltage.

        Args:
            volts: Target voltage, clamped to 0-4.8V
        """
        volts = self._clamp_and_validate(RailName.VOA_CTRL, volts)
        self._set_voltage_verified(RailName.VOA_CTRL, volts)
        self._logger.debug(f"VOA_CTRL -> {volts:.3f}V")

    def set_oa_x(self, volts: float) -> None:
        """Set Output Amplitude X.

        Args:
            volts: Target voltage, clamped to 0-3.3V (0-VCC)
        """
        volts = self._clamp_and_validate(RailName.OA_X, volts)
        self._set_voltage_verified(RailName.OA_X, volts)
        self._logger.debug(f"OA_X -> {volts:.3f}V")

    def set_oa_y(self, volts: float) -> None:
        """Set Output Amplitude Y.

        Args:
            volts: Target voltage, clamped to 0-3.3V (0-VCC)
        """
        volts = self._clamp_and_validate(RailName.OA_Y, volts)
        self._set_voltage_verified(RailName.OA_Y, volts)
        self._logger.debug(f"OA_Y -> {volts:.3f}V")

    def set_ga_x(self, volts: float) -> None:
        """Set Gain Adjust X.

        Args:
            volts: Target voltage, clamped to 0-3.3V (0-VCC)
        """
        volts = self._clamp_and_validate(RailName.GA_X, volts)
        self._set_voltage_verified(RailName.GA_X, volts)
        self._logger.debug(f"GA_X -> {volts:.3f}V")

    def set_ga_y(self, volts: float) -> None:
        """Set Gain Adjust Y.

        Args:
            volts: Target voltage, clamped to 0-3.3V (0-VCC)
        """
        volts = self._clamp_and_validate(RailName.GA_Y, volts)
        self._set_voltage_verified(RailName.GA_Y, volts)
        self._logger.debug(f"GA_Y -> {volts:.3f}V")

    # --- Measurement ---

    def measure_rail(self, rail: RailName) -> RailMeasurement:
        """Get current measurements for a rail.

        Args:
            rail: Rail to measure

        Returns:
            RailMeasurement with voltage, current, state, and mode
        """
        ch = self._get_channel(rail)
        config = RailRegistry.get(rail)
        psu = self._psus[config.psu_name]
        status = psu.status()

        return RailMeasurement(
            name=rail,
            voltage=ch.measure_voltage(),
            current=ch.measure_current(),
            state=self._rail_states[rail],
            mode=status.mode[config.channel - 1],
        )

    def measure_all_rails(self) -> dict[RailName, RailMeasurement]:
        """Get measurements for all rails.

        Returns:
            Dictionary mapping rail names to measurements
        """
        return {rail: self.measure_rail(rail) for rail in RailName}

    # --- Verification ---

    def verify_rail(self, rail: RailName) -> bool:
        """Verify a rail is within expected operating parameters.

        Checks measured voltage and current against the rail's
        verify_voltage and verify_current bounds if defined.

        Args:
            rail: Rail to verify

        Returns:
            True if rail is within spec, False otherwise
        """
        config = RailRegistry.get(rail)
        measurement = self.measure_rail(rail)

        if config.verify_voltage:
            v_min, v_max = config.verify_voltage
            if not (v_min <= measurement.voltage <= v_max):
                self._logger.error(
                    f"{rail.value}: Voltage {measurement.voltage:.3f}V "
                    f"outside expected range [{v_min:.3f}, {v_max:.3f}]"
                )
                return False

        if config.verify_current:
            i_min, i_max = config.verify_current
            if not (i_min <= measurement.current <= i_max):
                self._logger.error(
                    f"{rail.value}: Current {measurement.current:.3f}A "
                    f"outside expected range [{i_min:.3f}, {i_max:.3f}]"
                )
                return False

        return True

    def set_rail_fault(self, rail: RailName) -> None:
        """Mark a rail as faulted.

        Args:
            rail: Rail to mark as faulted
        """
        self._rail_states[rail] = RailState.FAULT
        self._logger.error(f"{rail.value}: Marked as FAULT")

    def get_rail_state(self, rail: RailName) -> RailState:
        """Get current state of a rail.

        Args:
            rail: Rail to query

        Returns:
            Current RailState (OFF, ENABLED, or FAULT)
        """
        return self._rail_states[rail]
