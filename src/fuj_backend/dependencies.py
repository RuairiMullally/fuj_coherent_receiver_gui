"""
Dependency injection for FastAPI endpoints.
"""
from .hardware import HardwareDriver, SafetyManager


# Global instances (initialized at startup)
_hardware_instance: HardwareDriver | None = None
_safety_manager_instance: SafetyManager | None = None


def set_hardware(hardware: HardwareDriver) -> None:
    """Set the global hardware instance."""
    global _hardware_instance
    _hardware_instance = hardware


def set_safety_manager(safety: SafetyManager) -> None:
    """Set the global safety manager instance."""
    global _safety_manager_instance
    _safety_manager_instance = safety


def get_hardware() -> HardwareDriver:
    """Dependency that provides the hardware driver."""
    if _hardware_instance is None:
        raise RuntimeError("Hardware not initialized")
    return _hardware_instance


def get_safety_manager() -> SafetyManager:
    """Dependency that provides the safety manager."""
    if _safety_manager_instance is None:
        raise RuntimeError("Safety manager not initialized")
    return _safety_manager_instance
