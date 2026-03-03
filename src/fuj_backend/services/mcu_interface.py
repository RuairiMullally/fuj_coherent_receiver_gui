"""MCU interface abstraction - placeholder for TBD protocol.

The external MCU (likely Arduino) provides digital control signals for the
FIM24725 module. The communication protocol is not yet determined, so this
module provides a Protocol interface and a MockMCU for development/testing.

Signals controlled by MCU:
- SD (Shutdown): MCU -> Module (Enable: 0-0.8V, Disable: 2V-VCC)
- MC/AGC (Mode): MCU -> Module (MGC: 0-0.8V, AGC: 2V-VCC)

Signals read by MCU:
- PI (Peak indicators): Module -> MCU ADC (0-2V, 4 channels)
- MPD+ (Monitor photodiode positive): Module -> MCU A4
- MPD- (Monitor photodiode negative): Module -> MCU A5
"""

from __future__ import annotations

import random
from typing import Protocol

from .logging import get_service_logger
from .models import OperatingMode, PeakIndicators


class MCUInterface(Protocol):
    """Protocol defining MCU communication interface.

    Implementations must provide these methods for controlling the FIM24725
    digital signals via the external MCU.
    """

    def set_shutdown(self, disable: bool) -> bool:
        """Set SD pin state. Returns actual SD state after setting.

        Args:
            disable: True  → D2 LOW  → FIM24725 SD LOW  = shutdown active (module off).
                     False → D2 HIGH → FIM24725 SD HIGH = shutdown inactive (module on).

        Returns:
            Actual SD state: True if disabled, False if enabled.
        """
        ...

    def set_mode(self, mode: OperatingMode) -> OperatingMode:
        """Set MC/AGC pin for gain control mode. Returns actual mode.

        Args:
            mode: AGC sets pin HIGH (automatic gain control),
                  MGC sets pin LOW (manual gain control).

        Returns:
            Actual operating mode confirmed by MCU.
        """
        ...

    @property
    def sd_disabled(self) -> bool:
        """Current SD pin state. True = module disabled (D2 LOW, FIM24725 SD LOW = shutdown active)."""
        ...

    @property
    def mode(self) -> OperatingMode:
        """Current MC/AGC mode setting."""
        ...

    def read_peak_indicators(self) -> PeakIndicators:
        """Read all 4 PI ADC channels.

        Returns:
            PeakIndicators with values 0-2V for each channel.
            Values near 0V indicate power loss.
            Values near 2V indicate clipping.
        """
        ...

    def read_mpd(self) -> float:
        """Read differential monitor photodiode value (MPD+ - MPD-).

        Returns:
            Differential MPD voltage (MPD+ - MPD-).
        """
        ...

    def read_mpd_n(self) -> float:
        """Read MPD- (negative terminal) raw value.

        Returns:
            MPD- voltage (0–2V).
        """
        ...

    def is_connected(self) -> bool:
        """Check if MCU is responsive.

        Returns:
            True if MCU communication is working.
        """
        ...


class MockMCU:
    """Mock MCU for development/testing before real hardware.

    Simulates the MCU interface for testing the service layer without
    actual hardware. Logs all operations.
    """

    def __init__(self) -> None:
        self._logger = get_service_logger().getChild("mcu.mock")
        self._sd_disabled = True  # Start in safe state
        self._mode = OperatingMode.AGC  # Default to AGC
        self._connected = True

    def set_shutdown(self, disable: bool) -> bool:
        """Set SD pin state (simulated). Returns actual state."""
        self._sd_disabled = disable
        state = "DISABLE (D2 LOW → SD LOW)" if disable else "ENABLE (D2 HIGH → SD HIGH)"
        self._logger.info(f"SD -> {state}")
        return self._sd_disabled

    def set_mode(self, mode: OperatingMode) -> OperatingMode:
        """Set MC/AGC pin (simulated). Returns actual mode."""
        self._mode = mode
        pin_state = "HIGH" if mode == OperatingMode.AGC else "LOW"
        self._logger.info(f"MC/AGC -> {mode.value} ({pin_state})")
        return self._mode

    def read_peak_indicators(self) -> PeakIndicators:
        """Return random PI values within valid range."""
        self._logger.debug("Reading PI channels (mock)")
        return PeakIndicators(
            pi_xi=random.uniform(0.0, 2.0),
            pi_xq=random.uniform(0.0, 2.0),
            pi_yi=random.uniform(0.0, 2.0),
            pi_yq=random.uniform(0.0, 2.0),
        )

    def read_mpd(self) -> float:
        """Return random differential MPD value (mock)."""
        self._logger.debug("Reading MPD differential (mock)")
        return random.uniform(0.0, 1.0)

    def read_mpd_n(self) -> float:
        """Return random MPD- raw value (mock)."""
        self._logger.debug("Reading MPD_N (mock)")
        return random.uniform(0.0, 0.5)

    def is_connected(self) -> bool:
        """Return mock connection status."""
        return self._connected

    def simulate_disconnect(self) -> None:
        """Simulate MCU disconnect for testing."""
        self._connected = False
        self._logger.warning("MCU disconnected (simulated)")

    def simulate_reconnect(self) -> None:
        """Simulate MCU reconnect for testing."""
        self._connected = True
        self._logger.info("MCU reconnected (simulated)")

    @property
    def sd_disabled(self) -> bool:
        """Current SD pin state (for testing)."""
        return self._sd_disabled

    @property
    def mode(self) -> OperatingMode:
        """Current mode setting (for testing)."""
        return self._mode
