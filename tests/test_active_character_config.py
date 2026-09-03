import hashlib
import io
import json
import struct
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from shadowbane_lab.cli import main
from shadowbane_lab.client_input.character_config import (
    CharacterConfigSession,
    open_active_character_config,
)
from shadowbane_lab.client_observation.native_character_config import (
    REVIEWED_CHARACTER_CONFIG_LAYOUTS,
    ActiveCharacterError,
    ActiveCharacterIdentity,
    NativeCharacterConfigReader,
)


class CharacterMemory:
    pointer_size = 4
    pid = 4320
    process_creation_filetime_utc = 134327529709130522
    executable_name = "sb.exe"
    executable_sha256 = REVIEWED_CHARACTER_CONFIG_LAYOUTS[0].executable_sha256
    base_address = 0x400000
    player = 0x10000000

    def __init__(self, root: Path):
        self.executable_path = root / "sb.exe"
        self.executable_path.write_bytes(b"test executable; memory is synthetic")
        (root / "Config").mkdir()
        self.memory = {}
        self.reads = []
        self.closed = False
        self.layout = REVIEWED_CHARACTER_CONFIG_LAYOUTS[0]
        self.set_identity("testercle", "Wonderbane")

    def put(self, address, value):
        self.memory.update({address + i: byte for i, byte in enumerate(value)})

    def set_identity(self, name, server):
        self.put(self.base_address + self.layout.player_pointer_rva, struct.pack("<I", self.player))
        self.put(self.base_address + self.layout.character_config_enabled_rva, b"\x01")
        self.put(
            self.player, struct.pack("<I", self.base_address + self.layout.character_vtable_rva)
        )
        for offset, buffer, value in (
            (self.layout.name_offset, 0x20000000, name),
            (self.layout.server_offset, 0x20001000, server),
        ):
            raw = value.encode("utf-16-le")
            self.put(
                self.player + offset,
                struct.pack("<IIII", 0, buffer, buffer + len(raw), buffer + len(raw) + 2),
            )
            self.put(buffer, raw + b"\x00\x00")

    def read(self, address, size):
        assert not self.closed
        assert 0 < size <= 64
        self.reads.append((address, size))
        return bytes(self.memory[address + i] for i in range(size))

    def close(self):
        self.closed = True


def write_profile(memory, name="testercle", server="Wonderbane", content=b"saved config"):
    identity = ActiveCharacterIdentity(memory.player, name, server)
    path = memory.executable_path.parent / "Config" / identity.config_filename
    path.write_bytes(content)
    return path


def test_selects_active_character_among_five_saved_files(tmp_path):
    memory = CharacterMemory(tmp_path)
    for name in ("bartHarley", "paul", "testercle", "tiny", "treehugger"):
        write_profile(memory, name)
    session = CharacterConfigSession(NativeCharacterConfigReader(memory))
    binding = session.binding
    assert binding.identity.character_name == "testercle"
    assert binding.config_path.name == (
        "SCREEN_GAME_0074006500730074006500720063006C0065_Wonderbane.cfg"
    )
    assert binding.config_sha256 == hashlib.sha256(b"saved config").hexdigest()
    assert (
        binding.as_dict()["process_creation_filetime_utc"] == memory.process_creation_filetime_utc
    )
    session.require_current()
    session.close()
    assert memory.closed


@pytest.mark.parametrize("name", ["a", "bartHarley", "\u00c9lan", "\U0001f680"])
def test_filename_encoding_uses_utf16_code_units(name):
    identity = ActiveCharacterIdentity(0x10000, name, "Wonderbane")
    encoded = identity.config_filename.removeprefix("SCREEN_GAME_").split("_")[0]
    assert bytes.fromhex(encoded).decode("utf-16-be") == name


def test_refuses_other_character_server_or_client_root(tmp_path):
    memory = CharacterMemory(tmp_path)
    expected = write_profile(memory)
    wrong = [write_profile(memory, "tiny"), write_profile(memory, server="Other")]
    other_root = tmp_path / "other-client"
    other_root.mkdir()
    other = other_root / expected.name
    other.write_bytes(expected.read_bytes())
    wrong.append(other)
    for path in wrong:
        with pytest.raises(ActiveCharacterError, match="does not match active"):
            CharacterConfigSession(NativeCharacterConfigReader(memory), explicit_path=path)
    assert (
        CharacterConfigSession(
            NativeCharacterConfigReader(memory), explicit_path=expected
        ).binding.config_path
        == expected
    )


def test_missing_active_file_does_not_fall_back_to_only_saved_file(tmp_path):
    memory = CharacterMemory(tmp_path)
    write_profile(memory, "tiny")
    with pytest.raises(ActiveCharacterError, match="profile is unavailable"):
        CharacterConfigSession(NativeCharacterConfigReader(memory))


@pytest.mark.parametrize(
    "field,value",
    [
        ("executable_sha256", "ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13"),
        ("executable_name", "other.exe"),
        ("pointer_size", 8),
        ("process_creation_filetime_utc", 0),
    ],
)
def test_unknown_build_and_unbound_process_fail_before_memory_reads(tmp_path, field, value):
    memory = CharacterMemory(tmp_path)
    setattr(memory, field, value)
    with pytest.raises(ActiveCharacterError):
        NativeCharacterConfigReader(memory)
    assert not memory.reads


@pytest.mark.parametrize(
    "case",
    [
        "logged_out",
        "null",
        "bad_vtable",
        "odd_string",
        "unterminated",
        "large_string",
        "partial",
        "invalid_utf16",
    ],
)
def test_rejects_absent_or_corrupt_identity(tmp_path, case):
    memory = CharacterMemory(tmp_path)
    layout = memory.layout
    if case == "logged_out":
        memory.put(memory.base_address + layout.character_config_enabled_rva, b"\x00")
    elif case == "null":
        memory.put(memory.base_address + layout.player_pointer_rva, b"\x00" * 4)
    elif case == "bad_vtable":
        memory.put(memory.player, b"\x00" * 4)
    elif case in ("odd_string", "large_string"):
        length = 3 if case == "odd_string" else 130
        memory.put(memory.player + layout.name_offset + 8, struct.pack("<I", 0x20000000 + length))
    elif case == "unterminated":
        memory.put(0x20000000 + len("testercle") * 2, b"xx")
    elif case == "invalid_utf16":
        memory.put(0x20000000, b"\x00\xd8")
    elif case == "partial":
        memory.read = lambda address, size: b""
    with pytest.raises(ActiveCharacterError):
        NativeCharacterConfigReader(memory).observe()


@pytest.mark.parametrize(
    "name,server",
    [("../evil", "Wonderbane"), ("a", "../evil"), ("a\x00b", "Wonderbane"), (" a", "Wonderbane")],
)
def test_rejects_unsafe_filename_values(tmp_path, name, server):
    memory = CharacterMemory(tmp_path)
    memory.set_identity(name, server)
    with pytest.raises(ActiveCharacterError):
        NativeCharacterConfigReader(memory).observe()


def test_rejects_torn_identity(tmp_path):
    memory = CharacterMemory(tmp_path)
    reader = NativeCharacterConfigReader(memory)
    first = reader.observe()
    with patch.object(
        reader, "_snapshot", side_effect=[first, replace(first, character_name="tiny")]
    ):
        with pytest.raises(ActiveCharacterError, match="changed during"):
            reader.observe()


@pytest.mark.parametrize("change", ["character", "server", "player", "file", "exit"])
def test_session_revokes_on_change_and_never_silently_rebinds(tmp_path, change):
    memory = CharacterMemory(tmp_path)
    path = write_profile(memory)
    session = CharacterConfigSession(NativeCharacterConfigReader(memory))
    if change == "character":
        memory.set_identity("tiny", "Wonderbane")
    elif change == "server":
        memory.set_identity("testercle", "Other")
    elif change == "player":
        memory.player += 0x10000
        memory.set_identity("testercle", "Wonderbane")
    elif change == "file":
        path.write_bytes(b"edited config")
    elif change == "exit":
        memory.closed = True
    with pytest.raises(ActiveCharacterError):
        session.require_current()
    memory.closed = False
    memory.set_identity("testercle", "Wonderbane")
    path.write_bytes(b"saved config")
    with pytest.raises(ActiveCharacterError, match="revoked"):
        session.require_current()


def test_next_initialization_resolves_new_character(tmp_path):
    memory = CharacterMemory(tmp_path)
    write_profile(memory)
    write_profile(memory, "tiny")
    assert (
        CharacterConfigSession(NativeCharacterConfigReader(memory)).binding.identity.character_name
        == "testercle"
    )
    memory.set_identity("tiny", "Wonderbane")
    assert (
        CharacterConfigSession(NativeCharacterConfigReader(memory)).binding.identity.character_name
        == "tiny"
    )


def test_factory_binds_requested_pid_and_closes_on_failure(tmp_path):
    memory = CharacterMemory(tmp_path)
    with patch(
        "shadowbane_lab.client_input.character_config.WindowsReadOnlyProcessMemory"
    ) as factory:
        factory.open_for_process.return_value = memory
        with pytest.raises(ActiveCharacterError, match="unavailable"):
            open_active_character_config(process_id=4320)
        factory.open_for_process.assert_called_once_with("sb.exe", 4320)
        factory.open_unique.assert_not_called()
    assert memory.closed


def test_factory_uses_unique_process_only_for_read_only_inspection(tmp_path):
    memory = CharacterMemory(tmp_path)
    write_profile(memory)
    with patch(
        "shadowbane_lab.client_input.character_config.WindowsReadOnlyProcessMemory"
    ) as factory:
        factory.open_unique.return_value = memory
        with open_active_character_config() as session:
            assert session.binding.process_id == 4320
        factory.open_unique.assert_called_once_with("sb.exe")
    assert memory.closed


def test_read_only_cli_reports_selected_character_and_saved_hotbar(tmp_path):
    from tests.test_arcane_hotbar import _CAPTURED_HOTBAR

    memory = CharacterMemory(tmp_path)
    path = write_profile(memory, content=_CAPTURED_HOTBAR.encode())
    output = io.StringIO()
    with (
        patch(
            "shadowbane_lab.client_input.character_config.WindowsReadOnlyProcessMemory"
        ) as factory,
        patch("shadowbane_lab.cli.PyAutoGuiBackend") as backend,
        redirect_stdout(output),
    ):
        factory.open_for_process.return_value = memory
        result = main(("client", "inspect-active-profile", "--process-id", "4320", "--json"))
    payload = json.loads(output.getvalue())
    assert result == 0
    assert payload["character_name"] == "testercle"
    assert payload["server_name"] == "Wonderbane"
    assert Path(payload["config_path"]) == path
    assert {"key": "f2", "power": "ASS-013"} in payload["active_slots"]
    backend.assert_not_called()
    assert memory.closed


def test_read_only_cli_reports_closed_client_without_input():
    output = io.StringIO()
    with (
        patch(
            "shadowbane_lab.client_input.character_config.WindowsReadOnlyProcessMemory"
        ) as factory,
        patch("shadowbane_lab.cli.PyAutoGuiBackend") as backend,
        redirect_stdout(output),
    ):
        factory.open_unique.side_effect = ActiveCharacterError("no running process named sb.exe")
        result = main(("client", "inspect-active-profile", "--json"))
    assert result == 2
    assert "no running process" in json.loads(output.getvalue())["error"]
    backend.assert_not_called()


def test_pve_ambiguous_or_unavailable_identity_never_opens_input_backend():
    from shadowbane_lab.client_input import (
        StaticWindowInspector,
        WindowBounds,
        WindowSnapshot,
        load_calibration,
    )

    template = Path(__file__).parents[1] / "configs" / "wonderbane-pve.template.json"
    calibration = replace(load_calibration(template), live_input_enabled=True)
    snapshot = WindowSnapshot(
        executable_name="sb.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(
            0, 0, calibration.target.reference_width, calibration.target.reference_height
        ),
        dpi_scale=calibration.target.dpi_scale,
        is_foreground=True,
        is_visible=True,
        process_id=4320,
    )
    output = io.StringIO()
    with (
        patch("shadowbane_lab.cli.load_calibration", return_value=calibration),
        patch(
            "shadowbane_lab.cli.WindowsForegroundWindowInspector",
            return_value=StaticWindowInspector(snapshot),
        ),
        patch(
            "shadowbane_lab.cli.open_active_character_config",
            side_effect=ActiveCharacterError("active character changed"),
        ) as resolve,
        patch("shadowbane_lab.cli.PyAutoGuiBackend") as backend,
        patch("shadowbane_lab.cli.PvERunner") as runner,
        redirect_stdout(output),
    ):
        result = main(
            (
                "client",
                "run-pve",
                "--client-profile",
                str(template),
                "--policy",
                "proc-assassin",
                "--wait-for-client-seconds",
                "0",
                "--live",
                "--json",
            )
        )
    assert result == 2
    assert "active character changed" in json.loads(output.getvalue())["error"]
    resolve.assert_called_once_with(process_id=4320, explicit_path=None)
    backend.assert_not_called()
    runner.assert_not_called()
