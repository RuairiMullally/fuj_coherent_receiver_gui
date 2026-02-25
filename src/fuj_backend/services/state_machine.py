"""System state machine for FIM24725.

Manages system state transitions and enforces valid sequencing.

State diagram:
    OFF -> STARTING -> READY -> SHUTTING_DOWN -> OFF
             |           |           |
             v           v           v
           FAULT <------+---------->FAULT
"""

from __future__ import annotations

from typing import Callable, Optional

from .exceptions import StateError
from .logging import get_service_logger
from .models import FaultInfo, OperatingMode, SystemState


class StateMachine:
    """
    Manages FIM24725 system state transitions.

    Enforces valid state flow, tracks operating mode, and provides
    callbacks for state changes.
    """

    # Valid state transitions
    TRANSITIONS: dict[SystemState, set[SystemState]] = {
        SystemState.OFF: {SystemState.STARTING, SystemState.FAULT},
        SystemState.STARTING: {SystemState.READY, SystemState.FAULT, SystemState.OFF},
        SystemState.READY: {SystemState.SHUTTING_DOWN, SystemState.FAULT},
        SystemState.FAULT: {SystemState.OFF, SystemState.SHUTTING_DOWN},
        SystemState.SHUTTING_DOWN: {SystemState.OFF, SystemState.FAULT},
    }

    def __init__(self) -> None:
        self._logger = get_service_logger().getChild("state")
        self._state = SystemState.OFF
        self._mode = OperatingMode.AGC
        self._fault_info: Optional[FaultInfo] = None
        self._state_callbacks: list[Callable[[SystemState, SystemState], None]] = []

    @property
    def state(self) -> SystemState:
        """Current system state."""
        return self._state

    @property
    def mode(self) -> OperatingMode:
        """Current operating mode (AGC/MGC)."""
        return self._mode

    @property
    def fault_info(self) -> Optional[FaultInfo]:
        """Fault information if in FAULT state."""
        return self._fault_info

    def add_state_callback(
        self, callback: Callable[[SystemState, SystemState], None]
    ) -> None:
        """Register callback for state changes.

        Args:
            callback: Function called as callback(old_state, new_state)
        """
        self._state_callbacks.append(callback)

    def remove_state_callback(
        self, callback: Callable[[SystemState, SystemState], None]
    ) -> None:
        """Remove a previously registered callback."""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)

    def _notify_callbacks(
        self, old_state: SystemState, new_state: SystemState
    ) -> None:
        """Notify all registered callbacks of state change."""
        for cb in self._state_callbacks:
            try:
                cb(old_state, new_state)
            except Exception as e:
                self._logger.error(f"State callback error: {e}")

    def transition_to(self, new_state: SystemState) -> None:
        """Attempt state transition.

        Args:
            new_state: Target state

        Raises:
            StateError: If transition is not valid from current state
        """
        valid_targets = self.TRANSITIONS.get(self._state, set())
        if new_state not in valid_targets:
            raise StateError(
                f"Cannot transition from {self._state.value} to {new_state.value}",
                self._state,
            )

        old_state = self._state
        self._state = new_state
        self._logger.info(f"State: {old_state.value} -> {new_state.value}")
        self._notify_callbacks(old_state, new_state)

        # Clear fault on successful transition to OFF
        if new_state == SystemState.OFF:
            self._fault_info = None

    def set_mode(self, mode: OperatingMode) -> None:
        """Set operating mode (AGC/MGC).

        Args:
            mode: Target operating mode
        """
        old_mode = self._mode
        self._mode = mode
        if old_mode != mode:
            self._logger.info(f"Mode: {old_mode.value} -> {mode.value}")

    def fault(self, info: FaultInfo) -> None:
        """Enter fault state with information.

        This method always succeeds - faults can occur from any state.

        Args:
            info: Fault information
        """
        self._fault_info = info
        old_state = self._state
        self._state = SystemState.FAULT
        self._logger.error(f"FAULT from {old_state.value}: {info.message}")
        self._notify_callbacks(old_state, SystemState.FAULT)

    def can_enable_output(self) -> bool:
        """Check if system is ready to enable SD.

        Returns:
            True if system is in READY state
        """
        return self._state == SystemState.READY

    def is_fault(self) -> bool:
        """Check if system is in fault state."""
        return self._state == SystemState.FAULT

    def is_off(self) -> bool:
        """Check if system is off."""
        return self._state == SystemState.OFF

    def is_ready(self) -> bool:
        """Check if system is ready for operation."""
        return self._state == SystemState.READY

    def require_state(self, *states: SystemState) -> None:
        """Raise StateError if not in one of the specified states.

        Args:
            *states: Allowed states

        Raises:
            StateError: If current state is not in the allowed list
        """
        if self._state not in states:
            allowed = [s.value for s in states]
            raise StateError(
                f"Operation requires state {allowed}",
                self._state,
            )
