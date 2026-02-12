"""Service layer exceptions for FIM24725 control."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import RailName, SystemState


class FIM24725Error(Exception):
    """Base exception for FIM24725 service."""

    pass


class StateError(FIM24725Error):
    """Invalid state transition or operation in current state."""

    def __init__(self, message: str, current_state: SystemState):
        self.current_state = current_state
        super().__init__(f"{message} (current state: {current_state.value})")


class RailError(FIM24725Error):
    """Rail-related error."""

    def __init__(self, message: str, rail: RailName):
        self.rail = rail
        super().__init__(f"Rail {rail.value}: {message}")


class BoundsError(RailError):
    """Value out of bounds for rail."""

    def __init__(
        self, rail: RailName, value: float, min_val: float, max_val: float
    ):
        self.value = value
        self.min_val = min_val
        self.max_val = max_val
        super().__init__(
            f"Value {value:.3f}V out of bounds [{min_val:.3f}, {max_val:.3f}]",
            rail,
        )


class VerificationError(RailError):
    """Rail verification failed."""

    def __init__(self, rail: RailName, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected {expected}, got {actual}", rail)


class MCUError(FIM24725Error):
    """MCU communication error."""

    pass


class SequenceError(FIM24725Error):
    """Power sequencing error."""

    pass
