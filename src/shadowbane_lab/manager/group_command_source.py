"""Passive exact-client inputs for the worker-owned group command service."""
from contextlib import ExitStack

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.event_reader import WindowsSharedMemorySnapshotReader
from shadowbane_lab.client_extension.group_publication import GroupPublicationReader
from shadowbane_lab.client_extension.movement_session import read_snapshot
from shadowbane_lab.client_extension.movement_wire import BINDINGS, TERMINAL
from shadowbane_lab.client_extension.tracking_publication import tick_ms
from shadowbane_lab.client_observation.native_character_session import open_native_character_session
from shadowbane_lab.client_observation.native_group import (
    NativeGroupReader,
    load_bundled_native_group_profile,
)
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationReader,
    load_bundled_native_character_population_profile,
)
from shadowbane_lab.pve.settings import load_pve_settings


class NativeGroupCommandSource:
    def __init__(self, binding):
        self.binding = binding
        self.lifetime = (binding.game_process_id, binding.game_process_started_at_100ns)
        memory = WindowsSharedMemorySnapshotReader()
        self.messages = GroupPublicationReader(*self.lifetime, memory, kind="messages")
        self.updates = GroupPublicationReader(*self.lifetime, memory, kind="updates")
        self.resources = ExitStack()
        self.character = None
        self.group = None
        self.population = None

    def read(self):
        # Advance receive cursors even when character observation is unavailable.
        messages, updates = self.messages.drain(), self.updates.drain()
        try:
            if self.character is None:
                self.character = self.resources.enter_context(open_native_character_session(
                    process_id=self.binding.game_process_id))
                born = self.character.binding.process_creation_filetime_utc
                if born != self.binding.game_process_started_at_100ns:
                    raise ValueError("group observer opened another game lifetime")
                process = self.character.reader.process
                self.group = NativeGroupReader(load_bundled_native_group_profile(), process)
                self.population = NativeCharacterPopulationReader(
                    load_bundled_native_character_population_profile(), process)
            self.character.require_current()
            scene = read_snapshot(NativeClientProcessIdentity(*self.lifetime),
                                  self.binding.game_window_handle)
            now = tick_ms()
            if (not scene.flags & BINDINGS or scene.flags & TERMINAL
                    or not scene.grant.scene or not 0 <= now - scene.tick <= 500):
                raise ValueError("current native group scene unavailable")
            context = self.group.observe_context()
            roster = self.group.observe()
            population = self.population.observe()
            after = self.group.observe_context()
            local = self.character.binding.object_key
            local_key = (local.object_type, local.object_uuid)
            keys = {(r[2], r[3]) for r in context.members}
            members = {(m.object_type, m.object_uuid): m.first_name for m in roster.members}
            if context != after or keys != set(members):
                raise ValueError("group identity changed during command observation")
            if population.local_player_object_key != local:
                raise ValueError("loaded group positions belong to another character")
            self.character.require_current()
            final_scene = read_snapshot(NativeClientProcessIdentity(*self.lifetime),
                                        self.binding.game_window_handle)
            if final_scene.grant.scene != scene.grant.scene:
                raise ValueError("native scene changed during group observation")
            positions = {
                (c.object_key.object_type, c.object_key.object_uuid): (c.lt, c.lg)
                for c in population.characters
                if c.object_key is not None and c.character_kind.value == "player"
                and (c.object_key.object_type, c.object_key.object_uuid) in keys
            }
            current = {"scene": scene.grant.scene, "local": local_key,
                       "group_digest": context.digest.hex(), "members": members,
                       "positions": positions,
                       "enabled": load_pve_settings(
                           self.character.binding.identity).group_commands.enabled}
            return messages, updates, current, now
        except Exception:
            self.resources.close()
            self.resources = ExitStack()
            self.character = self.group = self.population = None
            raise

    def attack_target(self, name):
        from shadowbane_lab.cli_commands.client_player_attack import resolve_player_attack_target
        if self.character is None:
            raise ValueError("native character is unavailable")
        return resolve_player_attack_target(self.character, self.population, self.group, name)

    def close(self):
        self.resources.close()
