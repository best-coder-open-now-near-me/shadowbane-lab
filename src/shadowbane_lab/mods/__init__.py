"""Public, build-aware mod package and texture-profile contracts."""

from .manifest import (
    ASSET_MOD_MANIFEST_FILE_NAME,
    ASSET_MOD_MANIFEST_SCHEMA_VERSION,
    AssetModManifest,
    AssetModManifestError,
    TextureSetComponent,
    TextureSetVariant,
    asset_mod_manifest_sha256,
    load_asset_mod_manifest,
    parse_asset_mod_manifest,
)
from .package import (
    AssetModPackage,
    AssetModPackageError,
    load_asset_mod_package,
)
from .texture_compile import compile_texture_profile
from .texture_materialize import (
    TextureProfileReceipt,
    materialize_texture_profile,
)
from .texture_model import (
    TEXTURE_PROFILE_RECEIPT_FILE_NAME,
    TEXTURE_PROFILE_SCHEMA_VERSION,
    TextureConflict,
    TextureProfileConflictError,
    TextureProfileError,
    TextureProfilePlan,
    TextureProvider,
)

__all__ = [
    "ASSET_MOD_MANIFEST_FILE_NAME",
    "ASSET_MOD_MANIFEST_SCHEMA_VERSION",
    "TEXTURE_PROFILE_RECEIPT_FILE_NAME",
    "TEXTURE_PROFILE_SCHEMA_VERSION",
    "AssetModManifest",
    "AssetModManifestError",
    "AssetModPackage",
    "AssetModPackageError",
    "TextureConflict",
    "TextureProfileConflictError",
    "TextureProfileError",
    "TextureProfilePlan",
    "TextureProfileReceipt",
    "TextureProvider",
    "TextureSetComponent",
    "TextureSetVariant",
    "asset_mod_manifest_sha256",
    "compile_texture_profile",
    "load_asset_mod_manifest",
    "load_asset_mod_package",
    "materialize_texture_profile",
    "parse_asset_mod_manifest",
]
