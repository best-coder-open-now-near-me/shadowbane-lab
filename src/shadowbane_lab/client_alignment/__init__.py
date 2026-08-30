"""Offline, non-mutating WonderBane client-build alignment tooling."""

from shadowbane_lab.client_alignment.compare import ClientAlignmentError, compare_client_builds
from shadowbane_lab.client_alignment.model import (
    AnchorIntersection,
    CalibratedAnchor,
    ChangedRange,
    ClientAlignmentReport,
    PeImage,
    PeSection,
    ProfileInventory,
)
from shadowbane_lab.client_alignment.pe import PeInspectionError, inspect_pe, inspect_pe_bytes
from shadowbane_lab.client_alignment.profiles import (
    ProfileInventoryError,
    inventory_native_profiles,
)

__all__ = [
    "AnchorIntersection",
    "CalibratedAnchor",
    "ChangedRange",
    "ClientAlignmentError",
    "ClientAlignmentReport",
    "PeImage",
    "PeInspectionError",
    "PeSection",
    "ProfileInventory",
    "ProfileInventoryError",
    "compare_client_builds",
    "inspect_pe",
    "inspect_pe_bytes",
    "inventory_native_profiles",
]
