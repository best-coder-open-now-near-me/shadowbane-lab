"""Strict, intentionally small layout format for WonderBane memory snapshots."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CharacterLayoutError(ValueError):
    """Raised when a layout file is malformed or unsafe to execute."""


_VALUE_TYPES = frozenset(
    {
        "u8",
        "u16",
        "u32",
        "u64",
        "i8",
        "i16",
        "i32",
        "i64",
        "f32",
        "f64",
        "pointer",
        "bool8",
        "bool32",
        "cstring",
        "wstring",
        "bytes",
        "hex",
    }
)


def _require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CharacterLayoutError(f"{label} must be an object")
    return value


def _require_array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CharacterLayoutError(f"{label} must be an array")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterLayoutError(f"{label} must be a non-empty string")
    return value


def _require_boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CharacterLayoutError(f"{label} must be a boolean")
    return value


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool):
        raise CharacterLayoutError(f"{label} must be an integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value, 0)
        except ValueError as exc:
            raise CharacterLayoutError(f"{label} must be an integer or 0x-prefixed value") from exc
    else:
        raise CharacterLayoutError(f"{label} must be an integer or 0x-prefixed value")
    if minimum is not None and parsed < minimum:
        raise CharacterLayoutError(f"{label} must be at least {minimum}")
    return parsed


def _reject_unknown(data: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise CharacterLayoutError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _validate_path(value: object, label: str) -> str:
    path = _require_string(value, label)
    parts = path.split(".")
    if any(not part or part.startswith("_") for part in parts):
        raise CharacterLayoutError(
            f"{label} must contain dot-separated public names without empty components"
        )
    return path


@dataclass(frozen=True, slots=True)
class AddressStep:
    offset: int
    dereference: bool = False


@dataclass(frozen=True, slots=True)
class AddressExpression:
    base: str
    steps: tuple[AddressStep, ...] = ()


@dataclass(frozen=True, slots=True)
class ValueSpec:
    path: str
    value_type: str
    address: AddressExpression
    required: bool = True
    encoding: str = "cp1252"
    max_length: int = 256
    length: int = 0
    scale: float = 1.0
    enum: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RecordSpec:
    path: str
    address: AddressExpression
    values: tuple[ValueSpec, ...]
    required: bool = True


@dataclass(frozen=True, slots=True)
class CollectionSpec:
    path: str
    address: AddressExpression
    count: int
    stride: int
    element_pointer: bool
    skip_null: bool
    labels: tuple[str, ...]
    values: tuple[ValueSpec, ...]
    required: bool = True


@dataclass(frozen=True, slots=True)
class TargetSpec:
    executable_names: tuple[str, ...]
    pointer_size: int
    expected_sha256: str | None
    live_capture_enabled: bool


@dataclass(frozen=True, slots=True)
class CharacterLayout:
    schema_version: int
    layout_id: str
    target: TargetSpec
    roots: tuple[tuple[str, AddressExpression], ...]
    values: tuple[ValueSpec, ...]
    records: tuple[RecordSpec, ...]
    collections: tuple[CollectionSpec, ...]
    notes: tuple[str, ...] = ()


def _parse_address(value: object, label: str) -> AddressExpression:
    data = _require_object(value, label)
    _reject_unknown(data, {"base", "steps"}, label)
    base = _require_string(data.get("base"), f"{label}.base")
    valid_base = (
        base.startswith("module:") or base.startswith("root:") or base in {"record", "element"}
    )
    if not valid_base:
        raise CharacterLayoutError(
            f"{label}.base must be module:<name>, root:<name>, record, or element"
        )
    steps: list[AddressStep] = []
    for index, item in enumerate(_require_array(data.get("steps", []), f"{label}.steps")):
        step_data = _require_object(item, f"{label}.steps[{index}]")
        _reject_unknown(step_data, {"offset", "dereference"}, f"{label}.steps[{index}]")
        steps.append(
            AddressStep(
                offset=_integer(step_data.get("offset", 0), f"{label}.steps[{index}].offset"),
                dereference=_require_boolean(
                    step_data.get("dereference", False),
                    f"{label}.steps[{index}].dereference",
                ),
            )
        )
    return AddressExpression(base=base, steps=tuple(steps))


def _parse_value(value: object, label: str, *, relative_base: str | None = None) -> ValueSpec:
    data = _require_object(value, label)
    _reject_unknown(
        data,
        {
            "path",
            "type",
            "address",
            "offset",
            "steps",
            "required",
            "encoding",
            "max_length",
            "length",
            "scale",
            "enum",
        },
        label,
    )
    path = _validate_path(data.get("path"), f"{label}.path")
    value_type = _require_string(data.get("type"), f"{label}.type")
    if value_type not in _VALUE_TYPES:
        raise CharacterLayoutError(f"{label}.type must be one of {', '.join(sorted(_VALUE_TYPES))}")
    if "address" in data and any(key in data for key in ("offset", "steps")):
        raise CharacterLayoutError(
            f"{label} must use either address or relative offset/steps, not both"
        )
    if "address" in data:
        address = _parse_address(data["address"], f"{label}.address")
    else:
        if relative_base is None:
            raise CharacterLayoutError(f"{label}.address is required")
        raw_steps = data.get("steps")
        if raw_steps is None:
            raw_steps = [
                {
                    "offset": data.get("offset", 0),
                    "dereference": False,
                }
            ]
        address = _parse_address(
            {"base": relative_base, "steps": raw_steps},
            f"{label}.relative_address",
        )
    required = _require_boolean(data.get("required", True), f"{label}.required")
    encoding = _require_string(data.get("encoding", "cp1252"), f"{label}.encoding")
    max_length = _integer(data.get("max_length", 256), f"{label}.max_length", minimum=1)
    length = _integer(data.get("length", 0), f"{label}.length", minimum=0)
    if value_type in {"bytes", "hex"} and length < 1:
        raise CharacterLayoutError(f"{label}.length must be positive for {value_type}")
    raw_scale = data.get("scale", 1.0)
    if isinstance(raw_scale, bool) or not isinstance(raw_scale, (int, float)):
        raise CharacterLayoutError(f"{label}.scale must be a finite number")
    scale = float(raw_scale)
    if not math.isfinite(scale):
        raise CharacterLayoutError(f"{label}.scale must be a finite number")
    enum_items: list[tuple[int, str]] = []
    raw_enum = data.get("enum", {})
    if not isinstance(raw_enum, dict):
        raise CharacterLayoutError(f"{label}.enum must be an object")
    for key, enum_value in raw_enum.items():
        enum_items.append(
            (
                _integer(key, f"{label}.enum key"),
                _require_string(enum_value, f"{label}.enum[{key!r}]"),
            )
        )
    return ValueSpec(
        path=path,
        value_type=value_type,
        address=address,
        required=required,
        encoding=encoding,
        max_length=max_length,
        length=length,
        scale=scale,
        enum=tuple(sorted(enum_items)),
    )


def _parse_target(value: object) -> TargetSpec:
    data = _require_object(value, "target")
    _reject_unknown(
        data,
        {"executable_names", "pointer_size", "expected_sha256", "live_capture_enabled"},
        "target",
    )
    names = tuple(
        _require_string(item, "target.executable_names item")
        for item in _require_array(data.get("executable_names"), "target.executable_names")
    )
    if not names or len(names) != len({name.casefold() for name in names}):
        raise CharacterLayoutError("target.executable_names must be non-empty and unique")
    pointer_size = _integer(data.get("pointer_size"), "target.pointer_size")
    if pointer_size not in (4, 8):
        raise CharacterLayoutError("target.pointer_size must be 4 or 8")
    raw_hash = data.get("expected_sha256")
    expected_hash: str | None
    if raw_hash is None:
        expected_hash = None
    else:
        expected_hash = _require_string(raw_hash, "target.expected_sha256").lower()
        expected_hash = expected_hash.removeprefix("sha256:")
        if len(expected_hash) != 64 or any(
            char not in "0123456789abcdef" for char in expected_hash
        ):
            raise CharacterLayoutError("target.expected_sha256 must contain 64 hexadecimal digits")
    return TargetSpec(
        executable_names=names,
        pointer_size=pointer_size,
        expected_sha256=expected_hash,
        live_capture_enabled=_require_boolean(
            data.get("live_capture_enabled", False), "target.live_capture_enabled"
        ),
    )


def _parse_record(value: object, label: str) -> RecordSpec:
    data = _require_object(value, label)
    _reject_unknown(data, {"path", "address", "values", "required"}, label)
    return RecordSpec(
        path=_validate_path(data.get("path"), f"{label}.path"),
        address=_parse_address(data.get("address"), f"{label}.address"),
        values=tuple(
            _parse_value(item, f"{label}.values[{index}]", relative_base="record")
            for index, item in enumerate(_require_array(data.get("values"), f"{label}.values"))
        ),
        required=_require_boolean(data.get("required", True), f"{label}.required"),
    )


def _parse_collection(value: object, label: str) -> CollectionSpec:
    data = _require_object(value, label)
    _reject_unknown(
        data,
        {
            "path",
            "address",
            "count",
            "stride",
            "element_pointer",
            "skip_null",
            "labels",
            "values",
            "required",
        },
        label,
    )
    count = _integer(data.get("count"), f"{label}.count", minimum=1)
    if count > 4096:
        raise CharacterLayoutError(f"{label}.count exceeds the safety limit of 4096")
    stride = _integer(data.get("stride"), f"{label}.stride", minimum=1)
    labels = tuple(
        _require_string(item, f"{label}.labels item")
        for item in _require_array(data.get("labels", []), f"{label}.labels")
    )
    if labels and len(labels) != count:
        raise CharacterLayoutError(f"{label}.labels must contain exactly count entries")
    if len(labels) != len(set(labels)):
        raise CharacterLayoutError(f"{label}.labels must be unique")
    return CollectionSpec(
        path=_validate_path(data.get("path"), f"{label}.path"),
        address=_parse_address(data.get("address"), f"{label}.address"),
        count=count,
        stride=stride,
        element_pointer=_require_boolean(
            data.get("element_pointer", False), f"{label}.element_pointer"
        ),
        skip_null=_require_boolean(data.get("skip_null", True), f"{label}.skip_null"),
        labels=labels,
        values=tuple(
            _parse_value(item, f"{label}.values[{index}]", relative_base="element")
            for index, item in enumerate(_require_array(data.get("values"), f"{label}.values"))
        ),
        required=_require_boolean(data.get("required", True), f"{label}.required"),
    )


def load_character_layout(path: Path | str) -> CharacterLayout:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CharacterLayoutError(f"layout is not valid JSON: {exc}") from exc
    data = _require_object(payload, "layout")
    _reject_unknown(
        data,
        {
            "schema_version",
            "layout_id",
            "target",
            "roots",
            "values",
            "records",
            "collections",
            "notes",
        },
        "layout",
    )
    if _integer(data.get("schema_version"), "schema_version") != 1:
        raise CharacterLayoutError("unsupported character layout schema version")
    roots_data = _require_object(data.get("roots", {}), "roots")
    roots: list[tuple[str, AddressExpression]] = []
    for name, expression in roots_data.items():
        root_name = _require_string(name, "root name")
        if root_name.startswith("_"):
            raise CharacterLayoutError("root names may not begin with an underscore")
        roots.append((root_name, _parse_address(expression, f"roots.{root_name}")))
    if len(roots) != len({name for name, _ in roots}):
        raise CharacterLayoutError("root names must be unique")
    notes = tuple(
        _require_string(item, "notes item")
        for item in _require_array(data.get("notes", []), "notes")
    )
    values = tuple(
        _parse_value(item, f"values[{index}]")
        for index, item in enumerate(_require_array(data.get("values", []), "values"))
    )
    records = tuple(
        _parse_record(item, f"records[{index}]")
        for index, item in enumerate(_require_array(data.get("records", []), "records"))
    )
    collections = tuple(
        _parse_collection(item, f"collections[{index}]")
        for index, item in enumerate(_require_array(data.get("collections", []), "collections"))
    )
    output_paths = [item.path for item in values]
    output_paths.extend(item.path for item in records)
    output_paths.extend(item.path for item in collections)
    if len(output_paths) != len(set(output_paths)):
        raise CharacterLayoutError("top-level captured paths must be unique")
    return CharacterLayout(
        schema_version=1,
        layout_id=_require_string(data.get("layout_id"), "layout_id"),
        target=_parse_target(data.get("target")),
        roots=tuple(roots),
        values=values,
        records=records,
        collections=collections,
        notes=notes,
    )
