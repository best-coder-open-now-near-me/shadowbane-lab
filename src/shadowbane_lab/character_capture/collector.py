"""Evaluate a pinned character layout against a read-only memory reader."""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from typing import Any

from shadowbane_lab.character_capture.layout import (
    AddressExpression,
    CharacterLayout,
    CollectionSpec,
    RecordSpec,
    ValueSpec,
)
from shadowbane_lab.character_capture.memory import MemoryAccessError, MemoryReader
from shadowbane_lab.character_capture.model import CharacterCapture


class CharacterCaptureError(RuntimeError):
    """Raised when a pinned layout cannot be captured safely."""


class NullPointerError(MemoryAccessError):
    """Raised when a declared pointer chain resolves through null."""


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cursor = target
    for part in parts[:-1]:
        existing = cursor.get(part)
        if existing is None:
            child: dict[str, Any] = {}
            cursor[part] = child
            cursor = child
        elif isinstance(existing, dict):
            cursor = existing
        else:
            raise CharacterCaptureError(
                f"path collision: {path!r} crosses the scalar value at {part!r}"
            )
    leaf = parts[-1]
    if leaf in cursor:
        raise CharacterCaptureError(f"duplicate captured path: {path}")
    cursor[leaf] = value


def _resolve_address(
    expression: AddressExpression,
    reader: MemoryReader,
    roots: dict[str, int],
    local_bases: dict[str, int],
) -> int:
    if expression.base.startswith("module:"):
        address = reader.module(expression.base.removeprefix("module:")).base_address
    elif expression.base.startswith("root:"):
        root_name = expression.base.removeprefix("root:")
        try:
            address = roots[root_name]
        except KeyError as exc:
            raise CharacterCaptureError(f"unknown layout root: {root_name}") from exc
    else:
        try:
            address = local_bases[expression.base]
        except KeyError as exc:
            raise CharacterCaptureError(
                f"address base {expression.base!r} is not valid in this capture context"
            ) from exc
    for step in expression.steps:
        address += step.offset
        if step.dereference:
            address = reader.read_pointer(address)
            if address == 0:
                raise NullPointerError("pointer chain resolved through address zero")
    return address


def _decode_value(spec: ValueSpec, reader: MemoryReader, address: int) -> Any:
    formats = {
        "u8": "<B",
        "u16": "<H",
        "u32": "<I",
        "u64": "<Q",
        "i8": "<b",
        "i16": "<h",
        "i32": "<i",
        "i64": "<q",
        "f32": "<f",
        "f64": "<d",
        "bool8": "<B",
        "bool32": "<I",
    }
    if spec.value_type in formats:
        fmt = formats[spec.value_type]
        value = struct.unpack(fmt, reader.read(address, struct.calcsize(fmt)))[0]
        if spec.value_type.startswith("bool"):
            value = bool(value)
    elif spec.value_type == "pointer":
        value = reader.read_pointer(address)
    elif spec.value_type == "cstring":
        value = reader.read_cstring(
            address,
            max_length=spec.max_length,
            encoding=spec.encoding,
        )
    elif spec.value_type == "wstring":
        value = reader.read_wstring(address, max_characters=spec.max_length)
    elif spec.value_type == "bytes":
        value = list(reader.read(address, spec.length))
    elif spec.value_type == "hex":
        value = reader.read(address, spec.length).hex()
    else:
        raise CharacterCaptureError(f"unsupported value type: {spec.value_type}")

    if isinstance(value, (int, float)) and not isinstance(value, bool) and spec.scale != 1.0:
        value = value * spec.scale
    if spec.enum and isinstance(value, int) and not isinstance(value, bool):
        enum_values = dict(spec.enum)
        value = {"value": value, "label": enum_values.get(value)}
    return value


def _capture_values(
    specs: tuple[ValueSpec, ...],
    reader: MemoryReader,
    roots: dict[str, int],
    local_bases: dict[str, int],
    output: dict[str, Any],
    warnings: list[str],
    *,
    context: str,
) -> None:
    for spec in specs:
        try:
            address = _resolve_address(spec.address, reader, roots, local_bases)
            value = _decode_value(spec, reader, address)
            _set_path(output, spec.path, value)
        except (MemoryAccessError, UnicodeError, struct.error) as exc:
            message = f"{context}.{spec.path}: {exc}"
            if spec.required:
                raise CharacterCaptureError(message) from exc
            warnings.append(message)


def _resolve_roots(layout: CharacterLayout, reader: MemoryReader) -> dict[str, int]:
    expressions = dict(layout.roots)
    resolved: dict[str, int] = {}
    resolving: set[str] = set()

    def resolve(name: str) -> int:
        if name in resolved:
            return resolved[name]
        if name in resolving:
            raise CharacterCaptureError(f"layout roots contain a cycle involving {name!r}")
        try:
            expression = expressions[name]
        except KeyError as exc:
            raise CharacterCaptureError(f"unknown layout root: {name}") from exc
        resolving.add(name)
        if expression.base.startswith("root:"):
            dependency = expression.base.removeprefix("root:")
            resolve(dependency)
        value = _resolve_address(expression, reader, resolved, {})
        resolving.remove(name)
        resolved[name] = value
        return value

    for root_name in expressions:
        resolve(root_name)
    return resolved


def _capture_record(
    spec: RecordSpec,
    reader: MemoryReader,
    roots: dict[str, int],
    character: dict[str, Any],
    warnings: list[str],
) -> None:
    try:
        base = _resolve_address(spec.address, reader, roots, {})
    except MemoryAccessError as exc:
        message = f"record {spec.path}: {exc}"
        if spec.required:
            raise CharacterCaptureError(message) from exc
        warnings.append(message)
        return
    record: dict[str, Any] = {}
    _capture_values(
        spec.values,
        reader,
        roots,
        {"record": base},
        record,
        warnings,
        context=spec.path,
    )
    _set_path(character, spec.path, record)


def _capture_collection(
    spec: CollectionSpec,
    reader: MemoryReader,
    roots: dict[str, int],
    character: dict[str, Any],
    warnings: list[str],
) -> None:
    try:
        base = _resolve_address(spec.address, reader, roots, {})
    except MemoryAccessError as exc:
        message = f"collection {spec.path}: {exc}"
        if spec.required:
            raise CharacterCaptureError(message) from exc
        warnings.append(message)
        return

    records: list[dict[str, Any]] = []
    for index in range(spec.count):
        element_address = base + index * spec.stride
        if spec.element_pointer:
            try:
                element_address = reader.read_pointer(element_address)
            except MemoryAccessError as exc:
                message = f"{spec.path}[{index}]: {exc}"
                if spec.required:
                    raise CharacterCaptureError(message) from exc
                warnings.append(message)
                continue
            if element_address == 0:
                if spec.skip_null:
                    continue
                records.append(
                    {
                        "index": index,
                        "label": spec.labels[index] if spec.labels else None,
                        "present": False,
                    }
                )
                continue
        record: dict[str, Any] = {"index": index, "present": True}
        if spec.labels:
            record["label"] = spec.labels[index]
        _capture_values(
            spec.values,
            reader,
            roots,
            {"element": element_address},
            record,
            warnings,
            context=f"{spec.path}[{index}]",
        )
        records.append(record)
    _set_path(character, spec.path, records)


def capture_character(layout: CharacterLayout, reader: MemoryReader) -> CharacterCapture:
    """Capture one character document without retaining unrelated process memory."""

    if not layout.target.live_capture_enabled:
        raise CharacterCaptureError(
            "layout is live-locked; pin the executable hash, fill reviewed offsets, and set "
            "target.live_capture_enabled=true"
        )
    process = reader.process_info
    if process.pointer_size != layout.target.pointer_size:
        raise CharacterCaptureError(
            f"layout pointer size {layout.target.pointer_size} does not match target "
            f"pointer size {process.pointer_size}"
        )
    if process.executable_name.casefold() not in {
        name.casefold() for name in layout.target.executable_names
    }:
        raise CharacterCaptureError(f"layout does not allow executable {process.executable_name!r}")
    if layout.target.expected_sha256:
        actual = process.executable_sha256
        if actual is None or actual.lower() != layout.target.expected_sha256:
            raise CharacterCaptureError(
                "executable hash does not match the layout; refuse to apply stale offsets"
            )

    roots = _resolve_roots(layout, reader)
    character: dict[str, Any] = {}
    warnings: list[str] = []
    _capture_values(
        layout.values,
        reader,
        roots,
        {},
        character,
        warnings,
        context="character",
    )
    for record in layout.records:
        _capture_record(record, reader, roots, character, warnings)
    for collection in layout.collections:
        _capture_collection(collection, reader, roots, character, warnings)

    return CharacterCapture(
        schema_version=1,
        layout_id=layout.layout_id,
        captured_at_utc=datetime.now(UTC).isoformat(),
        source={
            "backend": type(reader).__name__,
            "process": process.as_dict(),
            "roots": {name: f"0x{address:x}" for name, address in sorted(roots.items())},
        },
        character=character,
        warnings=tuple(warnings),
    )
