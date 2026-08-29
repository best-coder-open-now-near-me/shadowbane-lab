"""Strict, immutable manifests for one node's locally managed clients.

The manifest deliberately contains only operational launch and window-placement
data. Account credentials, character identity, and tactical roles belong to
other systems and are rejected rather than being silently coupled to a PC.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from math import ceil, sqrt
from os import PathLike
from pathlib import Path, PureWindowsPath
from typing import NoReturn

MANAGER_MANIFEST_SCHEMA_VERSION = 1
MAX_MANAGER_CLIENT_SLOTS = 32

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_INVALID_WINDOWS_COMPONENT_PATTERN = re.compile(r'[<>:"|?*]|[\x00-\x1f]')
_DISPLAY_RESOLUTION_PATTERN = re.compile(r"([1-9][0-9]{0,4})x([1-9][0-9]{0,4})\Z")
_MAX_DISPLAY_DIMENSION = 16_384
_SIGNED_WIN32_MIN = -(2**31)
_SIGNED_WIN32_MAX = (2**31) - 1
_LAUNCH_FLAG_OPTIONS = {
    "-windowed": "windowed",
    "--windowed": "windowed",
    "--client": "launcher-client",
}
_LAUNCH_VALUE_OPTIONS = {"-resolution": "resolution"}
_LAUNCH_ENVIRONMENT_VALUES: dict[str, frozenset[str | None]] = {
    "GALLIUM_DRIVER": frozenset({"llvmpipe"}),
    "LIBGL_ALWAYS_SOFTWARE": frozenset({"true"}),
    "MESA_EXTENSION_MAX_YEAR": frozenset({"2001"}),
    "MESA_GLSL_VERSION_OVERRIDE": frozenset({None}),
    "MESA_GL_VERSION_OVERRIDE": frozenset({None}),
}
_LAUNCH_GRAMMAR = (
    "-windowed or --windowed, --client, and -resolution WIDTHxHEIGHT "
    f"(each dimension 1..{_MAX_DISPLAY_DIMENSION})"
)


class ManagerManifestError(ValueError):
    """Raised when a manager manifest is malformed or violates its boundary."""


def _fail(message: str) -> NoReturn:
    raise ManagerManifestError(message)


def _require_exact_fields(
    value: object,
    *,
    location: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(f"{location} must be an object")
    keys = set(value)
    if any(not isinstance(key, str) for key in keys):
        _fail(f"{location} field names must be strings")
    unknown = keys - required - optional
    if unknown:
        _fail(f"{location} contains unknown fields: {', '.join(sorted(unknown))}")
    missing = required - keys
    if missing:
        _fail(f"{location} is missing required fields: {', '.join(sorted(missing))}")
    return value


def _parse_identifier(value: object, *, location: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        _fail(
            f"{location} must start with an ASCII letter or digit and contain only "
            "letters, digits, '.', '_', or '-' (maximum 128 characters)"
        )
    return value


def _parse_absolute_windows_path(
    value: object,
    *,
    location: str,
    require_file_name: bool = False,
) -> PureWindowsPath:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{location} must be a canonical absolute Windows path")
    if "\0" in value or "\r" in value or "\n" in value:
        _fail(f"{location} must not contain control characters")
    if require_file_name and value.endswith(("\\", "/")):
        _fail(f"{location} must identify an executable file, not a directory")
    path = PureWindowsPath(value)
    if not path.is_absolute():
        _fail(f"{location} must be an absolute Windows path")
    if ".." in path.parts:
        _fail(f"{location} must not contain parent-directory traversal")
    for part in path.parts[1:]:
        if _INVALID_WINDOWS_COMPONENT_PATTERN.search(part):
            _fail(f"{location} contains characters that are invalid in Windows paths")
        if part.rstrip(" .") != part:
            _fail(f"{location} contains a Windows path component ending in a space or dot")
    if require_file_name and (not path.name or path.name in {".", ".."}):
        _fail(f"{location} must identify an executable file")
    return path


def _parse_arguments(value: object, *, location: str) -> tuple[str, ...]:
    """Parse the complete allowlisted operational argv grammar.

    The public manifest remains a JSON token array so the resulting tuple can be
    passed directly to ``subprocess.Popen(shell=False)``.  It is not an opaque argv
    escape hatch: only the flags declared above and the value belonging to
    ``-resolution`` are accepted.
    """

    if not isinstance(value, list):
        _fail(f"{location} must be a JSON array of separate argument tokens")
    arguments: list[str] = []
    seen_options: set[str] = set()
    index = 0
    while index < len(value):
        argument = value[index]
        argument_location = f"{location}[{index}]"
        _require_launch_token(argument, location=argument_location)
        assert isinstance(argument, str)

        option_key = _LAUNCH_FLAG_OPTIONS.get(argument)
        if option_key is not None:
            _reject_duplicate_launch_option(
                option_key,
                seen_options=seen_options,
                location=argument_location,
            )
            arguments.append(argument)
            index += 1
            continue

        option_key = _LAUNCH_VALUE_OPTIONS.get(argument)
        if option_key is None:
            _fail(
                f"{argument_location} is not an allowed operational launch option; "
                f"accepted grammar: {_LAUNCH_GRAMMAR}"
            )
        _reject_duplicate_launch_option(
            option_key,
            seen_options=seen_options,
            location=argument_location,
        )
        value_index = index + 1
        if value_index >= len(value):
            _fail(f"{argument_location} requires a following WIDTHxHEIGHT value")
        option_value = value[value_index]
        value_location = f"{location}[{value_index}]"
        _require_launch_token(option_value, location=value_location)
        assert isinstance(option_value, str)
        _parse_display_resolution(option_value, location=value_location)
        arguments.extend((argument, option_value))
        index += 2
    return tuple(arguments)


def _parse_environment(
    value: object,
    *,
    location: str,
) -> tuple[tuple[str, str | None], ...]:
    if not isinstance(value, Mapping):
        _fail(f"{location} must be an object")
    parsed: list[tuple[str, str | None]] = []
    for name, setting in value.items():
        if not isinstance(name, str) or name not in _LAUNCH_ENVIRONMENT_VALUES:
            _fail(
                f"{location} contains unsupported variable {name!r}; allowed variables: "
                + ", ".join(sorted(_LAUNCH_ENVIRONMENT_VALUES))
            )
        if not (setting is None or isinstance(setting, str)) or (
            setting not in _LAUNCH_ENVIRONMENT_VALUES[name]
        ):
            allowed = ", ".join(
                "null" if item is None else repr(item)
                for item in sorted(
                    _LAUNCH_ENVIRONMENT_VALUES[name],
                    key=lambda item: "" if item is None else item,
                )
            )
            _fail(f"{location}.{name} must be one of: {allowed}")
        parsed.append((name, setting))
    return tuple(sorted(parsed))


def _require_launch_token(value: object, *, location: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value:
        _fail(f"{location} must be a non-empty string without NUL characters")
    if "\r" in value or "\n" in value:
        _fail(f"{location} must not contain line breaks")


def _reject_duplicate_launch_option(
    option_key: str,
    *,
    seen_options: set[str],
    location: str,
) -> None:
    if option_key in seen_options:
        _fail(f"{location} duplicates launch option {option_key!r}")
    seen_options.add(option_key)


def _parse_display_resolution(value: str, *, location: str) -> tuple[int, int]:
    match = _DISPLAY_RESOLUTION_PATTERN.fullmatch(value)
    if match is None:
        _fail(f"{location} must be a canonical WIDTHxHEIGHT display resolution")
    width, height = (int(component) for component in match.groups())
    if width > _MAX_DISPLAY_DIMENSION or height > _MAX_DISPLAY_DIMENSION:
        _fail(f"{location} dimensions must be between 1 and {_MAX_DISPLAY_DIMENSION} pixels")
    return width, height


def _parse_executable_names(value: object, *, location: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        _fail(f"{location} must be a non-empty JSON array of executable file names")
    names: list[str] = []
    normalized: set[str] = set()
    for index, name in enumerate(value):
        item_location = f"{location}[{index}]"
        if (
            not isinstance(name, str)
            or not name
            or name != name.strip()
            or "\0" in name
            or PureWindowsPath(name).name != name
            or name in {".", ".."}
            or name.rstrip(" .") != name
            or _INVALID_WINDOWS_COMPONENT_PATTERN.search(name)
        ):
            _fail(f"{item_location} must be a canonical executable file name")
        key = name.casefold()
        if key in normalized:
            _fail(f"{location} must not contain duplicate names (case-insensitive)")
        normalized.add(key)
        names.append(name)
    return tuple(names)


def _parse_integer(value: object, *, location: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{location} must be an integer")
    if positive and value <= 0:
        _fail(f"{location} must be a positive integer")
    return value


def _parse_win32_integer(
    value: object,
    *,
    location: str,
    positive: bool = False,
) -> int:
    parsed = _parse_integer(value, location=location, positive=positive)
    lower_bound = 1 if positive else _SIGNED_WIN32_MIN
    if parsed < lower_bound or parsed > _SIGNED_WIN32_MAX:
        _fail(f"{location} must fit the signed 32-bit Win32 coordinate range")
    return parsed


@dataclass(frozen=True, slots=True)
class WindowTile:
    """A non-activating target rectangle in virtual-screen coordinates."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        _parse_win32_integer(self.left, location="window_tile.left")
        _parse_win32_integer(self.top, location="window_tile.top")
        _parse_win32_integer(self.width, location="window_tile.width", positive=True)
        _parse_win32_integer(self.height, location="window_tile.height", positive=True)

    @property
    def assignment(self) -> tuple[int, int, int, int]:
        """Return the immutable key used to detect duplicate tile ownership."""

        return (self.left, self.top, self.width, self.height)

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class ClientLaunchConfig:
    """A direct, shell-free launch command and its explicit working directory."""

    executable: PureWindowsPath
    arguments: tuple[str, ...]
    working_directory: PureWindowsPath
    environment: tuple[tuple[str, str | None], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.executable, PureWindowsPath) or not self.executable.is_absolute():
            raise ManagerManifestError("launch.executable must be an absolute PureWindowsPath")
        _parse_absolute_windows_path(
            str(self.executable),
            location="launch.executable",
            require_file_name=True,
        )
        if not isinstance(self.working_directory, PureWindowsPath) or not (
            self.working_directory.is_absolute()
        ):
            raise ManagerManifestError(
                "launch.working_directory must be an absolute PureWindowsPath"
            )
        _parse_absolute_windows_path(
            str(self.working_directory),
            location="launch.working_directory",
        )
        if not isinstance(self.arguments, tuple):
            raise ManagerManifestError("launch.arguments must be an immutable tuple")
        _parse_arguments(list(self.arguments), location="launch.arguments")
        if not isinstance(self.environment, tuple):
            raise ManagerManifestError("launch.environment must be an immutable tuple")
        if any(not isinstance(item, tuple) or len(item) != 2 for item in self.environment):
            raise ManagerManifestError(
                "launch.environment must contain immutable name/value pairs"
            )
        if any(not isinstance(item[0], str) for item in self.environment):
            raise ManagerManifestError("launch.environment variable names must be strings")
        environment_names = [item[0] for item in self.environment]
        if len(environment_names) != len(set(environment_names)):
            raise ManagerManifestError("launch.environment variable names must be unique")
        parsed_environment = _parse_environment(
            dict(self.environment),
            location="launch.environment",
        )
        if parsed_environment != self.environment:
            raise ManagerManifestError(
                "launch.environment must contain unique, sorted immutable pairs"
            )

    @property
    def command(self) -> tuple[str, ...]:
        """Return tokens suitable for a direct ``subprocess.Popen`` call."""

        return (str(self.executable), *self.arguments)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "executable": str(self.executable),
            "arguments": list(self.arguments),
            "working_directory": str(self.working_directory),
        }
        if self.environment:
            payload["environment"] = dict(self.environment)
        return payload


@dataclass(frozen=True, slots=True)
class ManagedClientConfig:
    """Operational configuration for one logical local client slot."""

    client_id: str
    launch: ClientLaunchConfig
    expected_process_directory: PureWindowsPath
    expected_executable_names: tuple[str, ...]
    window_tile: WindowTile | None = None

    def __post_init__(self) -> None:
        _parse_identifier(self.client_id, location="client_id")
        if not isinstance(self.launch, ClientLaunchConfig):
            raise ManagerManifestError("launch must be ClientLaunchConfig")
        if not isinstance(self.expected_process_directory, PureWindowsPath) or not (
            self.expected_process_directory.is_absolute()
        ):
            raise ManagerManifestError(
                "expected_process_directory must be an absolute PureWindowsPath"
            )
        _parse_absolute_windows_path(
            str(self.expected_process_directory),
            location="expected_process_directory",
        )
        if not isinstance(self.expected_executable_names, tuple):
            raise ManagerManifestError("expected_executable_names must be an immutable tuple")
        _parse_executable_names(
            list(self.expected_executable_names),
            location="expected_executable_names",
        )
        if self.window_tile is not None and not isinstance(self.window_tile, WindowTile):
            raise ManagerManifestError("window_tile must be WindowTile or None")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "client_id": self.client_id,
            "launch": self.launch.to_dict(),
            "expected_process_directory": str(self.expected_process_directory),
            "expected_executable_names": list(self.expected_executable_names),
        }
        if self.window_tile is not None:
            payload["window_tile"] = self.window_tile.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ManagerManifest:
    """Complete local topology for a manager node, without strategic ownership."""

    node_id: str
    clients: tuple[ManagedClientConfig, ...]
    schema_version: int = field(default=MANAGER_MANIFEST_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        if self.schema_version != MANAGER_MANIFEST_SCHEMA_VERSION:
            raise ManagerManifestError(f"schema_version must be {MANAGER_MANIFEST_SCHEMA_VERSION}")
        _parse_identifier(self.node_id, location="node_id")
        if not isinstance(self.clients, tuple) or not self.clients:
            raise ManagerManifestError("clients must be a non-empty immutable tuple")
        if any(not isinstance(client, ManagedClientConfig) for client in self.clients):
            raise ManagerManifestError("clients must contain ManagedClientConfig values")
        client_ids = [client.client_id.casefold() for client in self.clients]
        if len(client_ids) != len(set(client_ids)):
            raise ManagerManifestError("client_id values must be unique (case-insensitive)")
        tile_assignments = [
            client.window_tile.assignment
            for client in self.clients
            if client.window_tile is not None
        ]
        if len(tile_assignments) != len(set(tile_assignments)):
            raise ManagerManifestError("window_tile assignments must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "clients": [client.to_dict() for client in self.clients],
        }


def _parse_window_tile(value: object, *, location: str) -> WindowTile:
    payload = _require_exact_fields(
        value,
        location=location,
        required=frozenset({"left", "top", "width", "height"}),
    )
    return WindowTile(
        left=_parse_win32_integer(payload["left"], location=f"{location}.left"),
        top=_parse_win32_integer(payload["top"], location=f"{location}.top"),
        width=_parse_win32_integer(payload["width"], location=f"{location}.width", positive=True),
        height=_parse_win32_integer(
            payload["height"], location=f"{location}.height", positive=True
        ),
    )


def _parse_launch(value: object, *, location: str) -> ClientLaunchConfig:
    payload = _require_exact_fields(
        value,
        location=location,
        required=frozenset({"executable", "arguments", "working_directory"}),
        optional=frozenset({"environment"}),
    )
    return ClientLaunchConfig(
        executable=_parse_absolute_windows_path(
            payload["executable"],
            location=f"{location}.executable",
            require_file_name=True,
        ),
        arguments=_parse_arguments(payload["arguments"], location=f"{location}.arguments"),
        working_directory=_parse_absolute_windows_path(
            payload["working_directory"],
            location=f"{location}.working_directory",
        ),
        environment=(
            _parse_environment(payload["environment"], location=f"{location}.environment")
            if "environment" in payload
            else ()
        ),
    )


def _parse_client(value: object, *, location: str) -> ManagedClientConfig:
    payload = _require_exact_fields(
        value,
        location=location,
        required=frozenset(
            {
                "client_id",
                "launch",
                "expected_process_directory",
                "expected_executable_names",
            }
        ),
        optional=frozenset({"window_tile"}),
    )
    tile = (
        _parse_window_tile(payload["window_tile"], location=f"{location}.window_tile")
        if "window_tile" in payload
        else None
    )
    return ManagedClientConfig(
        client_id=_parse_identifier(payload["client_id"], location=f"{location}.client_id"),
        launch=_parse_launch(payload["launch"], location=f"{location}.launch"),
        expected_process_directory=_parse_absolute_windows_path(
            payload["expected_process_directory"],
            location=f"{location}.expected_process_directory",
        ),
        expected_executable_names=_parse_executable_names(
            payload["expected_executable_names"],
            location=f"{location}.expected_executable_names",
        ),
        window_tile=tile,
    )


def expand_manager_slots(
    manifest: ManagerManifest,
    total_count: int,
    *,
    display_left: int = 0,
    display_top: int = 0,
    display_width: int = 1920,
    display_height: int = 955,
) -> ManagerManifest:
    """Expand a manifest and deterministically retile all slots on one display.

    Existing slot launch and process selectors are preserved. New slots clone the
    first reviewed operational configuration and receive fresh canonical client IDs.
    Shrinking is deliberately rejected because it would discard slot ownership.
    """

    if not isinstance(manifest, ManagerManifest):
        raise ValueError("manifest must be ManagerManifest")
    for value, field_name in (
        (total_count, "total_count"),
        (display_width, "display_width"),
        (display_height, "display_height"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ManagerManifestError(f"{field_name} must be a positive integer")
    for value, field_name in ((display_left, "display_left"), (display_top, "display_top")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ManagerManifestError(f"{field_name} must be an integer")
    if total_count > MAX_MANAGER_CLIENT_SLOTS:
        raise ManagerManifestError(
            f"total_count must not exceed {MAX_MANAGER_CLIENT_SLOTS} local client slots"
        )
    if total_count < len(manifest.clients):
        raise ManagerManifestError(
            "slot configuration cannot shrink a manifest; remove slots only through reviewed JSON"
        )
    if display_width > _MAX_DISPLAY_DIMENSION or display_height > _MAX_DISPLAY_DIMENSION:
        raise ManagerManifestError(
            f"display dimensions must not exceed {_MAX_DISPLAY_DIMENSION}"
        )

    columns = ceil(sqrt(total_count))
    rows = ceil(total_count / columns)
    if display_width < columns or display_height < rows:
        raise ManagerManifestError("display dimensions are too small for the requested slot count")

    existing_ids = {client.client_id.casefold() for client in manifest.clients}
    new_ids: list[str] = []
    candidate_number = 1
    while len(manifest.clients) + len(new_ids) < total_count:
        candidate = f"client-{candidate_number:02d}"
        candidate_number += 1
        if candidate.casefold() not in existing_ids:
            existing_ids.add(candidate.casefold())
            new_ids.append(candidate)

    clients = [*manifest.clients]
    template = manifest.clients[0]
    clients.extend(replace(template, client_id=client_id) for client_id in new_ids)

    tiled: list[ManagedClientConfig] = []
    for index, client in enumerate(clients):
        column = index % columns
        row = index // columns
        left = display_left + (display_width * column) // columns
        right = display_left + (display_width * (column + 1)) // columns
        top = display_top + (display_height * row) // rows
        bottom = display_top + (display_height * (row + 1)) // rows
        tiled.append(
            replace(
                client,
                window_tile=WindowTile(
                    left=left,
                    top=top,
                    width=right - left,
                    height=bottom - top,
                ),
            )
        )
    return ManagerManifest(node_id=manifest.node_id, clients=tuple(tiled))


def parse_manager_manifest(payload: object) -> ManagerManifest:
    """Validate an already-decoded JSON-compatible manager manifest."""

    root = _require_exact_fields(
        payload,
        location="manifest",
        required=frozenset({"schema_version", "node_id", "clients"}),
    )
    schema_version = root["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != MANAGER_MANIFEST_SCHEMA_VERSION
    ):
        _fail(f"manifest.schema_version must be {MANAGER_MANIFEST_SCHEMA_VERSION}")
    clients_payload = root["clients"]
    if not isinstance(clients_payload, list) or not clients_payload:
        _fail("manifest.clients must be a non-empty JSON array")
    clients = tuple(
        _parse_client(client, location=f"manifest.clients[{index}]")
        for index, client in enumerate(clients_payload)
    )
    return ManagerManifest(
        node_id=_parse_identifier(root["node_id"], location="manifest.node_id"),
        clients=clients,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON object contains duplicate field {key!r}")
        result[key] = value
    return result


def loads_manager_manifest(source: str | bytes | bytearray) -> ManagerManifest:
    """Decode and validate a manager manifest JSON document."""

    if not isinstance(source, (str, bytes, bytearray)):
        raise TypeError("source must be str, bytes, or bytearray")
    try:
        payload = json.loads(
            source,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=lambda value: _fail(f"JSON constant {value!r} is not permitted"),
        )
    except ManagerManifestError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManagerManifestError(f"invalid manager manifest JSON: {exc}") from exc
    return parse_manager_manifest(payload)


def load_manager_manifest(path: str | PathLike[str]) -> ManagerManifest:
    """Load and validate a UTF-8 manager manifest from disk."""

    return loads_manager_manifest(Path(path).read_bytes())


__all__ = [
    "MANAGER_MANIFEST_SCHEMA_VERSION",
    "MAX_MANAGER_CLIENT_SLOTS",
    "ClientLaunchConfig",
    "ManagedClientConfig",
    "ManagerManifest",
    "ManagerManifestError",
    "WindowTile",
    "expand_manager_slots",
    "load_manager_manifest",
    "loads_manager_manifest",
    "parse_manager_manifest",
]
