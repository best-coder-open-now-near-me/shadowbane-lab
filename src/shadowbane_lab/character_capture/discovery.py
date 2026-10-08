"""Discover logged-in characters without asking a tester for process identifiers."""

from __future__ import annotations

from shadowbane_lab.client_observation.native_character_session import NativeCharacterSession
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_vanilla_diagnostics.discovery import WindowsProcessDiscovery

from .binding import CaptureCharacterReader, PrivateServerCharacterReader


def discover_characters():
    found, issues = [], []
    for identity in WindowsProcessDiscovery().find("sb.exe"):
        process = None
        try:
            process = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", identity.process_id)
            if process.process_creation_filetime_utc != identity.process_creation_filetime_utc:
                continue
            # Source protocol is selected from the observed local typed key, never
            # from a guessed server name. Each reader still enforces its exact type.
            for profile, reader in (
                ("Wonderbane", CaptureCharacterReader),
                ("Private SB", PrivateServerCharacterReader),
            ):
                try:
                    session = NativeCharacterSession(reader(process))
                except Exception:
                    continue
                binding = session.binding.as_dict()
                found.append({**binding, "profile": profile})
                break
            else:
                issues.append("A game is open but no supported logged-in character is ready.")
        except Exception:
            issues.append("A game could not be read. Log in fully, then click Find characters.")
        finally:
            if process:
                process.close()
    return found, issues
