"""Safe, offline preparation for the persistent WonderBane client extension."""

from .baseline import (
    CLIENT_BASELINE_SCHEMA_VERSION,
    BaselineFile,
    ClientBaseline,
    ClientBaselineError,
    freeze_client_baseline,
)
from .manifest import (
    PATCH_MANIFEST_SCHEMA_VERSION,
    ExtensionArtifact,
    MaskedSignature,
    PatchManifest,
    PatchManifestError,
    PatchSite,
    SourceExecutable,
    load_patch_manifest,
)
from .resolver import (
    PatchAlignmentReport,
    PatchPlan,
    PatchResolutionError,
    PatchSiteResolution,
    PatchSiteStatus,
    PatchWrite,
    align_patch_sites,
    apply_patch_plan,
    build_patch_plan,
)

__all__ = [
    "CLIENT_BASELINE_SCHEMA_VERSION",
    "PATCH_MANIFEST_SCHEMA_VERSION",
    "BaselineFile",
    "ClientBaseline",
    "ClientBaselineError",
    "ExtensionArtifact",
    "MaskedSignature",
    "PatchAlignmentReport",
    "PatchManifest",
    "PatchManifestError",
    "PatchPlan",
    "PatchResolutionError",
    "PatchSite",
    "PatchSiteResolution",
    "PatchSiteStatus",
    "PatchWrite",
    "SourceExecutable",
    "align_patch_sites",
    "apply_patch_plan",
    "build_patch_plan",
    "freeze_client_baseline",
    "load_patch_manifest",
]
