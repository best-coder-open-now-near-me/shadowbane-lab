"""Create-only publication of compiled texture-profile candidates."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from shadowbane_lab.client_extension.texture_cache import (
    CacheResourceDigest,
    TextureCacheError,
    apply_texture_cache_plan,
    compare_untargeted_payloads,
    copy_file_exact,
    sha256_file,
    validate_cache,
)
from shadowbane_lab.integrity import (
    canonical_timestamp,
    create_only_json,
    validate_relative_path,
    validate_sha256,
)

from .texture_model import (
    TEXTURE_PROFILE_RECEIPT_FILE_NAME,
    TEXTURE_PROFILE_SCHEMA_VERSION,
    TextureProfileError,
    TextureProfilePlan,
    TextureProvider,
)


@dataclass(frozen=True, slots=True)
class TextureProfileReceipt:
    """Durable evidence for a materialized texture-profile directory."""

    created_at_utc: str
    destination_directory: str
    cache_relative_path: str
    profile_sha256: str
    result_cache_sha256: str
    result_cache_size: int
    plan: TextureProfilePlan
    schema_version: int = TEXTURE_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TEXTURE_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported texture-profile receipt schema version")
        if not isinstance(self.created_at_utc, str) or not self.created_at_utc:
            raise ValueError("created_at_utc must be non-empty text")
        if not Path(self.destination_directory).is_absolute():
            raise ValueError("destination_directory must be absolute")
        validate_relative_path(self.cache_relative_path, "cache_relative_path")
        validate_sha256(self.profile_sha256, "profile_sha256")
        validate_sha256(self.result_cache_sha256, "result_cache_sha256")
        if (
            isinstance(self.result_cache_size, bool)
            or not isinstance(self.result_cache_size, int)
            or self.result_cache_size <= 0
        ):
            raise ValueError("result_cache_size must be a positive integer")
        if not isinstance(self.plan, TextureProfilePlan):
            raise ValueError("receipt plan must be a TextureProfilePlan")
        if self.plan.profile_sha256 != self.profile_sha256:
            raise ValueError("receipt profile digest differs from its plan")
        if self.plan.cache_relative_path != self.cache_relative_path:
            raise ValueError("receipt cache path differs from its plan")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc,
            "destination_directory": self.destination_directory,
            "cache_relative_path": self.cache_relative_path,
            "profile_sha256": self.profile_sha256,
            "result_cache_sha256": self.result_cache_sha256,
            "result_cache_size": self.result_cache_size,
            "profile": self.plan.as_dict(),
        }


def materialize_texture_profile(
    plan: TextureProfilePlan,
    destination_directory: str | Path,
    *,
    created_at: datetime | None = None,
) -> TextureProfileReceipt:
    """Build, verify, and atomically publish a create-only texture profile directory."""

    if not isinstance(plan, TextureProfilePlan):
        raise TextureProfileError("plan must be a TextureProfilePlan")
    source_cache = Path(plan.source_cache_path).resolve()
    destination = Path(destination_directory).resolve()
    if destination.exists():
        raise TextureProfileError(f"texture-profile destination already exists: {destination}")
    if sha256_file(source_cache) != plan.source_cache_sha256:
        raise TextureProfileError("source cache changed after the texture profile was compiled")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    published = False
    try:
        relative_parts = PurePosixPath(plan.cache_relative_path).parts
        candidate_cache = temporary.joinpath(*relative_parts)
        copy_file_exact(
            source_cache,
            candidate_cache,
            expected_sha256=plan.source_cache_sha256,
        )
        apply_texture_cache_plan(candidate_cache, plan.cache_plan)
        compare_untargeted_payloads(
            source_cache,
            candidate_cache,
            plan.targeted_keys,
        )
        validation = validate_cache(candidate_cache)
        _verify_selected_results(validation.resources, plan.selected)
        receipt = TextureProfileReceipt(
            created_at_utc=canonical_timestamp(created_at),
            destination_directory=str(destination),
            cache_relative_path=plan.cache_relative_path,
            profile_sha256=plan.profile_sha256,
            result_cache_sha256=validation.cache_sha256,
            result_cache_size=validation.cache_size,
            plan=plan,
        )
        create_only_json(
            temporary / TEXTURE_PROFILE_RECEIPT_FILE_NAME,
            receipt.as_dict(),
        )
        if destination.exists():
            raise TextureProfileError(
                f"texture-profile destination appeared during publication: {destination}"
            )
        os.replace(temporary, destination)
        published = True
        published_cache = destination.joinpath(*relative_parts)
        if (
            sha256_file(published_cache) != receipt.result_cache_sha256
            or published_cache.stat().st_size != receipt.result_cache_size
        ):
            raise TextureProfileError(
                "published texture-profile cache failed verification"
            )
        return receipt
    except TextureProfileError:
        if published:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    except (OSError, TextureCacheError, ValueError) as exc:
        if published:
            shutil.rmtree(destination, ignore_errors=True)
        raise TextureProfileError(
            f"could not materialize texture profile: {exc}"
        ) from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def _verify_selected_results(
    resources: Sequence[CacheResourceDigest],
    selected: Sequence[TextureProvider],
) -> None:
    indexed = {item.key: item for item in resources}
    for provider in selected:
        result = indexed.get(provider.key)
        if result is None or result.payload_sha256 != provider.result_payload_sha256:
            raise TextureProfileError(
                f"materialized payload differs for "
                f"{provider.group_id}:{provider.resource_id}"
            )


__all__ = ["TextureProfileReceipt", "materialize_texture_profile"]
