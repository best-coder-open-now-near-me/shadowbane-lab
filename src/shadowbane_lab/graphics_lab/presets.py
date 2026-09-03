"""Versioned, atomic preset storage for WonderBane Graphics Lab."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .control import GraphicsParameters

PRESET_SCHEMA_VERSION = 2
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")


class GraphicsPresetStore:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise RuntimeError("LOCALAPPDATA is not available")
            root = Path(local_app_data) / "ShadowbaneLab" / "graphics-lab" / "presets"
        self.root = root

    def list_names(self) -> tuple[str, ...]:
        if not self.root.is_dir():
            return ()
        names: list[str] = []
        for path in self.root.glob("*.json"):
            try:
                name = self._read(path)[0]
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            names.append(name)
        return tuple(sorted(set(names), key=str.casefold))

    def save(self, name: str, parameters: GraphicsParameters) -> Path:
        safe_name = _validate_name(name)
        parameters.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / f"{safe_name}.json"
        payload = {
            "schema_version": PRESET_SCHEMA_VERSION,
            "name": safe_name,
            "updated_at_utc": datetime.now(UTC).isoformat(),
            "parameters": parameters.to_json(),
        }
        data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{safe_name}.", suffix=".tmp", dir=self.root
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return destination

    def load(self, name: str) -> GraphicsParameters:
        safe_name = _validate_name(name)
        path = self.root / f"{safe_name}.json"
        stored_name, parameters = self._read(path)
        if stored_name != safe_name:
            raise ValueError("preset filename and stored name do not match")
        return parameters

    @staticmethod
    def _read(path: Path) -> tuple[str, GraphicsParameters]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("graphics preset must be an object")
        schema_version = payload.get("schema_version")
        if schema_version not in {1, PRESET_SCHEMA_VERSION}:
            raise ValueError("unsupported graphics preset schema")
        name = _validate_name(payload.get("name"))
        parameters = GraphicsParameters.from_json(
            payload.get("parameters"),
            allow_legacy_contour_defaults=schema_version == 1,
        )
        return name, parameters


def _validate_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("preset name must be text")
    name = value.strip()
    if not _SAFE_NAME.fullmatch(name) or name in {".", ".."}:
        raise ValueError(
            "preset name must be 1-64 ordinary letters, numbers, spaces, dots, dashes, "
            "or underscores"
        )
    return name
