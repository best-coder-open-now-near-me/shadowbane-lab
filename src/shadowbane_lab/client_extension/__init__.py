"""Safe, offline preparation for the persistent WonderBane client extension."""

from .baseline import (
    CLIENT_BASELINE_SCHEMA_VERSION,
    BaselineFile,
    ClientBaseline,
    ClientBaselineError,
    freeze_client_baseline,
)

__all__ = [
    "CLIENT_BASELINE_SCHEMA_VERSION",
    "BaselineFile",
    "ClientBaseline",
    "ClientBaselineError",
    "freeze_client_baseline",
]
