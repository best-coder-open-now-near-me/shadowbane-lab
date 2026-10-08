"""Passive, exact-lifetime character labels for existing-client selection."""

from __future__ import annotations

import hashlib
import json
import ntpath
from dataclasses import dataclass

from shadowbane_lab.client_observation.native_character_session import open_native_character_session

from .model import ClientInstanceSnapshot


@dataclass(frozen=True, slots=True)
class CharacterChoice:
    name: str | None = None
    server: str | None = None
    token: str | None = None

    def to_dict(self):
        return {
            "state": "available" if self.token else "unavailable",
            "name": self.name,
            "server": self.server,
            "token": self.token,
        }


class NativeCharacterChoices:
    """Read one canonical native session; no owner, transport or input commands."""

    def inspect(self, client: ClientInstanceSnapshot) -> CharacterChoice:
        try:
            with open_native_character_session(process_id=client.process_id) as session:
                binding = session.binding
                if (binding.process_id, binding.process_creation_filetime_utc) != (
                    client.process_id,
                    client.process_started_at_100ns,
                ) or ntpath.normcase(
                    ntpath.normpath(str(binding.executable_path))
                ) != ntpath.normcase(ntpath.normpath(client.executable_path)):
                    return CharacterChoice()
                session.require_current()
                identity = binding.identity
                # Character object identity is part of the selection, not just its label.
                payload = [
                    client.instance_id,
                    client.window_handle,
                    binding.as_dict(),
                    identity.player_pointer,
                ]
                token = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                return CharacterChoice(identity.character_name, identity.server_name, token)
        except (OSError, RuntimeError, ValueError):
            # Login/loading and unqualified/unreadable identity cannot name a character.
            return CharacterChoice()
