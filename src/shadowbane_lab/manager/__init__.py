"""Read-only multi-client discovery primitives for the manager application."""

from .model import (
    MANAGER_SNAPSHOT_SCHEMA_VERSION,
    ClientInstanceSnapshot,
    ClientRegistrySnapshot,
    RejectedWindowSnapshot,
    WindowRejectionReason,
)
from .registry import (
    ClientRegistryError,
    ClientWindowRegistry,
    DuplicateClientIdentityError,
    derive_client_instance_id,
)

__all__ = [
    "MANAGER_SNAPSHOT_SCHEMA_VERSION",
    "ClientInstanceSnapshot",
    "ClientRegistryError",
    "ClientRegistrySnapshot",
    "ClientWindowRegistry",
    "DuplicateClientIdentityError",
    "RejectedWindowSnapshot",
    "WindowRejectionReason",
    "derive_client_instance_id",
]
