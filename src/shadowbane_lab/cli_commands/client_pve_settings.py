"""Inspect or edit PvE preferences for the exact currently loaded character."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from shadowbane_lab.client_observation.native_ability import resolve_learned_ability
from shadowbane_lab.client_observation.native_character_session import open_native_character_session
from shadowbane_lab.pve.buff_intent import BuffSettings
from shadowbane_lab.pve.settings import load_pve_settings, save_pve_settings
from shadowbane_lab.record_store import read_record_bytes

from .common import _error


def _configure_pve_settings(
    *,
    process_id: int,
    policy: str | None = None,
    opening_skill: str | None = None,
    clear_opening_skill: bool = False,
    as_json: bool = False,
    buff_config: Path | None = None,
    buffs_enabled: bool | None = None,
) -> int:
    try:
        if type(process_id) is not int or process_id <= 0:
            raise ValueError("process-id must be positive")
        if type(clear_opening_skill) is not bool:
            raise ValueError("clear-opening-skill must be boolean")
        if opening_skill is not None and clear_opening_skill:
            raise ValueError("opening-skill and clear-opening-skill are mutually exclusive")
        if buffs_enabled is not None and type(buffs_enabled) is not bool:
            raise ValueError("buffs-enabled must be boolean")
        configured_buffs = None
        if buff_config is not None:
            from shadowbane_lab.pve.settings import _unique_object
            path = Path(buff_config)
            if path.is_symlink():
                raise ValueError("buff configuration must not be a symlink")
            configured_buffs = BuffSettings.from_dict(json.loads(
                read_record_bytes(path, 16_384), object_pairs_hook=_unique_object))
        with open_native_character_session(process_id=process_id) as session:
            identity = session.binding.identity
            original = load_pve_settings(identity)
            changes = {}
            resolved = None
            if policy is not None:
                changes["policy"] = policy
            if opening_skill is not None:
                resolved = resolve_learned_ability(session, opening_skill)
                # Persist stable numeric intent, not a potentially ambiguous future name.
                changes["opening_skill"] = str(resolved.power_id)
            elif clear_opening_skill:
                changes["opening_skill"] = None
            buffs = original.buffs if configured_buffs is None else configured_buffs
            if buffs_enabled is not None:
                buffs = replace(buffs, enabled=buffs_enabled)
            if configured_buffs is not None or buffs_enabled is not None:
                changes["buffs"] = buffs
            settings = replace(original, **changes)
            if changes:
                settings = save_pve_settings(
                    identity, settings, expected=original, require_current=session.require_current
                )
            else:
                session.require_current()
            payload = {
                "state": "saved" if changes else "observed",
                "character": identity.character_name,
                "server": identity.server_name,
                "settings": settings.as_dict(),
                "resolved_ability": None if resolved is None else resolved.as_dict(),
                "effective_scope": "next PvE run; current native learned eligibility rechecked",
            }
        if as_json:
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print(
                f"{payload['state']}: {payload['character']} on {payload['server']}: "
                f"policy={settings.policy}, opening_skill={settings.opening_skill or 'none'}, "
                f"buffs={'enabled' if settings.buffs.enabled else 'disabled'}, "
                f"revision={settings.revision}"
            )
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"PvE settings failed: {exc}", as_json=as_json)
