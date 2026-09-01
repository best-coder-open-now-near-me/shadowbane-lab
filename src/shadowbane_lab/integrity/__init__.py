"""Shared fail-closed integrity primitives for durable Shadowbane Lab artifacts."""

from .canonical import (
    JsonBounds,
    canonical_json_bytes,
    canonical_json_sha256,
    canonical_json_text,
    load_strict_json,
    pretty_json_text,
    strict_json_loads,
    validate_finite_json,
)
from .paths import (
    PathSecurityError,
    canonical_timestamp,
    is_reparse_point,
    resolve_within_root,
    validate_identifier,
    validate_relative_path,
    validate_sha256,
)
from .storage import (
    CreateOnlyError,
    create_only_bytes,
    create_only_json,
    create_only_text,
)
from .tree import (
    FileRecord,
    TreeInventory,
    hash_file,
    inventory_tree,
    tree_sha256,
)

__all__ = [
    "CreateOnlyError",
    "FileRecord",
    "JsonBounds",
    "PathSecurityError",
    "TreeInventory",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "canonical_json_text",
    "canonical_timestamp",
    "create_only_bytes",
    "create_only_json",
    "create_only_text",
    "hash_file",
    "inventory_tree",
    "is_reparse_point",
    "load_strict_json",
    "pretty_json_text",
    "resolve_within_root",
    "strict_json_loads",
    "tree_sha256",
    "validate_finite_json",
    "validate_identifier",
    "validate_relative_path",
    "validate_sha256",
]
