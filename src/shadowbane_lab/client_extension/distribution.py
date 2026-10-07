"""Read-only baseline identification, separate from package and live qualification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shadowbane_lab.integrity import FileRecord, hash_file, is_reparse_point, resolve_within_root

ClientVariant = Literal["official", "prepared"]


@dataclass(frozen=True, slots=True)
class DistributionBaseline:
    """Reviewed markers; never a whole-distribution or server compatibility claim."""

    profile_id: str
    upstream_manifest_sha256: str
    official_executable: FileRecord
    prepared_executable: FileRecord
    objects_cache: FileRecord

    def files_for(self, variant: ClientVariant) -> tuple[FileRecord, ...]:
        if variant not in ("official", "prepared"):
            raise ValueError("variant must be official or prepared")
        executable = (self.official_executable if variant == "official"
                      else self.prepared_executable)
        return executable, self.objects_cache


# Provenance: docs/client-update-20261004.md, October 4 executable and October 7 cache.
# Deliberately independent of native-layout equivalence: equal offsets do not imply
# equal client content, gameplay data, installed extension, or server behavior.
WONDERBANE_BASELINE = DistributionBaseline(
    profile_id="wonderbane-1.3.38.14-objects-20261007-v1",
    upstream_manifest_sha256="22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c",
    official_executable=FileRecord(
        "sb.exe", 21143613,
        "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e",
    ),
    prepared_executable=FileRecord(
        "sb.exe", 21143613,
        "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903",
    ),
    objects_cache=FileRecord(
        "cache/CObjects.cache", 5433065,
        "08c115baeef5da811f7ee2802ccdc1002cfeba29cf1818956c452e3e594efef6",
    ),
)


def _identity(path: Path) -> tuple[int, ...]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def inspect_distribution(
    directory: Path,
    *,
    variant: ClientVariant,
    baseline: DistributionBaseline = WONDERBANE_BASELINE,
) -> dict[str, object]:
    """Identify exact markers without launching, copying, patching, or granting actions.

    An offline observation only: subsequent launch/deployment must revalidate its
    own package and process. This cannot provide an atomic snapshot of a live updater.
    """
    expected_files = baseline.files_for(variant)
    directory = Path(directory)
    if not directory.is_dir() or is_reparse_point(directory):
        raise ValueError("client directory must be a regular directory without reparse indirection")
    directory = directory.resolve(strict=True)
    checks: list[dict[str, object]] = []
    observed: list[tuple[FileRecord, tuple[int, ...], dict[str, object]]] = []
    for expected in expected_files:
        check: dict[str, object] = {"expected": expected.as_dict()}
        checks.append(check)
        try:
            path = resolve_within_root(directory, expected.relative_path)
            if not path.is_file():
                raise ValueError("required marker is missing or is not a regular file")
            before = _identity(path)
            observed.append((expected, before, check))
            if before[2] != expected.size:
                check.update(status="size_mismatch", observed_size=before[2])
                continue
            size, digest = hash_file(path, maximum_bytes=expected.size)
            check.update(
                observed_size=size, observed_sha256=digest,
                status="matched" if digest == expected.sha256 else "hash_mismatch",
            )
        except (OSError, ValueError) as exc:
            check.update(status="unreadable", error=str(exc))

    # Recheck all markers after hashing, including identity and parent indirection.
    for expected, before, check in observed:
        try:
            path = resolve_within_root(directory, expected.relative_path)
            if before != _identity(path):
                check["status"] = "changed_during_inspection"
        except (OSError, ValueError) as exc:
            check.update(status="changed_during_inspection", error=str(exc))

    return {
        "schema_version": 1,
        "profile_id": baseline.profile_id,
        "upstream_manifest_sha256": baseline.upstream_manifest_sha256,
        "directory": str(directory),
        "variant": variant,
        "scope": "executable_and_objects_cache_only",
        "markers_match": all(check["status"] == "matched" for check in checks),
        "checks": checks,
        "not_evaluated": [
            "remaining_distribution_files", "extension_package", "live_capabilities",
            "server_compatibility", "gameplay_ruleset",
        ],
    }
