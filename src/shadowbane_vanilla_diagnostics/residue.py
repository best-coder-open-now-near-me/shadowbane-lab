"""Fail-closed vanilla executable and extension-residue validation."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

from .model import ProcessIdentity

_FORBIDDEN_FILE_NAMES = frozenset(
    {
        "wonderbane-extension.dll",
        "wonderbane-extension.pdb",
    }
)
_FORBIDDEN_DIRECTORY_NAMES = frozenset({".wonderbane-extension"})
_FORBIDDEN_FILE_SUFFIXES = (".bootstrap-manifest.json",)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    stat = path.lstat()
    attributes = getattr(stat, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse)


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def find_client_residue(client_directory: Path) -> list[str]:
    """Return known extension deployment artifacts under the exact client tree."""

    findings: list[str] = []
    for root, directories, files in os.walk(client_directory, followlinks=False):
        root_path = Path(root)
        kept_directories: list[str] = []
        for name in directories:
            candidate = root_path / name
            if name.casefold() in _FORBIDDEN_DIRECTORY_NAMES:
                findings.append(candidate.relative_to(client_directory).as_posix())
                continue
            if _is_reparse(candidate):
                findings.append(candidate.relative_to(client_directory).as_posix() + " [reparse]")
                continue
            kept_directories.append(name)
        directories[:] = kept_directories
        for name in files:
            canonical = name.casefold()
            if canonical in _FORBIDDEN_FILE_NAMES or canonical.endswith(
                _FORBIDDEN_FILE_SUFFIXES
            ):
                findings.append((root_path / name).relative_to(client_directory).as_posix())
    return sorted(findings, key=str.casefold)


def find_identity_bound_runtime_residue(
    identity: ProcessIdentity,
    runtime_status_directory: Path | None,
) -> list[str]:
    """Find status files that can only belong to this exact process lifetime."""

    if runtime_status_directory is None or not runtime_status_directory.exists():
        return []
    if not runtime_status_directory.is_dir() or _is_reparse(runtime_status_directory):
        return [str(runtime_status_directory) + " [unsafe status directory]"]
    exact_token = (
        f"-{identity.process_id}-{identity.process_creation_filetime_utc}"
    ).casefold()
    findings: list[str] = []
    for candidate in runtime_status_directory.iterdir():
        if (
            candidate.is_file()
            and exact_token in candidate.name.casefold()
            and not _is_reparse(candidate)
        ):
            findings.append(str(candidate))
    return sorted(findings, key=str.casefold)


def build_vanilla_preflight(
    *,
    requested_executable: Path,
    identity: ProcessIdentity,
    allowed_executable_sha256: Iterable[str],
    modules: list[dict[str, object]],
    runtime_status_directory: Path | None,
) -> dict[str, object]:
    """Build complete preflight evidence; callers reject when ``accepted`` is false."""

    failures: list[str] = []
    executable = requested_executable.resolve(strict=True)
    client_directory = executable.parent
    if not executable.is_file() or _is_reparse(executable):
        failures.append("target executable is not a regular non-reparse file")
    if executable.name.casefold() != "sb.exe":
        failures.append("target executable is not named sb.exe")
    if not _same_path(executable, identity.executable_path):
        failures.append("live process executable differs from the requested exact path")
    executable_sha256 = sha256_file(executable)
    accepted_hashes = frozenset(value.casefold() for value in allowed_executable_sha256)
    if executable_sha256 not in accepted_hashes:
        failures.append("live sb.exe hash is not a reviewed vanilla executable")

    client_residue = find_client_residue(client_directory)
    if client_residue:
        failures.append("client tree contains extension deployment residue")
    runtime_residue = find_identity_bound_runtime_residue(identity, runtime_status_directory)
    if runtime_residue:
        failures.append("exact process lifetime has extension telemetry residue")

    normalized_modules = []
    extension_modules = []
    for module in modules:
        name = str(module.get("name", ""))
        path = str(module.get("path", ""))
        normalized = {
            "name": name,
            "path": path,
            "image_size": int(module.get("image_size", 0)),
        }
        normalized_modules.append(normalized)
        if name.casefold() in _FORBIDDEN_FILE_NAMES or Path(path).name.casefold() in (
            _FORBIDDEN_FILE_NAMES
        ):
            extension_modules.append(normalized)
    if extension_modules:
        failures.append("live process has the WonderBane extension module loaded")
    if not normalized_modules:
        failures.append("live process module inventory is empty")
    elif not any(_same_path(module["path"], executable) for module in normalized_modules):
        failures.append("module inventory does not contain the exact executable image")

    return {
        "schema_version": 1,
        "accepted": not failures,
        "failures": failures,
        "process_identity": identity.as_dict(),
        "executable_sha256": executable_sha256,
        "reviewed_vanilla_hash": executable_sha256 in accepted_hashes,
        "client_directory": str(client_directory),
        "client_residue": client_residue,
        "identity_bound_runtime_residue": runtime_residue,
        "loaded_modules": sorted(normalized_modules, key=lambda item: str(item["path"]).casefold()),
        "extension_modules": extension_modules,
        "extension_telemetry_loaded": False,
    }


__all__ = [
    "build_vanilla_preflight",
    "find_client_residue",
    "find_identity_bound_runtime_residue",
    "sha256_file",
]
