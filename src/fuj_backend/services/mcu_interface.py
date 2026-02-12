"""MCU interface abstraction - placeholder for TBD protocol.

The external MCU (likely Arduino) provides digital control signals for the
FIM24725 module. The communication protocol is not yet determined, so this
module provides a Protocol interface and a MockMCU for development/testing.

Signals controlled by MCU:
- SD (Shutdown): MCU -> Module (Enable: 0-0.8V, Disable: 2V-VCC)
- MC/AGC (Mode): MCU -> Module (MGC: 0-0.8V, AGC: 2V-VCC)

Signals read by MCU:
- PI (Peak indicators): Module -> MCU ADC (0-2V, 4 channels)
- MPD (Monitor photodiode): Module -> MCU ADC
"""

from __future__ import annotations

from typing import Protocol

from .logging import get_service_logger
from .models import OperatingMode, PeakIndicators


class MCUInterface(Protocol):
    """Protocol defining MCU communication interface.

    Implementations must provide these methods for controlling the FIM24725
    digital signals via the external MCU.
    """

    def set_shutdown(self, disable: bool) -> None:
        """Set SD pin state.

        Args:
            disable: True sets SD HIGH (module disabled/shutdown),
                     False sets SD LOW (module enabled/active).
        """
        ...

    def set_mode(self, mode: OperatingMode) -> None:
        """Set MC/AGC pin for gain control mode.

        Args:
            mode: AGC sets pin HIGH (automatic gain control),
                  MGC sets pin LOW (manual gain control).
        """
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
        """Read monitor photodiode value.

        Returns:
            MPD voltage/current value (units TBD).
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

    def set_shutdown(self, disable: bool) -> None:
        """Set SD pin state (simulated)."""
        self._sd_disabled = disable
        state = "DISABLE (HIGH)" if disable else "ENABLE (LOW)"
        self._logger.info(f"SD -> {state}")

    def set_mode(self, mode: OperatingMode) -> None:
        """Set MC/AGC pin (simulated)."""
        self._mode = mode
        pin_state = "HIGH" if mode == OperatingMode.AGC else "LOW"
        self._logger.info(f"MC/AGC -> {mode.value} ({pin_state})")

    def read_peak_indicators(self) -> PeakIndicators:
        """Return mock mid-range PI values."""
        self._logger.debug("Reading PI channels (mock)")
        return PeakIndicators(pi_xi=1.0, pi_xq=1.0, pi_yi=1.0, pi_yq=1.0)

    def read_mpd(self) -> float:
        """Return mock MPD value."""
        self._logger.debug("Reading MPD (mock)")
        return 0.5

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
