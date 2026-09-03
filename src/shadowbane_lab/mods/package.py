"""Validated directory packages for public Shadowbane asset mods."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shadowbane_lab.integrity import is_reparse_point, validate_sha256

from .manifest import (
    ASSET_MOD_MANIFEST_FILE_NAME,
    AssetModManifest,
    asset_mod_manifest_sha256,
    load_asset_mod_manifest,
)


class AssetModPackageError(RuntimeError):
    """Raised when an asset-mod directory cannot be trusted as a package."""


@dataclass(frozen=True, slots=True)
class AssetModPackage:
    """One validated directory package and its canonical public manifest."""

    root: str
    manifest: AssetModManifest
    manifest_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, str) or not self.root:
            raise ValueError("package root must be a non-empty absolute path")
        if not Path(self.root).is_absolute():
            raise ValueError("package root must be absolute")
        if not isinstance(self.manifest, AssetModManifest):
            raise ValueError("package manifest must be an AssetModManifest")
        validate_sha256(self.manifest_sha256, "manifest_sha256")
        if asset_mod_manifest_sha256(self.manifest) != self.manifest_sha256:
            raise ValueError("package manifest digest disagrees with the manifest")

    @property
    def identity(self) -> str:
        return self.manifest.identity

    def as_dict(self) -> dict[str, object]:
        return {
            "mod_id": self.manifest.mod_id,
            "version": self.manifest.version,
            "manifest_sha256": self.manifest_sha256,
        }


def load_asset_mod_package(root: str | Path) -> AssetModPackage:
    package_root = Path(root).resolve()
    if not package_root.is_dir() or is_reparse_point(package_root):
        raise AssetModPackageError(
            f"asset-mod package is not an ordinary directory: {package_root}"
        )
    try:
        manifest = load_asset_mod_manifest(
            package_root / ASSET_MOD_MANIFEST_FILE_NAME
        )
        return AssetModPackage(
            root=str(package_root),
            manifest=manifest,
            manifest_sha256=asset_mod_manifest_sha256(manifest),
        )
    except AssetModPackageError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise AssetModPackageError(
            f"could not load asset-mod package {package_root}: {exc}"
        ) from exc


def verify_asset_mod_package(package: AssetModPackage) -> AssetModPackage:
    """Reread a package manifest and require its selected identity to remain unchanged."""

    if not isinstance(package, AssetModPackage):
        raise AssetModPackageError("package must be an AssetModPackage")
    current = load_asset_mod_package(package.root)
    if (
        current.manifest != package.manifest
        or current.manifest_sha256 != package.manifest_sha256
    ):
        raise AssetModPackageError(
            f"asset-mod package changed after selection: {package.identity}"
        )
    return current


__all__ = [
    "AssetModPackage",
    "AssetModPackageError",
    "load_asset_mod_package",
    "verify_asset_mod_package",
]
