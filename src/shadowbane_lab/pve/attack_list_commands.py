"""Foreground-bound chat editing of persistent attack intent."""

from __future__ import annotations

import os
from pathlib import Path

from shadowbane_lab.client_input.character_config import open_active_character_config
from shadowbane_lab.client_observation.native_character_config import ActiveCharacterError
from shadowbane_lab.client_observation.native_group import (
    NativeGroupError,
    NativeGroupReader,
    load_bundled_native_group_profile,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
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
from shadowbane_lab.pve.authority_snapshot import native_party_identity_signature


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


def apply_attack_list_command(command, store, selected=None, *, expected_revision=None):
    words, action = _parse_command(command)
    if action == "add":
        if selected is None:
            raise ValueError("select a character before adding them to the attack list")
        result = store.add(selected, expected_revision=expected_revision)
    elif action == "remove":
        identity = (
            words[2] if len(words) == 3 else (selected.entry_id if selected is not None else None)
        )
        if identity is None:
            raise ValueError("select a character or provide the entry ID shown by list")
        result = store.remove(identity, expected_revision=expected_revision)
    elif action == "clear":
        result = store.clear(expected_revision=expected_revision)
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
        initial_revision = store.snapshot().revision
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
        if selected is not None:
            latest = reader.observe()
            latest_target = next(
                (c for c in latest.characters if c.token == latest.selected_target_token), None
            )
            if (latest.local_player_object_key != population.local_player_object_key
                    or latest_target is None
                    or latest_target.token != target.token
                    or latest_target.object_key != target.object_key
                    or latest_target.character_kind != target.character_kind):
                raise ValueError("selection changed before attack-list mutation")
            if player_identity is not None:
                latest_identity = session.reader.observe_selected_player()
                if (latest_identity.object_key != player_identity.object_key
                        or latest_identity.character_name != player_identity.name
                        or latest_identity.server_name != player_identity.server):
                    raise ValueError("player identity changed before attack-list mutation")
        current = guard.require_target()
        if (current.process_id, current.process_started_at_100ns, current.window_handle) != (
            window.process_id,
            window.process_started_at_100ns,
            window.window_handle,
        ):
            raise ValueError("foreground client changed during attack-list command")
        result = apply_attack_list_command(
            command, store, selected, expected_revision=initial_revision
        )
        # Status is an observation, never cached attack permission. A failed party
        # read must not prevent removal or erase the successful edit's receipt.
        party_keys = None
        try:
            group_reader = NativeGroupReader(
                load_bundled_native_group_profile(), session.reader.process
            )
            group = group_reader.observe()
            session.require_current()
            party_keys = {NativeObjectKey(m.object_type, m.object_uuid) for m in group.members}
        except (NativeGroupError, RuntimeError, OSError, ValueError):
            pass
        current_player = None
        try:
            remote = session.reader.observe_selected_player()
            session.require_current()
            current_player = AttackPlayerIdentity(
                remote.server_name, remote.object_key, remote.character_name
            )
            if party_keys is not None:
                after = group_reader.observe()
                if native_party_identity_signature(group) != native_party_identity_signature(after):
                    party_keys = None
        except (ActiveCharacterError, NativeGroupError, OSError, ValueError):
            current_player = None
            party_keys = None
        return describe_attack_list_result(result, party_keys, current_player=current_player)


def describe_attack_list_result(result, party_keys=None, *, current_player=None):
    """Present retained intent and positive roster protection without granting authority."""
    entries = []
    for raw in result["entries"]:
        entry = dict(raw)
        identity = entry.get("player_identity")
        entry["identity_status"] = "saved_player" if identity else "unresolved"
        if not identity or party_keys is None:
            entry["party_status"] = "unknown"
        elif NativeObjectKey.from_dict(identity["object_key"]) in party_keys:
            entry["party_status"] = "protected"
        else:
            entry["party_status"] = "not_in_observed_roster"
        entry["selected_binding"] = selected_player_binding_status(
            identity, current_player, party_keys
        )
        entries.append(entry)
    return {**result, "entries": entries}


def selected_player_binding_status(saved_identity, current_player, party_keys):
    """Describe a fresh selected-player match; this never authorizes an attack.

    A match carries no reusable lifetime lease. Combat must independently recheck
    current process/character/selection, list revision, party and native legality.
    """
    if saved_identity is None:
        return "unresolved_identity"
    saved = AttackPlayerIdentity.from_dict(saved_identity)
    if current_player is None:
        return "selection_unavailable"
    if saved.server != current_player.server or saved.object_key != current_player.object_key:
        return "different_selected_player"
    if saved.name != current_player.name:
        return "identity_conflict"
    if party_keys is None:
        return "party_unknown"
    if saved.object_key in party_keys:
        return "party_protected"
    return "selected_identity_matches"
