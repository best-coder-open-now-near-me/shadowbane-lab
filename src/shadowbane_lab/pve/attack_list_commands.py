"""Foreground-bound chat editing of persistent attack intent."""

from __future__ import annotations

import os
from pathlib import Path

from shadowbane_lab.client_input.character_config import open_active_character_config
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationReader,
    load_bundled_native_character_population_profile,
)
from shadowbane_lab.pve.attack_list import (
    AttackListEntry,
    AttackListOwner,
    AttackListStore,
    AttackPlayerIdentity,
    AttackTargetObservation,
)


def _parse_command(command):
    words = command.strip().split()
    if not words or words[0].casefold() != "/blacklist":
        raise ValueError("not an attack-list command")
    action = words[1].casefold() if len(words) > 1 else "list"
    if action not in {"add", "remove", "list", "clear"} or len(words) > 3:
        raise ValueError("use /blacklist add, remove [entry ID], list, or clear")
    if len(words) == 3 and action != "remove":
        raise ValueError("only remove accepts an entry ID; add uses the selected character")
    return words, action


def apply_attack_list_command(command, store, selected=None):
    words, action = _parse_command(command)
    if action == "add":
        if selected is None:
            raise ValueError("select a character before adding them to the attack list")
        result = store.add(selected)
    elif action == "remove":
        identity = (
            words[2] if len(words) == 3 else (selected.entry_id if selected is not None else None)
        )
        if identity is None:
            raise ValueError("select a character or provide the entry ID shown by list")
        result = store.remove(identity)
    elif action == "clear":
        result = store.clear()
    else:
        result = store.snapshot()
    return {
        "action": action,
        "revision": result.revision,
        "entries": [entry.as_dict() for entry in result.entries],
    }


def run_attack_list_command(command, guard, *, root: Path | None = None):
    """Edit only the character captured at command receipt, never a queued PID."""
    words, action = _parse_command(command)
    window = guard.require_target()
    if not window.process_id or not window.process_started_at_100ns:
        raise ValueError("attack-list command requires an exact client lifetime")
    if root is None:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            raise ValueError("LOCALAPPDATA is required for attack-list storage")
        root = Path(local) / "ShadowbaneLab" / "attack-lists"
    with open_active_character_config(process_id=window.process_id) as session:
        binding = session.binding
        if binding.process_creation_filetime_utc != window.process_started_at_100ns:
            raise ValueError("client lifetime changed before attack-list command")
        identity = binding.identity
        owner = AttackListOwner(identity.server_name, identity.character_name)
        store = AttackListStore(root, owner)
        needs_selection = len(words) == 2 and action in {"add", "remove"}
        selected = None
        if needs_selection:
            # Borrow the session's exact process handle; the session owns closure.
            reader = NativeCharacterPopulationReader(
                load_bundled_native_character_population_profile(),
                session.reader.process,
            )
            population = reader.observe()
            target = next(
                (c for c in population.characters if c.token == population.selected_target_token),
                None,
            )
            if target is not None and target.object_key is not None:
                # Only calibrated players receive a server-scoped persistent identity.
                # Other kinds retain historical evidence without automatic rebinding.
                evidence = AttackTargetObservation(
                    binding.executable_sha256,
                    window.process_id,
                    window.process_started_at_100ns,
                    population.local_player_object_key,
                    target.object_key,
                    target.character_kind.value,
                )
                player_identity = None
                if target.character_kind.value == "player":
                    remote = session.reader.observe_selected_player()
                    if remote.object_key != target.object_key:
                        raise ValueError("selection changed between population and identity reads")
                    player_identity = AttackPlayerIdentity(
                        remote.server_name,
                        remote.object_key,
                        remote.character_name,
                    )
                selected = AttackListEntry(
                    evidence.entry_id if player_identity is None else player_identity.entry_id,
                    (
                        f"Selected {target.character_kind.value} "
                        f"({target.object_key.canonical_token})"
                        if player_identity is None
                        else player_identity.name
                    ),
                    "manual",
                    f"selected:{target.object_key.canonical_token}",
                    evidence,
                    player_identity,
                )
        session.require_current()
        current = guard.require_target()
        if (current.process_id, current.process_started_at_100ns, current.window_handle) != (
            window.process_id,
            window.process_started_at_100ns,
            window.window_handle,
        ):
            raise ValueError("foreground client changed during attack-list command")
        return apply_attack_list_command(command, store, selected)
