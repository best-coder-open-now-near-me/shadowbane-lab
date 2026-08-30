"""Simulation-specific errors."""


class SimulationConfigurationError(ValueError):
    """Raised when a scenario or compiled action cannot execute safely."""
